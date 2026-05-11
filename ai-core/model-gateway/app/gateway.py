"""ModelGateway: dispatches requests to backends according to routing policy.

Flow for chat/completions
─────────────────────────
1. RoutingPolicyEngine.decide() → PolicyDecision (ordered backend list)
2. For each backend in decision.backends:
   a. Resolve ProviderConfig (base_url, api_key, timeout)
   b. Send the HTTP request to the backend
   c. On success → convert to ChatCompletionResponse, audit, return
   d. On failure (network error, non-2xx, timeout):
        - audit the failure
        - if local-only and backend==ollama → raise GatewayError(503) immediately
        - otherwise try next backend
3. If all backends fail → raise GatewayError(503)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx

from app.audit import AuditLogger
from app.config import ProviderConfig, RoutingPolicyConfig
from app.vyrex import VyrexMiddleware
from app.policy import RoutingPolicyEngine
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    CompletionChoice,
    UsageInfo,
)
logger = logging.getLogger(__name__)
_CONTENT_TYPE_JSON = "application/json"


class GatewayError(Exception):
    """Raised when all backends fail or a policy blocks the request."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class ModelGateway:
    """Async request dispatcher."""

    def __init__(
        self,
        policy_cfg: RoutingPolicyConfig,
        policy_engine: RoutingPolicyEngine,
        audit: AuditLogger,
        vyrex: Optional[VyrexMiddleware] = None,
    ) -> None:
        self._policy = policy_cfg
        self._engine = policy_engine
        self._audit = audit
        self._vyrex = vyrex

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        correlation_id: str,
    ) -> ChatCompletionResponse:
        request = await self._apply_vyrex_request(request)

        decision = self._engine.decide(request.model)
        await self._audit.log_request(
            correlation_id=correlation_id,
            endpoint="chat/completions",
            model=request.model,
            policy_mode=self._policy.mode,
            backends_to_try=decision.backends,
        )

        if not decision.allowed:
            raise GatewayError(
                f"Request blocked by policy: {decision.reason}", status_code=403
            )

        return await self._run_backend_loop(
            request=request,
            correlation_id=correlation_id,
            backends=decision.backends,
        )

    async def _apply_vyrex_request(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionRequest:
        if not self._vyrex or not self._vyrex.enabled:
            return request
        try:
            sanitized_payload = await self._vyrex.wrap_request(
                request.model,
                [message.model_dump(exclude_none=True) for message in request.messages],
                request.model_dump(exclude_none=True),
            )
            return ChatCompletionRequest.model_validate(sanitized_payload)
        except ValueError as exc:
            raise GatewayError(f"Vyrex blocked request: {exc}", status_code=400) from exc

    async def _run_backend_loop(
        self,
        *,
        request: ChatCompletionRequest,
        correlation_id: str,
        backends: List[str],
    ) -> ChatCompletionResponse:
        last_error: Optional[Exception] = None

        for backend in backends:
            provider_cfg = self._policy.get_provider(backend)
            if provider_cfg is None:
                logger.debug("Backend '%s' not found in provider config, skipping", backend)
                continue

            try:
                response = await self._dispatch_chat(
                    backend,
                    provider_cfg,
                    request,
                    correlation_id,
                )
                response = await self._apply_vyrex_response(response)
                await self._audit.log_response(
                    correlation_id=correlation_id,
                    backend=backend,
                    success=True,
                    model=response.model,
                )
                return response
            except Exception as exc:
                last_error = await self._handle_backend_error(backend, correlation_id, exc)

        raise GatewayError(
            f"All backends exhausted. Last error: {last_error}",
            status_code=503,
        )

    async def _apply_vyrex_response(
        self,
        response: ChatCompletionResponse,
    ) -> ChatCompletionResponse:
        if not self._vyrex or not self._vyrex.enabled:
            return response
        wrapped = await self._vyrex.wrap_response(response.model_dump())
        return ChatCompletionResponse.model_validate(wrapped)

    async def _handle_backend_error(
        self,
        backend: str,
        correlation_id: str,
        exc: Exception,
    ) -> Exception:
        if isinstance(exc, GatewayError):
            logger.warning(
                "Backend '%s' gateway error [correlation_id=%s]: %s",
                backend,
                correlation_id,
                exc,
            )
        else:
            logger.warning(
                "Backend '%s' failed [correlation_id=%s]: %s",
                backend,
                correlation_id,
                exc,
            )

        await self._audit.log_response(
            correlation_id=correlation_id,
            backend=backend,
            success=False,
            error=str(exc),
        )

        if self._engine.is_local_only():
            raise GatewayError(
                f"local-only policy: Ollama unavailable and cloud fallback is blocked. "
                f"Error: {exc}",
                status_code=503,
            ) from exc

        return exc

    async def completion(
        self,
        request: CompletionRequest,
        correlation_id: str,
    ) -> CompletionResponse:
        """Text completion – converted internally to chat format."""
        if isinstance(request.prompt, str):
            prompt = request.prompt
        elif request.prompt:
            prompt = request.prompt[0]
        else:
            prompt = ""
        chat_req = ChatCompletionRequest(
            model=request.model,
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            n=request.n,
            stream=request.stream,
            stop=request.stop,
        )
        chat_resp = await self.chat_completion(chat_req, correlation_id)

        choices = [
            CompletionChoice(
                index=choice.index,
                text=choice.message.content or "",
                finish_reason=choice.finish_reason,
            )
            for choice in chat_resp.choices
        ]
        return CompletionResponse(
            model=chat_resp.model,
            choices=choices,
            usage=chat_resp.usage,
        )

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch_chat(
        self,
        backend: str,
        provider_cfg: ProviderConfig,
        request: ChatCompletionRequest,
        correlation_id: str,
    ) -> ChatCompletionResponse:
        if backend == "ollama":
            return await self._ollama_chat(provider_cfg, request, correlation_id)
        if backend == "openai":
            return await self._openai_chat(provider_cfg, request, correlation_id)
        if backend == "anthropic":
            return await self._anthropic_chat(provider_cfg, request, correlation_id)
        if backend == "vyrex":
            return await self._vyrex_chat(provider_cfg, request, correlation_id)
        raise GatewayError(f"Unknown backend: '{backend}'", status_code=500)

    # ------------------------------------------------------------------
    # Backend implementations
    # ------------------------------------------------------------------

    async def _ollama_chat(
        self,
        cfg: ProviderConfig,
        request: ChatCompletionRequest,
        correlation_id: str,
    ) -> ChatCompletionResponse:
        url = f"{cfg.base_url}/v1/chat/completions"
        payload = request.model_dump(exclude_none=True)
        headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": correlation_id,
        }
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        return ChatCompletionResponse.model_validate(resp.json())

    async def _openai_chat(
        self,
        cfg: ProviderConfig,
        request: ChatCompletionRequest,
        correlation_id: str,
    ) -> ChatCompletionResponse:
        api_key = cfg.api_key
        if not api_key:
            raise GatewayError("OpenAI API key not configured (OPENAI_API_KEY)", status_code=503)

        url = f"{cfg.base_url}/chat/completions"
        payload = request.model_dump(exclude_none=True)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": _CONTENT_TYPE_JSON,
            "X-Correlation-ID": correlation_id,
        }
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        return ChatCompletionResponse.model_validate(resp.json())

    async def _anthropic_chat(
        self,
        cfg: ProviderConfig,
        request: ChatCompletionRequest,
        correlation_id: str,
    ) -> ChatCompletionResponse:
        api_key = cfg.api_key
        if not api_key:
            raise GatewayError(
                "Anthropic API key not configured (ANTHROPIC_API_KEY)", status_code=503
            )

        # Convert OpenAI messages → Anthropic Messages API format
        system_content: Optional[str] = None
        messages: list[Dict[str, Any]] = []
        for msg in request.messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                messages.append({"role": msg.role, "content": msg.content or ""})

        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1024,
        }
        if system_content:
            payload["system"] = system_content
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.stop:
            payload["stop_sequences"] = (
                [request.stop] if isinstance(request.stop, str) else request.stop
            )

        url = f"{cfg.base_url}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": _CONTENT_TYPE_JSON,
            "X-Correlation-ID": correlation_id,
        }
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()

        data = resp.json()
        content = ""
        if data.get("content"):
            block = data["content"][0]
            content = block.get("text", "")

        usage_data = data.get("usage") or {}
        prompt_tokens = usage_data.get("input_tokens", 0)
        completion_tokens = usage_data.get("output_tokens", 0)

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{uuid.uuid4().hex[:12]}"),
            model=data.get("model", request.model),
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason=_anthropic_stop_reason(data.get("stop_reason")),
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def _vyrex_chat(
        self,
        cfg: ProviderConfig,
        request: ChatCompletionRequest,
        correlation_id: str,
    ) -> ChatCompletionResponse:
        if not self._vyrex or not self._vyrex.enabled:
            raise GatewayError("Vyrex backend requested but middleware is disabled", status_code=503)

        url = f"{cfg.base_url}/v1/chat/completions"
        payload = request.model_dump(exclude_none=True)
        headers = {
            "Content-Type": _CONTENT_TYPE_JSON,
            "X-Correlation-ID": correlation_id,
        }
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()

        return ChatCompletionResponse.model_validate(resp.json())

    async def pull_model(self, source: str, checksum: Optional[str] = None) -> Dict[str, Any]:
        if not self._vyrex:
            return {
                "status": "error",
                "source": source,
                "detail": "Vyrex middleware not configured",
            }
        if not self._vyrex.enabled:
            return {
                "status": "error",
                "source": source,
                "detail": "Vyrex middleware is disabled (VYREX_ENABLED=false)",
            }
        return await self._vyrex.pull_model(source, checksum=checksum)

    async def list_loaded_models(self) -> List[Dict[str, Any]]:
        if not self._vyrex:
            return []
        return await self._vyrex.list_loaded_models()


def _anthropic_stop_reason(reason: Optional[str]) -> str:
    mapping = {"end_turn": "stop", "max_tokens": "length", "stop_sequence": "stop"}
    return mapping.get(reason or "", "stop")
