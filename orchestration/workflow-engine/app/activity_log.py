"""Activity logger: appends structured JSONL records to disk.

Every task start, subtask assignment, agent response, approval event,
and completion is written to logs/activity.jsonl with a UTC timestamp.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _append_json_line(path: Path, record: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


class ActivityLogger:
    def __init__(self, log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        self._path = log_dir / "activity.jsonl"
        self._lock = asyncio.Lock()

    async def log(self, event: str, task_id: str, **kwargs: Any) -> None:
        record: dict[str, Any] = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
        }
        for k, v in kwargs.items():
            if v is not None:
                record[k] = v
        await self._append(record)

    async def _append(self, record: dict[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(_append_json_line, self._path, record)

    @property
    def log_path(self) -> Path:
        return self._path
