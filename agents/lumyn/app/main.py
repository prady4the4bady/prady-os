from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException

from .config import LumynConfig, load_config
from .learning import load_learnings, run_nightly_reflection
from .memory import LumynMemory
from .model_gateway import GatewayClient
from .react_loop import ReactEngine
from .schemas import (
    ChatRequest,
    ChatResponse,
    ExecuteRequest,
    MemorySearchRequest,
    SessionTurn,
)
from .session_store import SessionStore
from .tooling import LumynTools


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _workspace_root(base_dir: Path) -> Path:
    # /repo/agents/lumyn -> /repo
    return base_dir.parent.parent


def _build_system_context(learnings: list[str]) -> str:
    if not learnings:
        return "You are Lumyn, the primary Kryos assistant."
    bullets = "\n".join(f"- {s}" for s in learnings)
    return (
        "You are Lumyn, the primary Kryos assistant. Apply these learned strategies:\n"
        f"{bullets}"
    )


def _register_routes(
    app: FastAPI,
    *,
    cfg: LumynConfig,
    session_store: SessionStore,
    memory: LumynMemory | None,
    react: ReactEngine,
) -> None:
    @app.post("/chat", tags=["chat"])
    async def chat(req: ChatRequest) -> ChatResponse:
        session = session_store.get_or_create(req.session_id)
        history: list[tuple[str, str]] = []
        for turn in session.turns:
            history.append(("user", turn.user))
            history.append(("assistant", turn.assistant))

        memory_context: list[str] = []
        if memory is not None:
            memory_context = [m.content for m in memory.search(req.message, top_k=3)]

        result = await react.run(
            user_message=req.message,
            session_context=req.context,
            retrieved_memories=memory_context,
            prior_history=history,
        )
        result.session_id = req.session_id

        session_store.append_turn(
            req.session_id,
            SessionTurn(user=req.message, assistant=result.answer, status=result.status, trace=result.trace),
        )

        if memory is not None and result.status in {"completed", "max_iterations", "error"}:
            convo = f"User: {req.message}\nAssistant: {result.answer}"
            memory.add_conversation(
                session_id=req.session_id,
                content=convo,
                outcome=result.status,
            )

        return result

    @app.get("/sessions", tags=["sessions"])
    async def list_sessions() -> dict[str, Any]:
        return {"sessions": [s.model_dump(mode="json") for s in session_store.list_active()]}

    @app.delete(
        "/sessions/{session_id}",
        tags=["sessions"],
        responses={404: {"description": "Session not found"}},
    )
    async def delete_session(session_id: str) -> dict[str, Any]:
        deleted = session_store.delete(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
        return {"deleted": True, "session_id": session_id}

    @app.post(
        "/execute",
        tags=["tasks"],
        responses={502: {"description": "workflow-engine returned an error"}},
    )
    async def execute(req: ExecuteRequest) -> dict[str, Any]:
        payload = {
            "goal": req.goal,
            "priority": "normal",
            "metadata": {"source": "lumyn-agent", "auto_approve": req.auto_approve},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{cfg.workflow_engine_url.rstrip('/')}/tasks", json=payload)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=resp.text)
            return resp.json()

    @app.post("/memory/search", tags=["memory"])
    async def memory_search(req: MemorySearchRequest) -> dict[str, Any]:
        if memory is None:
            return {"results": []}
        hits = memory.search(req.query, top_k=req.top_k)
        return {"results": [h.model_dump(mode="json") for h in hits]}


def create_app(*, start_scheduler: bool = True) -> FastAPI:
    base_dir = _base_dir()
    cfg = load_config(base_dir)

    session_store = SessionStore()
    gateway = GatewayClient(cfg.model_gateway_url)
    tools = LumynTools(
        workflow_engine_url=cfg.workflow_engine_url,
        screen_agent_url=cfg.screen_agent_url,
        auto_approve_safe_actions=cfg.auto_approve_safe_actions,
        workspace_root=_workspace_root(base_dir),
    )

    memory = LumynMemory(cfg.chroma_path) if cfg.memory_enabled else None
    learnings = load_learnings(cfg.learnings_file) if cfg.learning_enabled else []

    react = ReactEngine(
        gateway=gateway,
        tools=tools,
        max_iterations=cfg.max_iterations,
        model_name=None,
        static_system_context=_build_system_context(learnings),
    )

    scheduler: AsyncIOScheduler | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        nonlocal scheduler
        if cfg.learning_enabled and start_scheduler:
            scheduler = AsyncIOScheduler(timezone="UTC")

            async def _nightly() -> None:
                await run_nightly_reflection(
                    sessions=session_store.sessions_since(24),
                    gateway=gateway,
                    learnings_file=cfg.learnings_file,
                )

            scheduler.add_job(_nightly, "cron", hour=3, minute=0)
            scheduler.start()

        yield

        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await tools.close()
        await gateway.close()

    app = FastAPI(
        title="Lumyn Agent",
        version="0.1.0",
        description="Primary conversational agent with ReAct loop, memory, and self-improvement.",
        lifespan=lifespan,
    )

    app.state.cfg = cfg
    app.state.session_store = session_store
    app.state.memory = memory
    app.state.react = react

    _register_routes(app, cfg=cfg, session_store=session_store, memory=memory, react=react)

    return app


app = create_app()
