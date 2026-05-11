from __future__ import annotations

import json

import pytest
import respx

from kryos_sdk.agent import PraxAgent


def request_body(route) -> dict:
    return json.loads(route.calls.last.request.content.decode())


@pytest.mark.asyncio
async def test_constructor_uses_default_base():
    agent = PraxAgent()
    assert agent.api_base == "http://localhost:8001"


@pytest.mark.asyncio
async def test_assign_task_success():
    agent = PraxAgent("http://example")
    with respx.mock() as mock:
        mock.post("http://example/tasks").respond(json={"task_id": "t1", "status": "queued", "result": "ok"})
        result = await agent.assignTask("do it", {"priority": 2})
    assert result.task_id == "t1"
    assert result.status == "queued"


@pytest.mark.asyncio
async def test_assign_task_sends_payload():
    agent = PraxAgent("http://example")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://example/tasks").respond(json={"task_id": "t1", "status": "queued"})
        await agent.assignTask("do it", {"timeout_ms": 5000})
    assert request_body(route) == {"description": "do it", "timeout_ms": 5000}


@pytest.mark.asyncio
async def test_get_task_status_success():
    agent = PraxAgent("http://example")
    with respx.mock() as mock:
        mock.get("http://example/tasks/t1").respond(json={"task_id": "t1", "status": "done", "result": "ok"})
        result = await agent.getTaskStatus("t1")
    assert result.result == "ok"


@pytest.mark.asyncio
async def test_list_skills_from_wrapped_response():
    agent = PraxAgent()
    with respx.mock() as mock:
        mock.get("http://localhost:8018/learn/skills").respond(json={"skills": [{"skill_id": "s1", "description": "desc", "avg_score": 0.9}]})
        skills = await agent.listSkills()
    assert skills[0].skill_id == "s1"


@pytest.mark.asyncio
async def test_assign_task_raises_on_http_error():
    agent = PraxAgent("http://example")
    with respx.mock() as mock:
        mock.post("http://example/tasks").respond(status_code=500, text="boom")
        with pytest.raises(Exception):
            await agent.assignTask("do it")
