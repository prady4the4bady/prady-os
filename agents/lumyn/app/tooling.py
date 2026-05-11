from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import httpx


SAFE_SHELL_PREFIXES = (
    "ls",
    "pwd",
    "cat",
    "echo",
    "grep",
    "find",
    "head",
    "tail",
)


class LumynTools:
    def __init__(
        self,
        *,
        workflow_engine_url: str,
        screen_agent_url: str,
        auto_approve_safe_actions: bool,
        workspace_root: Path,
    ) -> None:
        self.workflow_engine_url = workflow_engine_url.rstrip("/")
        self.screen_agent_url = screen_agent_url.rstrip("/")
        self.auto_approve_safe_actions = auto_approve_safe_actions
        self.workspace_root = workspace_root
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self.client.aclose()

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "search_web",
                "description": "Search the web and return concise snippets.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 5}},
                    "required": ["query"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a UTF-8 text file from workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write UTF-8 text content to workspace file.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                },
            },
            {
                "name": "run_shell",
                "description": "Run a shell command for local diagnostics.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
            {
                "name": "take_screenshot",
                "description": "Capture screen via screen-agent.",
                "parameters": {
                    "type": "object",
                    "properties": {"label": {"type": "string", "default": "lumyn"}},
                },
            },
            {
                "name": "submit_task",
                "description": "Submit goal to workflow-engine.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"], "default": "normal"},
                    },
                    "required": ["goal"],
                },
            },
        ]

    async def execute(self, name: str, args: dict[str, Any]) -> str:
        handlers = {
            "search_web": self.search_web,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "run_shell": self.run_shell,
            "take_screenshot": self.take_screenshot,
            "submit_task": self.submit_task,
        }
        if name not in handlers:
            raise ValueError(f"Unknown tool: {name}")
        out = await handlers[name](**args)
        if isinstance(out, str):
            return out
        return json.dumps(out, ensure_ascii=True)

    async def search_web(self, query: str, top_k: int = 5) -> dict[str, Any]:
        # DuckDuckGo lite HTML endpoint; no API key needed.
        resp = await self.client.get("https://duckduckgo.com/html/", params={"q": query})
        resp.raise_for_status()
        text = resp.text
        snippets: list[str] = []
        marker = 'result__snippet'
        for chunk in text.split("<"):
            if marker in chunk:
                cleaned = chunk.split(">")[-1].strip()
                if cleaned:
                    snippets.append(cleaned)
            if len(snippets) >= top_k:
                break
        return {"query": query, "results": snippets}

    async def read_file(self, path: str) -> dict[str, Any]:
        file_path = (self.workspace_root / path).resolve()
        self._assert_in_workspace(file_path)
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        return {"path": str(file_path), "content": content}

    async def write_file(self, path: str, content: str) -> dict[str, Any]:
        file_path = (self.workspace_root / path).resolve()
        self._assert_in_workspace(file_path)
        await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")
        return {"path": str(file_path), "bytes": len(content.encode("utf-8"))}

    async def run_shell(self, command: str) -> dict[str, Any]:
        if self.auto_approve_safe_actions and not command.startswith(SAFE_SHELL_PREFIXES):
            raise PermissionError(f"Command requires approval: {command}")
        proc = await asyncio.to_thread(
            subprocess.run,
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(self.workspace_root),
            timeout=45,
            check=False,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-8000:],
        }

    async def take_screenshot(self, label: str = "lumyn") -> dict[str, Any]:
        resp = await self.client.post(
            f"{self.screen_agent_url}/actions/screenshot",
            json={"label": label},
        )
        resp.raise_for_status()
        return resp.json()

    async def submit_task(self, goal: str, priority: str = "normal") -> dict[str, Any]:
        payload = {
            "goal": goal,
            "priority": priority,
            "metadata": {"source": "lumyn-agent"},
        }
        resp = await self.client.post(f"{self.workflow_engine_url}/tasks", json=payload)
        resp.raise_for_status()
        return resp.json()

    def _assert_in_workspace(self, path: Path) -> None:
        root = self.workspace_root.resolve()
        if root == path or root in path.parents:
            return
        raise PermissionError(f"Path escapes workspace: {path}")
