"""Self-Learning Agent Loop service (Phase 35) - port 8018."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from embedding_engine import EmbeddingEngine
from lora_trainer import LoRATrainer
from skill_library import SkillLibrary
from task_evaluator import TaskEvaluator, TaskRecord

import os

VERSION = "1.0.0"
SERVICE_NAME = "self-learning"
MODEL_VERSION = EmbeddingEngine.MODEL_NAME

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "self_learning.db"
VYREX_URL = os.environ.get("VYREX_URL", "http://vyrex-proxy:8000")
AUDIT_LOG_URL = os.environ.get("AUDIT_LOG_URL", "http://audit-log:8006")


class LearnRecordRequest(BaseModel):
    task_id: str
    task_description: str
    action_sequence: list[dict[str, Any]]
    outcome: str
    duration_ms: int
    error_message: str | None = None
    model_used: str
    user_rating: int | None = Field(default=None, ge=1, le=5)


class RetrieveRequest(BaseModel):
    task_description: str
    top_k: int = Field(default=3, ge=1, le=20)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedding_engine = EmbeddingEngine()
    app.state.skill_library = SkillLibrary(DB_PATH, app.state.embedding_engine)
    await app.state.skill_library.init()
    app.state.task_evaluator = TaskEvaluator()
    app.state.lora_trainer = LoRATrainer(VYREX_URL, str(DATA_DIR), audit_url=AUDIT_LOG_URL)

    async def _provider() -> list[dict[str, Any]]:
        return await app.state.skill_library.top_skills(limit=100)

    app.state.lora_trainer.set_skill_provider(_provider)
    yield


app = FastAPI(title="Kryos Self-Learning Service", version=VERSION, lifespan=lifespan)


@app.post("/learn/record")
async def learn_record(req: LearnRecordRequest) -> dict[str, Any]:
    task_record = TaskRecord(
        record_id=str(uuid.uuid4()),
        task_id=req.task_id,
        task_description=req.task_description,
        outcome=req.outcome,
        score=0.0,
        duration_ms=req.duration_ms,
        model_used=req.model_used,
        user_rating=req.user_rating,
        error_message=req.error_message,
        skill_id=None,
        recorded_ts=_utc_now(),
    )

    score = app.state.task_evaluator.score(task_record)
    task_record.score = score

    skill_stored = False
    skill_id: str | None = None
    if app.state.task_evaluator.should_store_as_skill(score, req.outcome):
        emb = app.state.embedding_engine.embed(req.task_description)
        skill_id = await app.state.skill_library.store_skill(
            req.task_description,
            req.action_sequence,
            emb,
            score,
            req.outcome,
        )
        task_record.skill_id = skill_id
        skill_stored = True

    await app.state.skill_library.record_task(task_record)

    return {"skill_stored": skill_stored, "skill_id": skill_id, "score": score}


@app.get("/learn/skills")
async def learn_skills() -> list[dict[str, Any]]:
    skills = await app.state.skill_library.get_all_skills()
    return [
        {
            "skill_id": s.skill_id,
            "description": s.description,
            "use_count": s.use_count,
            "avg_score": s.score,
            "last_used": s.last_used_ts,
            "embedding_preview": s.embedding_preview,
        }
        for s in skills
    ]


@app.post("/learn/retrieve")
async def learn_retrieve(req: RetrieveRequest) -> list[dict[str, Any]]:
    q = app.state.embedding_engine.embed(req.task_description)
    matches = await app.state.skill_library.retrieve_similar(q, top_k=req.top_k)
    return [
        {
            "skill_id": m.skill_id,
            "description": m.description,
            "similarity": m.similarity,
            "action_sequence": m.action_sequence,
            "avg_score": m.avg_score,
        }
        for m in matches
    ]


@app.get("/learn/stats")
async def learn_stats() -> dict[str, Any]:
    stats = await app.state.skill_library.get_stats()
    improvement_rate = app.state.task_evaluator.compute_improvement_rate(stats.recent_scores, stats.older_scores)
    return {
        "total_skills": stats.total_skills,
        "total_tasks_recorded": stats.total_tasks_recorded,
        "avg_task_score": stats.avg_task_score,
        "improvement_rate": improvement_rate,
        "lora_training_runs": app.state.lora_trainer.training_runs,
        "last_training_ts": app.state.lora_trainer.last_training_ts,
        "model_version": MODEL_VERSION,
    }


@app.post("/learn/train/schedule")
async def learn_train_schedule() -> dict[str, str]:
    job_id = await app.state.lora_trainer.schedule()
    status = await app.state.lora_trainer.get_status(job_id)
    return {"job_id": job_id, "status": status["status"]}


@app.get("/learn/train/status/{job_id}")
async def learn_train_status(job_id: str) -> dict[str, Any]:
    return await app.state.lora_trainer.get_status(job_id)


@app.delete("/learn/skills/{skill_id}")
async def learn_delete_skill(skill_id: str) -> dict[str, bool]:
    deleted = await app.state.skill_library.delete_skill(skill_id)
    return {"deleted": deleted}


@app.get("/health")
async def health() -> dict[str, Any]:
    stats = await app.state.skill_library.get_stats()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": VERSION,
        "skills_count": stats.total_skills,
    }
