from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import respx

from kryos_sdk.task import KryosTask


def request_body(route) -> dict:
    return json.loads(route.calls.last.request.content.decode())


@pytest.mark.asyncio
async def test_constructor_uses_default_base():
    task = KryosTask()
    assert task.api_base == "http://localhost:8005"


@pytest.mark.asyncio
async def test_schedule_returns_id():
    task = KryosTask("http://example")
    with respx.mock() as mock:
        mock.post("http://example/tasks/schedule").respond(json={"schedule_id": "s1"})
        result = await task.schedule("run", datetime.now(timezone.utc))
    assert result == "s1"


@pytest.mark.asyncio
async def test_schedule_sends_repeat_option():
    task = KryosTask("http://example")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://example/tasks/schedule").respond(json={"schedule_id": "s1"})
        await task.schedule("run", datetime.now(timezone.utc), {"repeat": "daily"})
    assert request_body(route)["repeat"] == "daily"


@pytest.mark.asyncio
async def test_cancel_success():
    task = KryosTask("http://example")
    with respx.mock() as mock:
        mock.delete("http://example/tasks/s1").respond(json={"cancelled": True})
        await task.cancel("s1")


@pytest.mark.asyncio
async def test_list_returns_tasks():
    task = KryosTask("http://example")
    with respx.mock() as mock:
        mock.get("http://example/tasks").respond(json={"tasks": [{"schedule_id": "s1", "description": "run", "run_at": "2026-05-11T00:00:00Z", "status": "scheduled"}]})
        result = await task.list()
    assert result[0].schedule_id == "s1"


@pytest.mark.asyncio
async def test_list_accepts_array_response():
    task = KryosTask("http://example")
    with respx.mock() as mock:
        mock.get("http://example/tasks").respond(json=[{"schedule_id": "s1", "description": "run", "run_at": "2026-05-11T00:00:00Z", "status": "scheduled"}])
        result = await task.list()
    assert result[0].status == "scheduled"
