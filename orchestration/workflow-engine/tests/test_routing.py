"""Tests for Redis Streams routing and approval gating via conductor."""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import fakeredis.aioredis as fake_aioredis
import pytest
import respx
import httpx

from app.activity_log import ActivityLogger
from app.approvals import ApprovalStore
from app.bus import MessageBus, agent_stream, CONDUCTOR_RESULTS_STREAM
from app.conductor import Conductor
from app.schemas import ApprovalDecision

pytestmark = pytest.mark.anyio


@pytest.fixture()
async def real_fake_bus() -> MessageBus:
    server = fakeredis.FakeServer()
    bus = MessageBus.__new__(MessageBus)
    bus._redis_url = "redis://localhost:6379"
    bus._client = fake_aioredis.FakeRedis(server=server, decode_responses=True)
    return bus


async def test_publish_and_read(real_fake_bus: MessageBus):
    stream = "kryos:stream:test"
    await real_fake_bus.publish(stream, {"hello": "world"})
    messages = await real_fake_bus.read_new(stream, "grp", "consumer1")
    assert len(messages) == 1
    _msg_id, fields = messages[0]
    assert fields["hello"] == "world"


async def test_ack_removes_message(real_fake_bus: MessageBus):
    stream = "kryos:stream:ack_test"
    await real_fake_bus.publish(stream, {"key": "val"})
    messages = await real_fake_bus.read_new(stream, "grp", "c1")
    assert len(messages) == 1
    msg_id, _ = messages[0]
    await real_fake_bus.ack(stream, "grp", msg_id)
    # After ack there should be no pending messages for a new consumer
    second_read = await real_fake_bus.read_new(stream, "grp", "c2")
    assert second_read == []


async def test_conductor_publishes_to_agent_stream(
    real_fake_bus: MessageBus,
    approvals: ApprovalStore,
    activity: ActivityLogger,
):
    conductor = Conductor(
        bus=real_fake_bus,
        approvals=approvals,
        activity=activity,
        gateway_url="http://gateway",
        playwright_runner_url="http://playwright-runner",
        gateway_model="test-model",
        approval_timeout=5.0,
    )

    decompose_items = [
        {
            "agent_type": "shell",
            "action": "run",
            "params": {"command": "echo hi"},
            "depends_on": [],
        }
    ]
    summarize_content = "Done."

    with respx.mock:
        # First call = decompose, second = summarize
        call_count = 0

        def _side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"content": json.dumps(decompose_items)}}
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": summarize_content}}]},
            )

        respx.post("http://gateway/v1/chat/completions").mock(side_effect=_side_effect)

        from app.schemas import TaskRequest
        req = TaskRequest(goal="echo hello world", policy="default")
        await conductor.enqueue(req)

        # Give the background task time to execute
        await asyncio.sleep(0.3)

    msgs = await real_fake_bus.read_new(agent_stream("shell"), "grp", "c1")
    assert len(msgs) >= 1
    _id, fields = msgs[0]
    assert fields["agent_type"] == "shell"
    assert fields["action"] == "run"


async def test_approval_gating_blocks_until_decision(
    real_fake_bus: MessageBus,
    approvals: ApprovalStore,
    activity: ActivityLogger,
):
    conductor = Conductor(
        bus=real_fake_bus,
        approvals=approvals,
        activity=activity,
        gateway_url="http://gateway",
        playwright_runner_url="http://playwright-runner",
        gateway_model="test-model",
        approval_timeout=5.0,
    )

    decompose_items = [
        {
            "agent_type": "shell",
            "action": "run",
            "params": {"command": "echo safe"},
            "depends_on": [],
        }
    ]

    with respx.mock:
        call_count = 0

        def _side(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": json.dumps(decompose_items)}}]},
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "completed"}}]},
            )

        respx.post("http://gateway/v1/chat/completions").mock(side_effect=_side)

        from app.schemas import TaskRequest
        req = TaskRequest(goal="delete tmp dir", policy="require_approval_for_shell")
        record = await conductor.enqueue(req)

        # Short wait — task should be blocked on approval
        await asyncio.sleep(0.1)

        pending = approvals.pending()
        assert len(pending) == 1

        # Approve after 100ms
        approval_id = pending[0].approval_id

        async def approve():
            await asyncio.sleep(0.1)
            await approvals.submit(ApprovalDecision(approval_id=approval_id, approved=True))

        approval_task = asyncio.create_task(approve())
        _ = approval_task

        # Give background task time to finish after approval
        await asyncio.sleep(0.5)

    final = conductor.get_task(record.task_id)
    assert final is not None
    assert final.status.value in ("completed", "running", "failed")
