"""In-memory approval store with async wait-for-decision support.

When a subtask requires human approval the conductor calls request(),
which inserts a pending ApprovalRecord and sets an asyncio.Event.
The conductor then awaits wait_for_decision(); when a human POSTs to
/approvals/submit the event fires and execution resumes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.schemas import ApprovalDecision, ApprovalRecord, ApprovalRequest


class ApprovalStore:
    def __init__(self) -> None:
        self._store: Dict[str, ApprovalRecord] = {}
        self._events: Dict[str, asyncio.Event] = {}

    async def request(self, req: ApprovalRequest) -> ApprovalRecord:
        await asyncio.sleep(0)
        record = ApprovalRecord(
            approval_id=req.approval_id,
            task_id=req.task_id,
            subtask_id=req.subtask_id,
            agent_type=req.agent_type,
            action=req.action,
            params=req.params,
            reason=req.reason,
            created_at=req.created_at,
        )
        self._store[req.approval_id] = record
        self._events[req.approval_id] = asyncio.Event()
        return record

    async def submit(self, decision: ApprovalDecision) -> Optional[ApprovalRecord]:
        """Apply an approval or rejection decision. Returns None if not found."""
        await asyncio.sleep(0)
        record = self._store.get(decision.approval_id)
        if not record:
            return None
        if record.status != "pending":
            return record  # idempotent for already-decided approvals

        record.status = "approved" if decision.approved else "rejected"
        record.decided_at = datetime.now(timezone.utc)
        record.reviewer_note = decision.reviewer_note

        event = self._events.get(decision.approval_id)
        if event:
            event.set()
        return record

    async def wait_for_decision(
        self,
        approval_id: str,
        wait_seconds: float = 300.0,
        **kwargs: Any,
    ) -> Optional[ApprovalRecord]:
        """Block until the approval is decided or *timeout* seconds elapse."""
        if "timeout" in kwargs:
            wait_seconds = float(kwargs["timeout"])

        event = self._events.get(approval_id)
        if not event:
            return self._store.get(approval_id)
        try:
            async with asyncio.timeout(wait_seconds):
                await event.wait()
        except TimeoutError:
            pass
        return self._store.get(approval_id)

    def pending(self) -> List[ApprovalRecord]:
        return [r for r in self._store.values() if r.status == "pending"]

    def get(self, approval_id: str) -> Optional[ApprovalRecord]:
        return self._store.get(approval_id)

    def all(self) -> List[ApprovalRecord]:
        return list(self._store.values())
