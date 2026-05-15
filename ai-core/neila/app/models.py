"""Shared data models for Neila — avoids circular imports between main and persistence."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RetryState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    EXHAUSTED = "exhausted"


@dataclass
class RetryEntry:
    id: str
    task_type: str
    target_url: str
    payload: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3
    attempt: int = 0
    state: RetryState = RetryState.PENDING
    last_error: str = ""
    created_ts: str = ""
    next_attempt_ts: str = ""


@dataclass
class ScheduledAction:
    id: str
    action_type: str
    target_url: str
    payload: dict[str, Any] = field(default_factory=dict)
    due_ts: str = ""
    trigger_ts: str = ""
    completed: bool = False


@dataclass
class LoopMetrics:
    cycle_count: int = 0
    last_cycle_ts: str = ""
    tasks_scanned: int = 0
    actions_triggered: int = 0
    actions_deferred: int = 0
    retry_queue_depth: int = 0
    scheduled_count: int = 0
    digests_generated: int = 0
    failures: int = 0
    followups_generated: int = 0
