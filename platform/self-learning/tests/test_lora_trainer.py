from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lora_trainer import LoRATrainer


@pytest.mark.asyncio
async def test_schedule_skipped_when_busy(monkeypatch, tmp_path: Path):
    trainer = LoRATrainer("http://vyrex-proxy:8000", str(tmp_path))

    monkeypatch.setattr("lora_trainer.psutil.cpu_percent", lambda interval=1: 90.0)

    class _Mem:
        available = 10 * 1024 * 1024 * 1024

    monkeypatch.setattr("lora_trainer.psutil.virtual_memory", lambda: _Mem())

    job_id = await trainer.schedule()
    status = await trainer.get_status(job_id)
    assert status["status"] == "skipped"


@pytest.mark.asyncio
async def test_schedule_runs_when_idle(monkeypatch, tmp_path: Path):
    trainer = LoRATrainer("http://vyrex-proxy:8000", str(tmp_path))

    monkeypatch.setattr("lora_trainer.psutil.cpu_percent", lambda interval=1: 5.0)

    class _Mem:
        available = 10 * 1024 * 1024 * 1024

    monkeypatch.setattr("lora_trainer.psutil.virtual_memory", lambda: _Mem())

    async def fake_provider():
        return [{"task_description": "x", "action_sequence": [{"step": "a"}], "score": 0.9, "outcome": "success"}]

    trainer.set_skill_provider(fake_provider)

    async def fake_run(job_id: str, skill_data):
        trainer._jobs[job_id].update({
            "status": "complete",
            "progress_pct": 100,
            "eta_seconds": 0,
            "log_tail": "training complete",
        })

    monkeypatch.setattr(trainer, "_run_training", fake_run)

    job_id = await trainer.schedule()
    await asyncio.sleep(0.01)
    status = await trainer.get_status(job_id)
    assert status["status"] in {"running", "complete"}
