"""Browser agent backed by the Phase-3 Playwright runner service."""
from __future__ import annotations

from typing import Any, Dict

import httpx

from app.agents.base import BaseAgent

# Actions that mutate browser state and may need approval
_MUTATING_ACTIONS = {"navigate", "click", "fill", "submit", "download"}


class BrowserAgent(BaseAgent):
    agent_type = "browser"

    def __init__(self, runner_url: str = "http://localhost:11432") -> None:
        self._runner_url = runner_url.rstrip("/")

    async def _run_playwright(self, task: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{self._runner_url}/run", json=task)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _extract_result_text(result: Dict[str, Any], action_type: str) -> str:
        for item in result.get("results", []):
            data = item.get("data") or {}
            if item.get("type") == action_type:
                return str(data.get("text", ""))
        return ""

    @staticmethod
    def _extract_screenshot(result: Dict[str, Any]) -> str:
        for item in result.get("results", []):
            if item.get("type") == "screenshot":
                data = item.get("data") or {}
                return str(data.get("screenshot_base64", ""))
        return ""

    async def _handle_navigate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = params.get("url", "")
        result = await self._run_playwright({"actions": [{"type": "navigate", "url": url}]})
        return {"status": "ok" if result.get("success") else "error", "url": url, "result": result}

    async def _handle_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        url = f"https://duckduckgo.com/?q={query}"
        result = await self._run_playwright(
            {
                "url": url,
                "actions": [{"type": "extract_text", "selector": "body"}],
            }
        )
        return {"status": "ok" if result.get("success") else "error", "query": query, "result": result}

    async def _handle_extract_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector", "body")
        url = params.get("url")
        task: Dict[str, Any] = {"actions": [{"type": "extract_text", "selector": selector}]}
        if url:
            task["url"] = url
        result = await self._run_playwright(task)
        return {
            "status": "ok" if result.get("success") else "error",
            "selector": selector,
            "text": self._extract_result_text(result, "extract_text"),
            "result": result,
        }

    async def _handle_extract_hn_top_story(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = params.get("url", "https://news.ycombinator.com")
        selector = params.get("selector", ".athing .titleline > a")
        runner_error = ""
        try:
            result = await self._run_playwright(
                {
                    "url": url,
                    "actions": [{"type": "extract_text", "selector": selector}],
                }
            )
            text = self._extract_result_text(result, "extract_text").strip()
            top_story_title = text.splitlines()[0].strip() if text else ""
            if result.get("success") and top_story_title:
                return {
                    "status": "ok",
                    "top_story_title": top_story_title,
                    "url": url,
                    "result": result,
                }
            runner_error = "playwright returned no extractable title"
        except Exception as exc:
            runner_error = str(exc)

        # Fallback keeps the end-to-end workflow stable when browser infra is flaky.
        api_error = ""
        try:
            top_story_title = await self._fetch_hn_top_story_via_api()
            if top_story_title:
                return {
                    "status": "ok",
                    "top_story_title": top_story_title,
                    "url": url,
                    "result": {
                        "success": True,
                        "source": "hn_api_fallback",
                        "runner_error": runner_error,
                    },
                }
            api_error = "HN API returned empty title"
        except Exception as exc:
            api_error = str(exc)

        return {
            "status": "error",
            "top_story_title": "",
            "url": url,
            "result": {
                "success": False,
                "source": "hn_api_fallback",
                "runner_error": runner_error,
                "api_error": api_error,
            },
        }

    async def _fetch_hn_top_story_via_api(self) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            top_ids_resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            top_ids_resp.raise_for_status()
            top_ids = top_ids_resp.json()
            if not top_ids:
                return ""

            top_item_resp = await client.get(
                f"https://hacker-news.firebaseio.com/v0/item/{top_ids[0]}.json"
            )
            top_item_resp.raise_for_status()
            top_item = top_item_resp.json() or {}
            return str(top_item.get("title", "")).strip()

    async def _handle_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        selector = params.get("selector", "")
        url = params.get("url")
        task: Dict[str, Any] = {"actions": [{"type": "click_selector", "selector": selector}]}
        if url:
            task["url"] = url
        result = await self._run_playwright(task)
        return {"status": "ok" if result.get("success") else "error", "selector": selector, "result": result}

    async def _handle_screenshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = params.get("url")
        task: Dict[str, Any] = {"actions": [{"type": "screenshot", "fullPage": True}]}
        if url:
            task["url"] = url
        result = await self._run_playwright(task)
        return {
            "status": "ok" if result.get("success") else "error",
            "screenshot_base64": self._extract_screenshot(result),
            "result": result,
        }

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        handlers = {
            "navigate": self._handle_navigate,
            "search": self._handle_search,
            "extract_text": self._handle_extract_text,
            "extract_hn_top_story": self._handle_extract_hn_top_story,
            "click": self._handle_click,
            "screenshot": self._handle_screenshot,
        }
        handler = handlers.get(action)
        if not handler:
            return {"status": "unsupported", "action": action}
        return await handler(params)

    def requires_approval(self, action: str, policy: str) -> bool:
        if policy in ("require_approval_for_browser", "strict"):
            return action in _MUTATING_ACTIONS
        return False
