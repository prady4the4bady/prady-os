from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import (
    app,
    metrics,
    _retry_queue,
    _scheduled_actions,
    _paused,
    store,
    _replay_count_total,
)
from app.models import RetryEntry, RetryState, ScheduledAction
from app.persistence import NeilaStore


@pytest.fixture(autouse=True)
def reset():
    metrics.cycle_count = 0
    metrics.failures = 0
    metrics.actions_triggered = 0
    metrics.digests_generated = 0
    metrics.followups_generated = 0
    _retry_queue.clear()
    _scheduled_actions.clear()
    store.clear_retries()
    store.clear_schedules()
    store.clear_deadletters()
    global _paused, _replay_count_total
    _paused = False
    _replay_count_total = 0


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Existing tests (backward compatible) ---

@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["service"] == "neila"


@pytest.mark.asyncio
async def test_status_returns_metrics(client: AsyncClient):
    resp = await client.get("/neila/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "paused" in data
    assert "loop_active" in data
    assert "metrics" in data


@pytest.mark.asyncio
async def test_pause_resume(client: AsyncClient):
    resp = await client.post("/neila/pause")
    assert resp.json()["status"] == "paused"
    resp = await client.post("/neila/resume")
    assert resp.json()["status"] == "resumed"


@pytest.mark.asyncio
async def test_metrics_track_cycle(client: AsyncClient):
    metrics.cycle_count = 42
    resp = await client.get("/neila/status")
    assert resp.json()["metrics"]["cycle_count"] == 42


@pytest.mark.asyncio
async def test_enqueue_adds_to_queue(client: AsyncClient):
    resp = await client.post("/neila/enqueue", json={"task_type": "test", "target_url": "http://example.com/task", "payload": {"key": "val"}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "enqueued"
    assert len(_retry_queue) >= 1


@pytest.mark.asyncio
async def test_enqueue_rejects_no_target(client: AsyncClient):
    resp = await client.post("/neila/enqueue", json={"task_type": "test"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_queue_returns_list(client: AsyncClient):
    resp = await client.get("/neila/queue")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_schedule_adds_action(client: AsyncClient):
    resp = await client.post("/neila/schedule", json={"action_type": "digest", "target_url": "http://example.com/digest", "delay_minutes": 30})
    assert resp.status_code == 200
    assert resp.json()["status"] == "scheduled"


@pytest.mark.asyncio
async def test_scheduled_returns_list(client: AsyncClient):
    resp = await client.get("/neila/scheduled")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    metrics.cycle_count = 10
    resp = await client.get("/neila/metrics")
    assert resp.status_code == 200
    assert resp.json()["cycles_total"] == 10
    assert "last_cycle_ts" in resp.json()


# --- New tests: persistence across restart simulation ---

def test_store_enqueue_dequeue():
    s = NeilaStore(":memory:")
    s.clear_retries()
    entry = RetryEntry(
        id="test-id-1",
        task_type="test",
        target_url="http://example.com/task",
        payload={"key": "val"},
        max_retries=3,
        attempt=0,
        state=RetryState.PENDING,
        created_ts="2025-01-01T00:00:00Z",
    )
    s.enqueue(entry)
    assert s.retry_count() == 1
    s.dequeue("test-id-1")
    assert s.retry_count() == 0


def test_store_persistence_simulation(tmp_path):
    db_path = str(tmp_path / "test_neila.db")
    s = NeilaStore(db_path)
    s.clear_retries()
    entry = RetryEntry(
        id="persist-id",
        task_type="persist-test",
        target_url="http://example.com/retry",
        payload={"attempt": 2},
        max_retries=5,
        attempt=2,
        state=RetryState.PENDING,
        last_error="timeout",
        created_ts="2025-01-01T00:00:00Z",
        next_attempt_ts="2025-01-02T00:00:00Z",
    )
    s.enqueue(entry)
    s.close()

    # Simulate restart: create a new store instance pointing to same DB file
    s2 = NeilaStore(db_path)
    restored, _ = s2.restore()
    assert len(restored) >= 1
    found = [r for r in restored if r.id == "persist-id"]
    assert len(found) == 1
    assert found[0].task_type == "persist-test"
    assert found[0].attempt == 2
    assert found[0].state == RetryState.PENDING
    assert found[0].last_error == "timeout"
    assert found[0].next_attempt_ts == "2025-01-02T00:00:00Z"
    s2.close()


def test_schedule_persistence_simulation(tmp_path):
    db_path = str(tmp_path / "test_sched.db")
    s = NeilaStore(db_path)
    s.clear_schedules()
    action = ScheduledAction(
        id="sched-id",
        action_type="digest",
        target_url="http://example.com/digest",
        payload={"cycle": 5},
        due_ts="2025-01-03T00:00:00Z",
        completed=False,
    )
    s.add_schedule(action)
    s.close()

    # Simulate restart
    s2 = NeilaStore(db_path)
    _, restored = s2.restore()
    found = [a for a in restored if a.id == "sched-id"]
    assert len(found) == 1
    assert found[0].action_type == "digest"
    assert found[0].due_ts == "2025-01-03T00:00:00Z"
    assert not found[0].completed
    s2.close()


def test_backoff_preserved_after_restart(tmp_path):
    db_path = str(tmp_path / "test_backoff.db")
    s = NeilaStore(db_path)
    s.clear_retries()
    entry = RetryEntry(
        id="backoff-id",
        task_type="backoff-test",
        target_url="http://example.com/backoff",
        attempt=3,
        max_retries=5,
        state=RetryState.PENDING,
        last_error="connection refused",
        next_attempt_ts="2025-06-01T00:00:00Z",
        created_ts="2025-01-01T00:00:00Z",
    )
    s.enqueue(entry)
    s.close()

    s2 = NeilaStore(db_path)
    restored, _ = s2.restore()
    found = [r for r in restored if r.id == "backoff-id"]
    assert len(found) == 1
    assert found[0].attempt == 3
    assert found[0].max_retries == 5
    assert found[0].last_error == "connection refused"
    s2.close()


# --- New tests: follow-up and digest ---

@pytest.mark.asyncio
async def test_followup_endpoint(client: AsyncClient):
    resp = await client.post("/neila/followup", json={
        "source": "neila",
        "title": "test follow-up",
        "body": "this is a test follow-up item",
        "severity": "info",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"
    assert "followup_id" in resp.json()


@pytest.mark.asyncio
async def test_followups_list(client: AsyncClient):
    await client.post("/neila/followup", json={
        "source": "neila",
        "title": "list test",
        "body": "test body",
    })
    resp = await client.get("/neila/followups")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_followup_mark_processed(client: AsyncClient):
    create = await client.post("/neila/followup", json={
        "source": "neila",
        "title": "process test",
        "body": "will be processed",
    })
    fid = create.json()["followup_id"]
    resp = await client.post(f"/neila/followups/{fid}/processed")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_digests_list(client: AsyncClient):
    resp = await client.get("/neila/digests")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# --- New tests: enhanced responses ---

@pytest.mark.asyncio
async def test_enqueue_response_structured(client: AsyncClient):
    resp = await client.post("/neila/enqueue", json={"task_type": "test", "target_url": "http://example.com/task"})
    data = resp.json()
    assert "status" in data
    assert "entry_id" in data


@pytest.mark.asyncio
async def test_schedule_response_structured(client: AsyncClient):
    resp = await client.post("/neila/schedule", json={"action_type": "test", "target_url": "http://example.com/schedule"})
    data = resp.json()
    assert "status" in data
    assert "action_id" in data


@pytest.mark.asyncio
async def test_metrics_endpoint_detailed(client: AsyncClient):
    resp = await client.get("/neila/metrics")
    data = resp.json()
    assert "cycles_total" in data
    assert "scheduled_pending" in data
    assert "uptime_seconds" in data
    assert "paused" in data
    assert "deadletter_count" in data
    assert "replay_count_total" in data
    assert "last_deadletter_ts" in data


# --- New tests: dead-letter queue ---

def test_deadletter_add_and_list(tmp_path):
    db_path = str(tmp_path / "test_dl.db")
    s = NeilaStore(db_path)
    s.clear_deadletters()
    did = s.add_deadletter("retry-1", "test-task", "http://example.com/fail", {"key": "val"}, "connection timeout")
    assert did
    items = s.list_deadletters()
    assert len(items) == 1
    assert items[0]["source_retry_id"] == "retry-1"
    assert items[0]["task_type"] == "test-task"
    assert items[0]["last_error"] == "connection timeout"
    assert items[0]["replay_count"] == 0
    s.close()


def test_deadletter_delete(tmp_path):
    db_path = str(tmp_path / "test_dl_del.db")
    s = NeilaStore(db_path)
    s.clear_deadletters()
    did = s.add_deadletter("retry-2", "del-test", "http://example.com/del", {}, "gone")
    assert s.deadletter_count() == 1
    assert s.delete_deadletter(did)
    assert s.deadletter_count() == 0
    s.close()


def test_deadletter_replay_increment(tmp_path):
    db_path = str(tmp_path / "test_dl_replay.db")
    s = NeilaStore(db_path)
    s.clear_deadletters()
    did = s.add_deadletter("retry-3", "replay-test", "http://example.com/replay", {"x": 1}, "error")
    s.increment_replay(did)
    s.increment_replay(did)
    item = s.get_deadletter(did)
    assert item is not None
    assert item["replay_count"] == 2
    s.close()


def test_deadletter_get_nonexistent(tmp_path):
    db_path = str(tmp_path / "test_dl_get.db")
    s = NeilaStore(db_path)
    assert s.get_deadletter("nonexistent") is None
    s.close()


def test_deadletter_count_empty(tmp_path):
    db_path = str(tmp_path / "test_dl_empty.db")
    s = NeilaStore(db_path)
    s.clear_deadletters()
    assert s.deadletter_count() == 0
    s.close()


@pytest.mark.asyncio
async def test_deadletters_endpoint(client: AsyncClient):
    resp = await client.get("/neila/deadletters")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_deadletter_replay_endpoint(client: AsyncClient):
    did = store.add_deadletter("retry-api", "api-test", "http://example.com/api", {"val": 42}, "fail")
    resp = await client.post(f"/neila/deadletters/{did}/replay")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "replayed"
    assert "entry_id" in data
    assert data["replay_count"] >= 1


@pytest.mark.asyncio
async def test_deadletter_delete_endpoint(client: AsyncClient):
    did = store.add_deadletter("retry-del", "del-test", "http://example.com/del", {}, "removed")
    resp = await client.delete(f"/neila/deadletters/{did}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    resp = await client.delete("/neila/deadletters/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_metrics_includes_deadletter_fields(client: AsyncClient):
    resp = await client.get("/neila/metrics")
    data = resp.json()
    assert "deadletter_count" in data
    assert "replay_count_total" in data
    assert "last_deadletter_ts" in data

