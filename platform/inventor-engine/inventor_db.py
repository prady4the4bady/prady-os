from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

DB_PATH = "/data/inventor/inventor.db"


class InventorDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS problems (
                    problem_id   TEXT PRIMARY KEY,
                    title        TEXT NOT NULL,
                    description  TEXT,
                    source_url   TEXT,
                    scores       TEXT,
                    tags         TEXT,
                    status       TEXT DEFAULT 'discovered',
                    discovered_ts TEXT NOT NULL
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id       TEXT PRIMARY KEY,
                    problem_id        TEXT,
                    problem_summary   TEXT NOT NULL,
                    why_it_matters    TEXT,
                    what_to_build     TEXT,
                    tools             TEXT,
                    time_estimate_hrs INTEGER,
                    deliverables      TEXT,
                    confidence_level  TEXT,
                    honest_caveats    TEXT,
                    status TEXT DEFAULT 'pending',
                    created_ts        TEXT NOT NULL,
                    decided_ts        TEXT,
                    FOREIGN KEY (problem_id) REFERENCES problems(problem_id)
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id      TEXT PRIMARY KEY,
                    proposal_id     TEXT,
                    name            TEXT NOT NULL,
                    status          TEXT DEFAULT 'building',
                    current_agent   TEXT,
                    workspace_path  TEXT,
                    repo_url        TEXT,
                    test_pass_rate  REAL DEFAULT 0.0,
                    verified        INTEGER DEFAULT 0,
                    build_started   TEXT,
                    build_completed TEXT,
                    failure_details TEXT,
                    steps_log       TEXT,
                    FOREIGN KEY (proposal_id) REFERENCES proposals(proposal_id)
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_steps (
                    step_id     TEXT PRIMARY KEY,
                    project_id  TEXT NOT NULL,
                    agent_name  TEXT NOT NULL,
                    status      TEXT DEFAULT 'running',
                    output      TEXT,
                    started_ts  TEXT NOT NULL,
                    completed_ts TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                )""")
            await db.commit()

    async def save_proposal(self, card) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO proposals
                (proposal_id, problem_summary, why_it_matters,
                 what_to_build, tools, time_estimate_hrs,
                 deliverables, confidence_level, honest_caveats,
                 status, created_ts)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                card.proposal_id,
                card.problem_summary,
                card.why_it_matters,
                card.what_to_build,
                json.dumps(card.tools),
                card.time_estimate_hours,
                json.dumps(card.deliverables),
                card.confidence_level,
                json.dumps(card.honest_caveats),
                "pending",
                card.created_ts
            ))
            await db.commit()

    async def get_pending_proposals(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM proposals
                WHERE status = 'pending'
                ORDER BY created_ts DESC""") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def approve_proposal(self, proposal_id: str, project_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE proposals
                SET status='approved', decided_ts=?
                WHERE proposal_id=?""", (
                datetime.now(timezone.utc).isoformat(),
                proposal_id))
            await db.execute("""
                INSERT INTO projects
                (project_id, proposal_id, name, status,
                 build_started, steps_log)
                VALUES (?,?,?,?,?,?)""", (
                project_id,
                proposal_id,
                f"project-{project_id[:8]}",
                "building",
                datetime.now(timezone.utc).isoformat(),
                json.dumps([])
            ))
            await db.commit()

    async def reject_proposal(self, proposal_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE proposals
                SET status='rejected', decided_ts=?
                WHERE proposal_id=?""", (
                datetime.now(timezone.utc).isoformat(),
                proposal_id))
            await db.commit()

    async def update_project_status(self, project_id: str, status: str, current_agent: str = None, test_pass_rate: float = None, verified: bool = None, failure_details: list = None, repo_url: str = None) -> None:
        fields = ["status=?"]
        values = [status]
        if current_agent is not None:
            fields.append("current_agent=?")
            values.append(current_agent)
        if test_pass_rate is not None:
            fields.append("test_pass_rate=?")
            values.append(test_pass_rate)
        if verified is not None:
            fields.append("verified=?")
            values.append(1 if verified else 0)
        if failure_details is not None:
            fields.append("failure_details=?")
            values.append(json.dumps(failure_details))
        if repo_url is not None:
            fields.append("repo_url=?")
            values.append(repo_url)
        if status in ("completed", "failed", "verified"):
            fields.append("build_completed=?")
            values.append(datetime.now(timezone.utc).isoformat())
        values.append(project_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE projects SET {', '.join(fields)} WHERE project_id=?", values)
            await db.commit()

    async def get_project(self, project_id: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_all_projects(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM projects ORDER BY build_started DESC") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def log_agent_step(self, project_id: str, agent_name: str, status: str, output: str = None) -> str:
        step_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO agent_steps
                (step_id, project_id, agent_name, status, output, started_ts)
                VALUES (?,?,?,?,?,?)""", (
                step_id, project_id, agent_name, status, output,
                datetime.now(timezone.utc).isoformat()))
            await db.commit()
        return step_id
