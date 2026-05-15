"""Neila — NEILA autonomous background daemon for Prady OS.

Runs as a persistent async daemon below Prax. Handles:
- Retry queue for failed-but-retryable jobs (SQLite-backed)
- Stalled-task resurfacing
- Digest candidate generation
- Memory consolidation triggers
- Scheduled follow-up reminders
- Prax → Ahnis → Neila episodic memory loop
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.models import LoopMetrics, RetryEntry, RetryState, ScheduledAction
from app.persistence import NeilaStore

VERSION = "1.1.0"
SERVICE_NAME = "neila"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

TICK_INTERVAL = int(os.getenv("NEILA_TICK_INTERVAL", "60"))
INVENTOR_URL = os.getenv("INVENTOR_ENGINE_URL", "http://inventor-engine:8022")
AUDIT_URL = os.getenv("AUDIT_LOG_URL", "http://audit-log:8112")
NOTIFY_URL = os.getenv("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
SELF_LEARN_URL = os.getenv("SELF_LEARNING_URL", "http://self-learning:8018")
AHNIS_URL = os.getenv("AHNIS_URL", "http://ahnis:8091")
MODEL_URL = os.getenv("MODEL_GATEWAY_URL", "http://model-gateway:11430")

HTTP_TIMEOUT = float(os.getenv("NEILA_HTTP_TIMEOUT", "10.0"))


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class EnqueueRequest(BaseModel):
    task_type: str
    target_url: str
    payload: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 3


class EnqueueResponse(BaseModel):
    status: str
    entry_id: str


class QueueEntryResponse(BaseModel):
    id: str
    task_type: str
    state: str
    attempt: int
    max_retries: int
    last_error: str = ""


class ScheduleRequest(BaseModel):
    action_type: str
    target_url: str
    payload: dict[str, Any] = Field(default_factory=dict)
    delay_minutes: int = 0


class ScheduleResponse(BaseModel):
    status: str
    action_id: str


class ScheduledEntryResponse(BaseModel):
    id: str
    action_type: str
    due_ts: str
    completed: bool


class NeilaStatusResponse(BaseModel):
    paused: bool
    loop_active: bool
    metrics: dict[str, Any] = Field(default_factory=dict)


class MetricsResponse(BaseModel):
    cycles_total: int = 0
    last_cycle_ts: str = ""
    tasks_scanned_total: int = 0
    actions_triggered_total: int = 0
    actions_deferred_total: int = 0
    retry_queue_depth: int = 0
    scheduled_pending: int = 0
    digests_generated_total: int = 0
    failures_total: int = 0
    followups_generated_total: int = 0
    deadletter_count: int = 0
    replay_count_total: int = 0
    last_deadletter_ts: str = ""
    paused: bool = False
    uptime_seconds: float = 0.0


class FollowupCandidateResponse(BaseModel):
    id: str
    source: str = ""
    title: str = ""
    body: str = ""
    severity: str = "info"
    created_ts: str = ""
    processed: bool = False


class DigestCandidateResponse(BaseModel):
    id: str
    source: str = ""
    summary: str = ""
    cycle: int = 0
    created_ts: str = ""
    processed: bool = False


class FollowupRequest(BaseModel):
    source: str = "neila"
    title: str = ""
    body: str = ""
    severity: str = "info"
    ahnis_query: str = ""


class DeadletterEntryResponse(BaseModel):
    id: str
    source_retry_id: str = ""
    task_type: str = ""
    target_url: str = ""
    last_error: str = ""
    failed_at: str = ""
    replay_count: int = 0


class ReplayResponse(BaseModel):
    status: str
    entry_id: str
    replay_count: int


class AuditEvent(BaseModel):
    event_type: str
    source: str = "neila"
    correlation_id: str = ""
    status: str = "success"
    detail: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

metrics = LoopMetrics()
_paused = False
_loop_task: asyncio.Task | None = None
_uptime_start = time.time()
_replay_count_total = 0
_last_deadletter_ts = ""

store = NeilaStore()

# Restore persisted state
_retry_queue, _scheduled_actions = store.restore()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _audit(event_type: str, detail: dict[str, Any], correlation_id: str = "", status: str = "success") -> None:
    try:
        event = AuditEvent(
            event_type=event_type,
            source="neila",
            correlation_id=correlation_id or str(uuid.uuid4()),
            status=status,
            detail=detail,
        )
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            await c.post(f"{AUDIT_URL}/events", json=event.model_dump())
    except Exception:
        pass


async def _http_post(url: str, json_data: dict | None = None) -> httpx.Response | None:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            return await c.post(url, json=json_data or {})
    except Exception as e:
        logger.debug("HTTP POST %s: %s", url, e)
        return None


async def _http_get(url: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("HTTP GET %s: %s", url, e)
    return None


async def _read_ahnis_summaries() -> list[str]:
    """Pull recent summaries from Ahnis for context-aware follow-ups."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            resp = await c.post(
                f"{AHNIS_URL}/memory/search",
                json={"query": "", "category": "summary", "limit": 5},
            )
            if resp.status_code == 200:
                data = resp.json()
                return [r.get("content", "") for r in data.get("results", [])]
    except Exception as e:
        logger.debug("Ahnis summaries read: %s", e)
    return []


