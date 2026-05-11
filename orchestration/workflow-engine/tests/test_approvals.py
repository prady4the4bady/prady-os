"""Tests for the ApprovalStore."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.approvals import ApprovalStore
from app.schemas import ApprovalDecision, ApprovalRequest

pytestmark = pytest.mark.anyio


def _req(**kwargs) -> ApprovalRequest:
    defaults = {
        "task_id": str(uuid.uuid4()),
        "subtask_id": str(uuid.uuid4()),
        "agent_type": "shell",
        "action": "run",
        "params": {"command": "ls"},
        "reason": "policy requires approval",
    }
    defaults.update(kwargs)
    return ApprovalRequest(**defaults)


async def test_request_creates_pending_record(approvals: ApprovalStore):
    req = _req()
    record = await approvals.request(req)
    assert record.status == "pending"
    assert record.approval_id == req.approval_id
    assert approvals.get(req.approval_id) is not None


async def test_approve_resolves_wait(approvals: ApprovalStore):
    req = _req()
    await approvals.request(req)

    async def approve_soon():
        await asyncio.sleep(0.05)
        await approvals.submit(ApprovalDecision(approval_id=req.approval_id, approved=True))

    approval_task = asyncio.create_task(approve_soon())
    _ = approval_task
    record = await approvals.wait_for_decision(req.approval_id, timeout=2.0)
    assert record.status == "approved"


async def test_reject_resolves_wait(approvals: ApprovalStore):
    req = _req()
    await approvals.request(req)

    async def reject_soon():
        await asyncio.sleep(0.05)
        await approvals.submit(
            ApprovalDecision(approval_id=req.approval_id, approved=False, reviewer_note="no")
        )

    rejection_task = asyncio.create_task(reject_soon())
    _ = rejection_task
    record = await approvals.wait_for_decision(req.approval_id, timeout=2.0)
    assert record.status == "rejected"
    assert record.reviewer_note == "no"


async def test_timeout_returns_pending(approvals: ApprovalStore):
    req = _req()
    await approvals.request(req)
    record = await approvals.wait_for_decision(req.approval_id, timeout=0.05)
    # Timed out — still pending
    assert record.status == "pending"


async def test_submit_unknown_returns_none(approvals: ApprovalStore):
    result = await approvals.submit(
        ApprovalDecision(approval_id=str(uuid.uuid4()), approved=True)
    )
    assert result is None


async def test_pending_list_excludes_decided(approvals: ApprovalStore):
    req1 = _req()
    req2 = _req()
    await approvals.request(req1)
    await approvals.request(req2)

    await approvals.submit(ApprovalDecision(approval_id=req1.approval_id, approved=True))

    pending = approvals.pending()
    ids = [p.approval_id for p in pending]
    assert req1.approval_id not in ids
    assert req2.approval_id in ids


async def test_all_returns_all(approvals: ApprovalStore):
    req1 = _req()
    req2 = _req()
    await approvals.request(req1)
    await approvals.request(req2)
    assert len(approvals.all()) == 2
