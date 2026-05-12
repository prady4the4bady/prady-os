"""Vyrex security middleware for model-gateway.

Canonical module: ``app.vyrex``.

``app.vyrex`` is kept as a backwards-compatibility shim that re-exports
everything from this module so that older imports continue to work.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import anyio
import httpx
from huggingface_hub import snapshot_download


_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+mode", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"bypass\s+safety", re.IGNORECASE),
]

_OUTPUT_BLOCK_PATTERNS = [
    re.compile(r"api[_-]?key\s*[:=]", re.IGNORECASE),
    re.compile(r"BEGIN\s+PRIVATE\s+KEY", re.IGNORECASE),
    re.compile(r"password\s*[:=]", re.IGNORECASE),
]


class VyrexMiddleware:
    def __init__(
        self,
        *,
        enabled: bool = False,
        endpoint: str = "http://localhost:8000",
        storage_dir: str = "/opt/kryos/models",
        hf_token: Optional[str] = None,
    ) -> None:
        self.enabled = enabled
        self.endpoint = endpoint.rstrip("/")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.hf_token = hf_token or os.getenv("HUGGINGFACE_TOKEN")
        self._loaded_models: Dict[str, Dict[str, Any]] = {}
        self.nvidia_gpu_detected = self._detect_nvidia_gpu()

    @staticmethod
    def _detect_nvidia_gpu() -> bool:
        if shutil.which("nvidia-smi") is None:
            return False
        try:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
            return proc.returncode == 0 and bool(proc.stdout.strip())
        except Exception:
            return False

    @staticmethod
    def _contains_prompt_injection(text: str) -> bool:
        return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)

    @staticmethod
    def _contains_blocked_output(text: str) -> bool:
        return any(pattern.search(text) for pattern in _OUTPUT_BLOCK_PATTERNS)

    @staticmethod
    def _sanitize_text(text: str) -> str:
        sanitized = text.replace("\x00", "")
        return "".join(ch for ch in sanitized if ch.isprintable() or ch in "\n\t\r")

    async def wrap_request(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        await anyio.sleep(0)
        sanitized_messages: List[Dict[str, Any]] = []
        for msg in messages:
            cloned = dict(msg)
            content = str(cloned.get("content") or "")
            sanitized_content = self._sanitize_text(content)
            if self._contains_prompt_injection(sanitized_content):
                raise ValueError("prompt injection pattern detected")
            cloned["content"] = sanitized_content
            sanitized_messages.append(cloned)

        sanitized_params = dict(params)
        sanitized_params["model"] = model_id.strip()
        sanitized_params["messages"] = sanitized_messages
        return sanitized_params

    async def wrap_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        await anyio.sleep(0)
        filtered = dict(response)
        choices = filtered.get("choices")
        if isinstance(choices, list):
            safe_choices: List[Dict[str, Any]] = []
            for choice in choices:
                cloned = dict(choice)
                message = dict(cloned.get("message") or {})
                content = str(message.get("content") or "")
                if self._contains_blocked_output(content):
                    message["content"] = "[filtered by Vyrex security policy]"
                cloned["message"] = message
                safe_choices.append(cloned)
            filtered["choices"] = safe_choices
        return filtered

    async def pull_model(self, source: str, checksum: Optional[str] = None) -> Dict[str, Any]:
        if source.startswith("huggingface:"):
            model_id = source.split(":", 1)[1].strip()
            local_dir = self.storage_dir / model_id.replace("/", "--")
            snapshot_download(
                repo_id=model_id,
                local_dir=str(local_dir),
                token=self.hf_token,
                local_dir_use_symlinks=False,
            )
            record = {
                "source": source,
                "model_id": model_id,
                "path": str(local_dir),
                "provider": "huggingface",
            }
            self._loaded_models[model_id] = record
            return {"status": "ok", **record}

        if source.startswith("github:"):
            url = source.split(":", 1)[1].strip()
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or "github.com" not in parsed.netloc.lower():
                raise ValueError("github source must be a valid github.com URL")

            filename = Path(parsed.path).name or "model.bin"
            model_id = f"github::{filename}"
            local_dir = self.storage_dir / "github"
            local_dir.mkdir(parents=True, exist_ok=True)
            target_path = local_dir / filename

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                target_path.write_bytes(resp.content)

            if checksum:
                digest = hashlib.sha256(target_path.read_bytes()).hexdigest()
                if digest.lower() != checksum.lower():
                    target_path.unlink(missing_ok=True)
                    raise ValueError("checksum validation failed for downloaded GitHub model")

            record = {
                "source": source,
                "model_id": model_id,
                "path": str(target_path),
                "provider": "github",
            }
            self._loaded_models[model_id] = record
            return {"status": "ok", **record}

        raise ValueError("unsupported model source. Use huggingface:<repo> or github:<url>")

    async def list_loaded_models(self) -> List[Dict[str, Any]]:
        await anyio.sleep(0)
        return list(self._loaded_models.values())


__all__ = [
    "VyrexMiddleware",
    "snapshot_download",
]