async def _read_ahnis_unresolved() -> list[dict[str, Any]]:
    """Pull items from Ahnis that may need follow-up."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            resp = await c.post(
                f"{AHNIS_URL}/memory/search",
                json={"query": "failure lesson unresolved stalled", "limit": 5},
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
    except Exception as e:
        logger.debug("Ahnis unresolved read: %s", e)
    return []


async def _write_to_ahnis(category: str, content: str, metadata: dict[str, Any] | None = None) -> None:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
            await c.post(
                f"{AHNIS_URL}/memory/write",
                json={
                    "category": category,
                    "content": content,
                    "metadata": metadata or {},
                },
            )
    except Exception as e:
        logger.debug("Ahnis write failed: %s", e)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop_task
    _loop_task = asyncio.create_task(_NEILA_loop())
    logger.info(
        "Neila started with %d persisted retries, %d pending schedules",
        len(_retry_queue), len(_scheduled_actions),
    )
    await _audit("neila_startup", {
        "retries_restored": len(_retry_queue),
        "schedules_restored": len(_scheduled_actions),
        "tick_interval": TICK_INTERVAL,
    })
    yield
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
        try:
            await _loop_task
        except asyncio.CancelledError:
            pass
    store.close()


app = FastAPI(title="Prady OS Neila — NEILA Daemon", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def _NEILA_loop():
    backoff = TICK_INTERVAL
    while True:
        try:
            if _paused:
                await asyncio.sleep(TICK_INTERVAL)
                continue
            metrics.cycle_count += 1
            metrics.last_cycle_ts = _utc_now()
            cycle_start = time.perf_counter()

            # 1. Scan inventor-engine proposals
            data = await _http_get(f"{INVENTOR_URL}/inventor/proposals")
            proposals = data if isinstance(data, list) else []
            metrics.tasks_scanned = len(proposals)
            if proposals:
                logger.info("Neila: %d pending proposals found", len(proposals))

            # 2. Process retry queue (from SQLite)
            pending = [e for e in _retry_queue if e.state == RetryState.PENDING]
            metrics.retry_queue_depth = len(pending)
            now = _utc_now()
            for entry in pending:
                if entry.next_attempt_ts and entry.next_attempt_ts > now:
                    continue
                entry.state = RetryState.RUNNING
                entry.attempt += 1
                try:
                    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as c:
                        resp = await c.post(entry.target_url, json=entry.payload)
                    if resp.status_code < 500:
                        entry.state = RetryState.FAILED
                        _retry_queue.remove(entry)
                        store.dequeue(entry.id)
                        metrics.actions_triggered += 1
                    else:
                        raise IOError(f"HTTP {resp.status_code}")
                except Exception as e:
                    entry.last_error = str(e)
                    if entry.attempt >= entry.max_retries:
                        global _last_deadletter_ts
                        entry.state = RetryState.EXHAUSTED
                        store.update(entry)
                        store.dequeue(entry.id)
                        _retry_queue.remove(entry)
                        store.add_deadletter(entry.id, entry.task_type, entry.target_url, entry.payload, str(e))
                        _last_deadletter_ts = _utc_now()
                        await _audit("deadletter_created", {
                            "source_retry_id": entry.id, "task_type": entry.task_type,
                            "error": str(e)[:200],
                        })
                        logger.warning("Retry exhausted for %s/%s: moved to dead-letter", entry.task_type, entry.id)
                    else:
                        entry.state = RetryState.PENDING
                        backoff_sec = min(60 * (2 ** (entry.attempt - 1)), 3600)
                        entry.next_attempt_ts = (datetime.now(timezone.utc) + timedelta(seconds=backoff_sec)).isoformat()
                        store.update(entry)
                        metrics.actions_deferred += 1

            # 3. Process scheduled actions
            now_dt = datetime.now(timezone.utc)
            for action in list(_scheduled_actions):
                if action.completed:
                    continue
                if action.due_ts and action.due_ts <= _utc_now():
                    result = await _http_post(action.target_url, action.payload)
                    action.completed = True
                    action.trigger_ts = _utc_now()
                    store.update_schedule(action)
                    metrics.actions_triggered += 1
                    await _audit("scheduled_action_triggered", {"action_type": action.action_type, "id": action.id})
            metrics.scheduled_count = len([a for a in _scheduled_actions if not a.completed])

            # 4. Memory consolidation via Ahnis
            await _http_post(f"{AHNIS_URL}/memory/consolidate")

            # 5. Digest candidate generation (every 10 cycles)
            if metrics.cycle_count % 10 == 0:
                digest = await _http_get(f"{INVENTOR_URL}/inventor/digest")
                if digest:
                    summary_text = digest.get("honest_summary", "")[:500]
                    did = store.add_digest("neila", summary_text, metrics.cycle_count)
                    metrics.digests_generated += 1
                    await _http_post(f"{NOTIFY_URL}/notify", {
                        "title": "Prax Digest Snapshot",
                        "body": f"Cycle {metrics.cycle_count}: {summary_text[:200]}",
                        "severity": "info", "source": "neila",
                    })
                    await _audit("digest_generated", {"cycle": metrics.cycle_count, "digest_id": did, "summary": summary_text[:200]})

            # 6. Prax → Ahnis → Neila follow-up loop
            if metrics.cycle_count % 5 == 0:
                summaries = await _read_ahnis_summaries()
                unresolved = await _read_ahnis_unresolved()
                if summaries:
                    combined = " | ".join(summaries[:3])
                    followup_body = f"Ahnis summaries: {combined[:300]}"
                    if unresolved:
                        followup_body += f" | Unresolved: {len(unresolved)} items"
                    store.add_followup("neila", f"Cycle {metrics.cycle_count} follow-up", followup_body)
                    metrics.followups_generated += 1
                if unresolved:
                    for item in unresolved[:3]:
                        content = item.get("content", "")[:200]
                        store.add_followup("ahnis", "Unresolved item requires attention", content, severity="warning")

            # 7. Stalled-task resurfacing
            for p in proposals:
                created = p.get("created_ts", "")
                if created and created < (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat():
                    await _http_post(f"{NOTIFY_URL}/notify", {
                        "title": "Stalled Proposal Resurfaced",
                        "body": f"Proposal {p.get('proposal_id', '')} has been pending >24h",
                        "severity": "info", "source": "neila",
                    })
                    break

            # 8. Log cycle to audit
            cycle_ms = int((time.perf_counter() - cycle_start) * 1000)
            await _audit("neila_cycle", {
                "cycle": metrics.cycle_count, "duration_ms": cycle_ms,
                "proposals_found": len(proposals),
            })

            backoff = TICK_INTERVAL
            await asyncio.sleep(TICK_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            metrics.failures += 1
            logger.error("NEILA loop error: %s", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, TICK_INTERVAL * 16)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=VERSION)


@app.get("/neila/status", response_model=NeilaStatusResponse)
async def neila_status() -> NeilaStatusResponse:
    return NeilaStatusResponse(
        paused=_paused,
        loop_active=_loop_task is not None and not _loop_task.done(),
        metrics={
            "cycle_count": metrics.cycle_count,
            "last_cycle_ts": metrics.last_cycle_ts,
            "tasks_scanned": metrics.tasks_scanned,
            "actions_triggered": metrics.actions_triggered,
            "actions_deferred": metrics.actions_deferred,
            "retry_queue_depth": metrics.retry_queue_depth,
            "scheduled_count": metrics.scheduled_count,
            "digests_generated": metrics.digests_generated,
            "followups_generated": metrics.followups_generated,
            "failures": metrics.failures,
        },
    )


@app.get("/neila/metrics", response_model=MetricsResponse)
async def neila_metrics() -> MetricsResponse:
    return MetricsResponse(
        cycles_total=metrics.cycle_count,
        last_cycle_ts=metrics.last_cycle_ts,
        tasks_scanned_total=metrics.tasks_scanned,
        actions_triggered_total=metrics.actions_triggered,
        actions_deferred_total=metrics.actions_deferred,
        retry_queue_depth=store.retry_count(),
        scheduled_pending=store.scheduled_count(),
        digests_generated_total=metrics.digests_generated,
        failures_total=metrics.failures,
        followups_generated_total=metrics.followups_generated,
        deadletter_count=store.deadletter_count(),
        replay_count_total=_replay_count_total,
        last_deadletter_ts=_last_deadletter_ts,
        paused=_paused,
        uptime_seconds=time.time() - _uptime_start,
    )


@app.post("/neila/pause")
async def neila_pause() -> dict[str, str]:
    global _paused
    _paused = True
    logger.info("Neila paused")
    await _audit("neila_paused", {})
    return {"status": "paused"}


@app.post("/neila/resume")
async def neila_resume() -> dict[str, str]:
    global _paused
    _paused = False
    logger.info("Neila resumed")
    await _audit("neila_resumed", {})
    return {"status": "resumed"}


@app.post("/neila/enqueue", response_model=EnqueueResponse)
async def neila_enqueue(req: EnqueueRequest) -> EnqueueResponse:
    entry = RetryEntry(
        id=str(uuid.uuid4()),
        task_type=req.task_type,
        target_url=req.target_url,
        payload=req.payload,
        max_retries=max(1, req.max_retries),
        created_ts=_utc_now(),
    )
    _retry_queue.append(entry)
    store.enqueue(entry)
    await _audit("enqueued", {"task_type": req.task_type, "id": entry.id})
    return EnqueueResponse(status="enqueued", entry_id=entry.id)


@app.get("/neila/queue", response_model=list[QueueEntryResponse])
async def neila_queue() -> list[QueueEntryResponse]:
    return [
        QueueEntryResponse(
            id=e.id, task_type=e.task_type, state=e.state.value,
            attempt=e.attempt, max_retries=e.max_retries, last_error=e.last_error,
        )
        for e in _retry_queue
    ]


@app.post("/neila/schedule", response_model=ScheduleResponse)
async def neila_schedule(req: ScheduleRequest) -> ScheduleResponse:
    due = (datetime.now(timezone.utc) + timedelta(minutes=max(0, req.delay_minutes))).isoformat()
    action = ScheduledAction(
        id=str(uuid.uuid4()), action_type=req.action_type,
        target_url=req.target_url, payload=req.payload, due_ts=due,
    )
    _scheduled_actions.append(action)
    store.add_schedule(action)
    await _audit("scheduled", {"action_type": req.action_type, "id": action.id})
    return ScheduleResponse(status="scheduled", action_id=action.id)


@app.get("/neila/scheduled", response_model=list[ScheduledEntryResponse])
async def neila_scheduled() -> list[ScheduledEntryResponse]:
    return [
        ScheduledEntryResponse(id=a.id, action_type=a.action_type, due_ts=a.due_ts, completed=a.completed)
        for a in _scheduled_actions if not a.completed
    ]


# ---------------------------------------------------------------------------
# Dead-letter queue
# ---------------------------------------------------------------------------


@app.get("/neila/deadletters", response_model=list[DeadletterEntryResponse])
async def neila_deadletters(limit: int = 50) -> list[DeadletterEntryResponse]:
    items = store.list_deadletters(limit)
    return [
        DeadletterEntryResponse(
            id=it["id"], source_retry_id=it["source_retry_id"],
            task_type=it["task_type"], target_url=it["target_url"],
            last_error=it["last_error"], failed_at=it["failed_at"],
            replay_count=it["replay_count"],
        )
        for it in items
    ]


@app.post("/neila/deadletters/{deadletter_id}/replay", response_model=ReplayResponse)
async def neila_deadletter_replay(deadletter_id: str) -> ReplayResponse:
    global _replay_count_total
    dl = store.get_deadletter(deadletter_id)
    if dl is None:
        raise HTTPException(404, f"Deadletter {deadletter_id} not found")
    import json
    payload = json.loads(dl["payload_json"]) if dl["payload_json"] else {}
    entry = RetryEntry(
        id=str(uuid.uuid4()),
        task_type=dl["task_type"],
        target_url=dl["target_url"],
        payload=payload,
        max_retries=3,
        attempt=0,
        created_ts=_utc_now(),
    )
    _retry_queue.append(entry)
    store.enqueue(entry)
    store.increment_replay(deadletter_id)
    _replay_count_total += 1
    await _audit("deadletter_replayed", {
        "deadletter_id": deadletter_id, "new_entry_id": entry.id,
        "task_type": dl["task_type"],
    })
    dl_updated = store.get_deadletter(deadletter_id)
    replay_count = dl_updated["replay_count"] if dl_updated else 0
    return ReplayResponse(status="replayed", entry_id=entry.id, replay_count=replay_count)


@app.delete("/neila/deadletters/{deadletter_id}")
async def neila_deadletter_delete(deadletter_id: str) -> dict[str, str]:
    if store.delete_deadletter(deadletter_id):
        await _audit("deadletter_deleted", {"deadletter_id": deadletter_id})
        return {"status": "deleted"}
    raise HTTPException(404, f"Deadletter {deadletter_id} not found")


# ---------------------------------------------------------------------------
# Follow-up candidates
# ---------------------------------------------------------------------------


@app.post("/neila/followup", response_model=dict[str, str])
async def neila_followup(req: FollowupRequest) -> dict[str, str]:
    """Create a follow-up candidate (used by Prax → Ahnis → Neila loop)."""
    fid = store.add_followup(req.source, req.title, req.body, req.severity)
    await _audit("followup_created", {"id": fid, "source": req.source, "title": req.title})
    return {"status": "created", "followup_id": fid}


@app.get("/neila/followups", response_model=list[FollowupCandidateResponse])
async def neila_followups(limit: int = 20) -> list[FollowupCandidateResponse]:
    items = store.list_followups(limit)
    return [
        FollowupCandidateResponse(
            id=it["id"], source=it["source"], title=it["title"],
            body=it["body"], severity=it["severity"],
            created_ts=it["created_ts"], processed=bool(it["processed"]),
        )
        for it in items
    ]


@app.post("/neila/followups/{fid}/processed")
async def neila_followup_processed(fid: str) -> dict[str, str]:
    store.mark_followup_processed(fid)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Digest candidates
# ---------------------------------------------------------------------------


@app.get("/neila/digests", response_model=list[DigestCandidateResponse])
async def neila_digests(limit: int = 10) -> list[DigestCandidateResponse]:
    items = store.list_digests(limit)
    return [
        DigestCandidateResponse(
            id=it["id"], source=it["source"], summary=it["summary"],
            cycle=it["cycle"], created_ts=it["created_ts"],
            processed=bool(it["processed"]),
        )
        for it in items
    ]
