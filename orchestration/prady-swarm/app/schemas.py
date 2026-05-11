"""Pydantic schemas for the kryos-swarm API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StartSwarmRequest(BaseModel):
    goal: str = Field(..., description="High-level goal for the swarm to accomplish")
    max_agents: int = Field(5, ge=1, le=50, description="Maximum number of parallel agents")
    model_id: Optional[str] = Field(None, description="Override agent model (default: lumyn-agent)")


class StartSwarmResponse(BaseModel):
    swarm_id: str
    goal: str
    max_agents: int
    model_id: str
    status: str


class AgentState(BaseModel):
    agent_id: str
    model_id: str
    status: str
    memory_namespace: str
    task_history_count: int
    result: Optional[Dict[str, Any]] = None


class SwarmState(BaseModel):
    swarm_id: str
    goal: str
    status: str
    agent_count: int
    agents: List[AgentState] = []
    started_at: str
    finished_at: Optional[str] = None
    merged_result: Optional[Dict[str, Any]] = None


class SwarmStatusResponse(BaseModel):
    swarms: List[SwarmState]


class SwarmResultResponse(BaseModel):
    swarm_id: str
    status: str
    merged_result: Optional[Dict[str, Any]] = None
