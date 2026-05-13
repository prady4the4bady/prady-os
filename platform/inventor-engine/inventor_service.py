"""Prady OS — Inventor Engine (Phase 39)
Port 8022 — Prax autonomous project discovery and building service."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from build_team import BuildTeam
from inventor_db import InventorDB
from project_releaser import ProjectReleaser
from proposal_engine import ProposalCard, ProposalEngine
from research_agent import ResearchAgent
from verifier_agent import VerifierAgent

VERSION = "1.0.0"
SERVICE_NAME = "inventor-engine"

SCAN_INTERVAL_HOURS = int(os.getenv("SCAN_INTERVAL_HOURS", "6"))
MIN_PROBLEM_SCORE = float(os.getenv("MIN_PROBLEM_SCORE", "0.6"))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class InventorState:
    def __init__(self):
        self.loop_active = False
        self.current_phase = "idle"
        self.active_project: dict | None = None
        self.completed_projects: int = 0
        self.pending_proposal: dict | None = None
        self.last_scan_ts: str = ""
        self._loop_task: asyncio.Task | None = None
        self.db: InventorDB | None = None


state = InventorState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.db = InventorDB()
    await state.db.init()
    yield
    state.loop_active = False
    if state._loop_task and not state._loop_task.done():
        state._loop_task.cancel()
        try:
            await state._loop_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Prady OS Inventor Engine", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def inventor_loop():
    """Background loop: research -> propose -> wait for approval -> build -> verify -> release."""
    research_agent = ResearchAgent()
    proposal_engine = ProposalEngine()

    while state.loop_active:
        try:
            state.current_phase = "researching"

            problems = await research_agent.scan()

            novel_problems = []
            for problem in problems:
                if await research_agent.verify_novelty(problem):
                    novel_problems.append(problem)

            if not novel_problems:
                state.current_phase = "idle"
                await asyncio.sleep(SCAN_INTERVAL_HOURS * 3600)
                continue

            state.current_phase = "proposing"
            problem = novel_problems[0]

            research = await research_agent.deep_research(problem)
            proposal = await proposal_engine.generate(research)

            await state.db.save_proposal(proposal)
            state.last_scan_ts = datetime.now(timezone.utc).isoformat()

            state.current_phase = "awaiting_approval"
            state.pending_proposal = {
                "proposal_id": proposal.proposal_id,
                "problem_summary": proposal.problem_summary,
                "created_ts": proposal.created_ts,
            }

            polling_cycles = 0
            max_poll_cycles = (SCAN_INTERVAL_HOURS * 3600) // 30
            while state.loop_active and polling_cycles < max_poll_cycles:
                pending = await state.db.get_pending_proposals()
                approved = [p for p in pending if p["status"] == "approved"]

                rejected_proposals = [p for p in pending if p["status"] == "rejected" and p["proposal_id"] == proposal.proposal_id]
                if rejected_proposals:
                    state.pending_proposal = None
                    break

                if approved:
                    approved_proposal = approved[0]
                    state.pending_proposal = None
                    await _build_and_verify(approved_proposal)
                    break

                await asyncio.sleep(30)
                polling_cycles += 1

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("inventor_loop error: %s", e)
            await asyncio.sleep(60)

    state.current_phase = "idle"


async def _build_and_verify(proposal_data: dict):
    """Build a project and verify it."""
    project_id = str(uuid.uuid4())
    proposal_card = ProposalCard(
        proposal_id=proposal_data["proposal_id"],
        problem_summary=proposal_data["problem_summary"],
        why_it_matters=proposal_data.get("why_it_matters", ""),
        what_to_build=proposal_data.get("what_to_build", ""),
        tools=proposal_data.get("tools", []),
        time_estimate_hours=proposal_data.get("time_estimate_hrs", 8),
        deliverables=proposal_data.get("deliverables", []),
        confidence_level=proposal_data.get("confidence_level", "medium"),
        honest_caveats=proposal_data.get("honest_caveats", []),
        created_ts=proposal_data.get("created_ts", datetime.now(timezone.utc).isoformat()),
    )

    state.current_phase = "building"
    state.active_project = {"project_id": project_id, "status": "building"}

    await state.db.approve_proposal(proposal_card.proposal_id, project_id)

    build_team = BuildTeam()
    await state.db.log_agent_step(project_id, "architect", "running")
    result = await build_team.build(proposal_card, project_id)
    await state.db.log_agent_step(project_id, "architect", "completed", result.arch_output.output if result.arch_output else "")

    state.current_phase = "verifying"
    await state.db.update_project_status(project_id, "verifying", current_agent="verifier")

    verifier = VerifierAgent()
    verification = await verifier.verify(result, proposal_card)

    await state.db.update_project_status(
        project_id,
        status="completed" if verification.verified else "failed",
        current_agent="verifier",
        test_pass_rate=verification.test_pass_rate,
        verified=verification.verified,
        failure_details=verification.failure_details,
    )

    if verification.verified:
        state.current_phase = "releasing"
        releaser = ProjectReleaser()
        project = await state.db.get_project(project_id)
        if project:
            release_result = await releaser.release(project)
            await state.db.update_project_status(project_id, "released", repo_url=release_result.urls.get("github"))
            if release_result.urls.get("github"):
                await state.db.update_project_status(project_id, "released", repo_url=release_result.urls["github"])
        state.completed_projects += 1

    state.active_project = None
    state.current_phase = "idle"


@app.get("/inventor/status")
async def inventor_status() -> dict[str, Any]:
    return {
        "loop_active": state.loop_active,
        "current_phase": state.current_phase,
        "active_project": state.active_project,
        "completed_projects": state.completed_projects,
        "pending_proposal": state.pending_proposal,
        "last_scan_ts": state.last_scan_ts,
    }


@app.post("/inventor/start")
async def inventor_start() -> dict[str, str]:
    if state.loop_active:
        return {"status": "already_running"}
    state.loop_active = True
    state._loop_task = asyncio.create_task(inventor_loop())
    return {"status": "started"}


@app.post("/inventor/stop")
async def inventor_stop() -> dict[str, str]:
    if not state.loop_active:
        return {"status": "already_stopped"}
    state.loop_active = False
    if state._loop_task and not state._loop_task.done():
        state._loop_task.cancel()
    return {"status": "stopped"}


@app.get("/inventor/proposals")
async def inventor_proposals() -> list[dict[str, Any]]:
    return await state.db.get_pending_proposals()


@app.post("/inventor/proposals/{proposal_id}/approve")
async def inventor_approve(proposal_id: str) -> dict[str, Any]:
    proposals = await state.db.get_pending_proposals()
    proposal = next((p for p in proposals if p["proposal_id"] == proposal_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    project_id = str(uuid.uuid4())
    await state.db.approve_proposal(proposal_id, project_id)

    asyncio.create_task(_build_and_verify(proposal))

    return {"status": "building", "project_id": project_id}


@app.post("/inventor/proposals/{proposal_id}/reject")
async def inventor_reject(proposal_id: str) -> dict[str, str]:
    proposals = await state.db.get_pending_proposals()
    proposal = next((p for p in proposals if p["proposal_id"] == proposal_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    await state.db.reject_proposal(proposal_id)
    return {"status": "rejected"}


@app.get("/inventor/projects")
async def inventor_projects() -> list[dict[str, Any]]:
    return await state.db.get_all_projects()


@app.get("/inventor/projects/{project_id}/progress")
async def inventor_project_progress(project_id: str) -> dict[str, Any]:
    project = await state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    steps_log = project.get("steps_log", "[]")
    try:
        import json
        steps = json.loads(steps_log) if isinstance(steps_log, str) else steps_log
    except (json.JSONDecodeError, TypeError):
        steps = []

    return {
        "project_id": project["project_id"],
        "name": project["name"],
        "status": project["status"],
        "current_agent": project.get("current_agent", ""),
        "steps_completed": steps,
        "steps_remaining": [],
        "latest_commit": "",
        "test_results": {"passed": 0, "failed": 0},
        "verified": bool(project["verified"]),
        "eta_minutes": 0,
    }


@app.post("/inventor/projects/{project_id}/release")
async def release_project(project_id: str) -> dict[str, Any]:
    project = await state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project["verified"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot release unverified project. Prax does not release what it cannot confirm works.",
        )
    releaser = ProjectReleaser()
    result = await releaser.release(project)
    return {"status": "released", "urls": result.urls}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}
