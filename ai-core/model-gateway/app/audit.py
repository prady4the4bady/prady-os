"""Structured audit logger.

Appends one JSON-Lines record per event to ``logs/audit.jsonl``.
Two event kinds are emitted per request:
  - ``request``  – logged when the gateway receives the request
  - ``response`` – logged for *each* backend attempt (success or failure)

File writes are serialised via an :class:`asyncio.Lock` so concurrent
coroutines never interleave partial writes.

Environment:
  GATEWAY_LOG_DIR  – directory that holds audit.jsonl
                     (defaults to <repo-root>/logs)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _log_dir() -> Path:
    env = os.getenv("GATEWAY_LOG_DIR")
    if env:
        return Path(env)
    # app/audit.py → ../logs/
    return Path(__file__).parent.parent / "logs"


class AuditLogger:
    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self._dir = log_dir or _log_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "audit.jsonl"
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    async def log_request(
        self,
        correlation_id: str,
        endpoint: str,
        model: str,
        policy_mode: str,
        backends_to_try: List[str],
    ) -> None:
        record: Dict[str, Any] = {
            "event": "request",
            "ts": _now(),
            "correlation_id": correlation_id,
            "endpoint": endpoint,
            "model": model,
            "policy_mode": policy_mode,
            "backends_to_try": backends_to_try,
        }
        await self._append(record)

    async def log_response(
        self,
        correlation_id: str,
        backend: str,
        success: bool,
        model: Optional[str] = None,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> None:
        record: Dict[str, Any] = {
            "event": "response",
            "ts": _now(),
            "correlation_id": correlation_id,
            "backend": backend,
            "success": success,
        }
        if model:
            record["model"] = model
        if error:
            record["error"] = error
        if latency_ms is not None:
            record["latency_ms"] = latency_ms
        await self._append(record)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _append(self, record: Dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append_sync, line)

    def _append_sync(self, line: str) -> None:
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line)

    @property
    def log_path(self) -> Path:
        return self._path


def _now() -> str:
    """ISO-8601 UTC timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_audit: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger()
    return _audit


def reset_audit_logger() -> None:
    """Reset the singleton – useful in tests."""
    global _audit
    _audit = None
