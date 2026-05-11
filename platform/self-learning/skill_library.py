"""SQLite skill store and retrieval for Phase 35 self-learning."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import numpy as np

from embedding_engine import EmbeddingEngine
from task_evaluator import TaskRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Skill:
    skill_id: str
    description: str
    action_sequence: list[dict[str, Any]]
    outcome: str
    score: float
    use_count: int
    created_ts: str
    last_used_ts: str
    embedding_preview: str


@dataclass
class SkillMatch:
    skill_id: str
    description: str
    similarity: float
    action_sequence: list[dict[str, Any]]
    avg_score: float


@dataclass
class LibraryStats:
    total_skills: int
    total_tasks_recorded: int
    avg_task_score: float
    recent_scores: list[float]
    older_scores: list[float]


class SkillLibrary:
    def __init__(self, db_path: Path, embedding_engine: EmbeddingEngine) -> None:
        self.db_path = db_path
        self.embedding_engine = embedding_engine

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY,
                    task_description TEXT NOT NULL,
                    action_sequence TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    outcome TEXT NOT NULL,
                    score REAL NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    created_ts TEXT NOT NULL,
                    last_used_ts TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_records (
                    record_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    score REAL NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    model_used TEXT NOT NULL,
                    user_rating INTEGER,
                    skill_id TEXT,
                    recorded_ts TEXT NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY(skill_id) REFERENCES skills(skill_id)
                );
                """
            )
            await db.commit()

    async def store_skill(
        self,
        description: str,
        action_sequence: list[dict[str, Any]],
        embedding: np.ndarray,
        score: float,
        outcome: str,
    ) -> str:
        skill_id = str(uuid.uuid4())
        ts = _utc_now()
        blob = self.embedding_engine.serialize(embedding)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO skills
                (skill_id, task_description, action_sequence, embedding, outcome, score, use_count, created_ts, last_used_ts)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    skill_id,
                    description,
                    json.dumps(action_sequence),
                    blob,
                    outcome,
                    float(score),
                    ts,
                    ts,
                ),
            )
            await db.commit()
        return skill_id

    async def retrieve_similar(self, query_embedding: np.ndarray, top_k: int = 3) -> list[SkillMatch]:
        rows: list[tuple[Any, ...]] = []
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT skill_id, task_description, action_sequence, embedding, score FROM skills"
            )
            rows = await cur.fetchall()
            await cur.close()

        matches: list[SkillMatch] = []
        for skill_id, desc, action_json, emb_blob, score in rows:
            emb = self.embedding_engine.deserialize(emb_blob)
            sim = self.embedding_engine.cosine_similarity(query_embedding, emb)
            matches.append(
                SkillMatch(
                    skill_id=skill_id,
                    description=desc,
                    similarity=float(sim),
                    action_sequence=json.loads(action_json),
                    avg_score=float(score),
                )
            )

        matches.sort(key=lambda m: m.similarity, reverse=True)
        selected = matches[: max(1, top_k)]

        # Track usage of selected skills.
        ts = _utc_now()
        async with aiosqlite.connect(self.db_path) as db:
            for m in selected:
                await db.execute(
                    "UPDATE skills SET use_count = use_count + 1, last_used_ts = ? WHERE skill_id = ?",
                    (ts, m.skill_id),
                )
            await db.commit()

        return selected

    async def record_task(self, task_record: TaskRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO task_records
                (record_id, task_id, task_description, outcome, score, duration_ms, model_used,
                 user_rating, skill_id, recorded_ts, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_record.record_id,
                    task_record.task_id,
                    task_record.task_description,
                    task_record.outcome,
                    float(task_record.score),
                    int(task_record.duration_ms),
                    task_record.model_used,
                    task_record.user_rating,
                    task_record.skill_id,
                    task_record.recorded_ts,
                    task_record.error_message,
                ),
            )
            await db.commit()

    async def get_all_skills(self) -> list[Skill]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT skill_id, task_description, action_sequence, outcome, score,
                       use_count, created_ts, last_used_ts, embedding
                FROM skills
                ORDER BY created_ts DESC
                """
            )
            rows = await cur.fetchall()
            await cur.close()

        out: list[Skill] = []
        for r in rows:
            emb_preview = self.embedding_engine.deserialize(r[8])[:6].tolist()
            out.append(
                Skill(
                    skill_id=r[0],
                    description=r[1],
                    action_sequence=json.loads(r[2]),
                    outcome=r[3],
                    score=float(r[4]),
                    use_count=int(r[5]),
                    created_ts=r[6],
                    last_used_ts=r[7],
                    embedding_preview=",".join(f"{x:.3f}" for x in emb_preview),
                )
            )
        return out

    async def delete_skill(self, skill_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("DELETE FROM skills WHERE skill_id = ?", (skill_id,))
            await db.commit()
            return cur.rowcount > 0

    async def get_stats(self) -> LibraryStats:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM skills")
            total_skills = (await cur.fetchone())[0]
            await cur.close()

            cur = await db.execute("SELECT COUNT(*), COALESCE(AVG(score), 0.0) FROM task_records")
            row = await cur.fetchone()
            await cur.close()
            total_tasks_recorded = int(row[0])
            avg_task_score = float(row[1])

            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

            cur = await db.execute("SELECT score FROM task_records WHERE recorded_ts >= ?", (cutoff,))
            recent = [float(r[0]) for r in await cur.fetchall()]
            await cur.close()

            cur = await db.execute("SELECT score FROM task_records WHERE recorded_ts < ?", (cutoff,))
            older = [float(r[0]) for r in await cur.fetchall()]
            await cur.close()

        return LibraryStats(
            total_skills=total_skills,
            total_tasks_recorded=total_tasks_recorded,
            avg_task_score=avg_task_score,
            recent_scores=recent,
            older_scores=older,
        )

    async def top_skills(self, limit: int = 100) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT skill_id, task_description, action_sequence, score, outcome FROM skills ORDER BY score DESC, use_count DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
            await cur.close()

        return [
            {
                "skill_id": r[0],
                "task_description": r[1],
                "action_sequence": json.loads(r[2]),
                "score": float(r[3]),
                "outcome": r[4],
            }
            for r in rows
        ]
