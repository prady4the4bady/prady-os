"""On-device LoRA fine-tuning scheduler for self-learning."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
import psutil


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LoRATrainer:
    def __init__(self, vyrex_url: str, data_dir: str, audit_url: str | None = None) -> None:
        self.vyrex_url = vyrex_url.rstrip("/")
        self.data_dir = Path(data_dir)
        self.audit_url = audit_url.rstrip("/") if audit_url else None
        self._current_job: dict[str, Any] | None = None
        self._jobs: dict[str, dict[str, Any]] = {}
        self._skill_provider: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None

    def set_skill_provider(self, provider: Callable[[], Awaitable[list[dict[str, Any]]]]) -> None:
        self._skill_provider = provider

    async def schedule(self) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": "scheduled",
            "progress_pct": 0,
            "eta_seconds": None,
            "log_tail": "scheduled",
            "created_ts": _utc_now(),
        }

        cpu = psutil.cpu_percent(interval=1)
        mem_ok = psutil.virtual_memory().available > (2 * 1024 * 1024 * 1024)

        if cpu >= 20.0 or not mem_ok:
            self._jobs[job_id].update(
                {
                    "status": "skipped",
                    "progress_pct": 0,
                    "eta_seconds": 0,
                    "log_tail": f"skipped: cpu={cpu:.1f}%, mem_ok={mem_ok}",
                    "finished_ts": _utc_now(),
                }
            )
            return job_id

        self._jobs[job_id]["status"] = "running"
        self._jobs[job_id]["log_tail"] = "starting training"

        skill_data = []
        if self._skill_provider is not None:
            skill_data = await self._skill_provider()

        asyncio.create_task(self._run_training(job_id, skill_data))
        self._current_job = self._jobs[job_id]
        return job_id

    async def _run_training(self, job_id: str, skill_data: list[dict[str, Any]]) -> None:
        job = self._jobs[job_id]
        job["status"] = "running"
        job["progress_pct"] = 10

        self.data_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = self.data_dir / f"lora_train_{job_id}.jsonl"

        top = sorted(skill_data, key=lambda s: float(s.get("score", 0.0)), reverse=True)[:100]
        with dataset_path.open("w", encoding="utf-8") as fh:
            for item in top:
                prompt = item.get("task_description", "")
                completion = json.dumps(item.get("action_sequence", []), ensure_ascii=True)
                fh.write(json.dumps({"prompt": prompt, "completion": completion}) + "\n")

        job["progress_pct"] = 45
        job["eta_seconds"] = 30
        job["log_tail"] = f"prepared dataset with {len(top)} skills"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.vyrex_url}/v1/fine-tune",
                    json={
                        "job_id": job_id,
                        "dataset_path": str(dataset_path),
                        "format": "jsonl",
                        "adapter": "lora",
                    },
                )

            if resp.status_code == 404:
                msg = "Fine-tuning not available in current model"
                job.update({"status": "skipped", "progress_pct": 100, "eta_seconds": 0, "log_tail": msg, "finished_ts": _utc_now()})
                await self._audit(msg, level="warning")
                return

            if resp.status_code >= 400:
                msg = f"fine-tune request failed: {resp.status_code}"
                job.update({"status": "failed", "progress_pct": 100, "eta_seconds": 0, "log_tail": msg, "finished_ts": _utc_now()})
                await self._audit(msg, level="error")
                return

            job.update({"status": "complete", "progress_pct": 100, "eta_seconds": 0, "log_tail": "training complete", "finished_ts": _utc_now()})
            await self._audit("training complete", level="info")

        except Exception as exc:
            msg = f"training exception: {exc}"
            job.update({"status": "failed", "progress_pct": 100, "eta_seconds": 0, "log_tail": msg, "finished_ts": _utc_now()})
            await self._audit(msg, level="error")

    async def _audit(self, message: str, level: str) -> None:
        if not self.audit_url:
            return
        payload = {
            "service": "self-learning",
            "event": "lora_training",
            "level": level,
            "message": message,
            "ts": _utc_now(),
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{self.audit_url}/audit/events", json=payload)
        except Exception:
            pass

    async def get_status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            return {
                "job_id": job_id,
                "status": "not_found",
                "progress_pct": 0,
                "eta_seconds": None,
                "log_tail": "unknown job",
            }
        return {
            "job_id": job_id,
            "status": job["status"],
            "progress_pct": job["progress_pct"],
            "eta_seconds": job.get("eta_seconds"),
            "log_tail": job.get("log_tail", ""),
        }

    @property
    def training_runs(self) -> int:
        return len(self._jobs)

    @property
    def last_training_ts(self) -> str | None:
        if not self._jobs:
            return None
        # latest finished/created timestamp
        latest = None
        for j in self._jobs.values():
            ts = j.get("finished_ts") or j.get("created_ts")
            if ts and (latest is None or ts > latest):
                latest = ts
        return latest
