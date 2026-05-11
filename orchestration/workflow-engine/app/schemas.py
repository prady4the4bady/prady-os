"""Pydantic v2 models for tasks, subtasks, and approvals."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"


class SubtaskStatus(str, Enum):
    pending = "pending"
    waiting_approval = "waiting_approval"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskStatus(str, Enum):
    queued = "queued"
    decomposing = "decomposing"
    running = "running"
    waiting_approval = "waiting_approval"
    completed = "completed"
    failed = "failed"


class TaskRequest(BaseModel):
    """Inbound job submitted to the orchestration engine."""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    agent: str = "conductor"
    priority: Priority = Priority.normal
    policy: str = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Subtask(BaseModel):
    """A single unit of work assigned to one sub-agent."""

    subtask_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: str
    agent_type: Literal["screen", "browser", "shell", "file", "research"]
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)  # subtask_ids
    status: SubtaskStatus = SubtaskStatus.pending
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskRecord(BaseModel):
    """Full task state tracked in memory during execution."""

    task_id: str
    goal: str
    agent: str
    priority: Priority
    policy: str
    status: TaskStatus = TaskStatus.queued
    subtasks: List[Subtask] = Field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class ApprovalRequest(BaseModel):
    """Raised when an agent action requires human confirmation."""

    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    subtask_id: str
    agent_type: str
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalDecision(BaseModel):
    """Human response to an approval request."""

    approval_id: str
    approved: bool
    reviewer_note: Optional[str] = None


class ApprovalRecord(BaseModel):
    """Full approval state stored in the approval store."""

    approval_id: str
    task_id: str
    subtask_id: str
    agent_type: str
    action: str
    params: Dict[str, Any]
    reason: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime
    decided_at: Optional[datetime] = None
    reviewer_note: Optional[str] = None
