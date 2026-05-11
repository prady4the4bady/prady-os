"""Tests for lumyn_bridge.py"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.lumyn_bridge import (
    LumynBridge,
    Skill,
    SkillResult,
    _deterministic_id,
    _task_to_name,
    get_skill,
    list_skills,
    register_skill,
    remove_skill,
    _SKILL_REGISTRY,
)


@pytest.fixture(autouse=True)
def clear_registry():
    """Ensure each test starts with a clean skill registry."""
    _SKILL_REGISTRY.clear()
    yield
    _SKILL_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_deterministic_id_stable():
    task = "Write a Python function to sort a list"
    id1 = _deterministic_id(task)
    id2 = _deterministic_id(task)
    assert id1 == id2
    assert id1.startswith("skill-")


def test_task_to_name():
    assert _task_to_name("Write a Python function") == "write_a_python_function"
    assert _task_to_name("") == "unnamed_skill"
    assert len(_task_to_name("a" * 200)) <= 64


def test_skill_success_rate():
    skill = Skill(
        skill_id="test-1",
        name="test",
        description="test",
        task_description="test task",
        code="print('hello')",
    )
    assert skill.success_rate == pytest.approx(0.0)
    skill.success_count = 8
    skill.failure_count = 2
    assert skill.success_rate == pytest.approx(0.8)


def test_skill_avg_latency():
    skill = Skill(
        skill_id="test-2",
        name="test",
        description="test",
        task_description="test task",
        code="print('hello')",
    )
    assert skill.avg_latency_ms == pytest.approx(0.0)
    skill.success_count = 4
    skill.total_latency_ms = 200.0
    assert skill.avg_latency_ms == pytest.approx(50.0)


def test_skill_to_dict():
    skill = Skill(
        skill_id="s1",
        name="my_skill",
        description="does stuff",
        task_description="do stuff",
        code="pass",
        success_count=5,
        failure_count=1,
    )
    d = skill.to_dict()
    assert d["skill_id"] == "s1"
    assert d["success_rate"] == pytest.approx(5 / 6, rel=1e-3)
    assert "avg_latency_ms" in d
    assert d["elite"] is False


def test_register_get_remove():
    skill = Skill(
        skill_id="reg-1",
        name="test",
        description="t",
        task_description="test",
        code="pass",
    )
    register_skill(skill)
    assert get_skill("reg-1") is skill
    assert remove_skill("reg-1") is True
    assert get_skill("reg-1") is None
    assert remove_skill("reg-1") is False


# ---------------------------------------------------------------------------
# async integration tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_acquire_skill_new():
    bridge = LumynBridge(agent_id="test-agent")
    skill = await bridge.acquire_skill("Write a hello world function in Python")
    assert isinstance(skill, Skill)
    assert skill.skill_id.startswith("skill-")
    assert skill.status == "active"
    # Should be in registry
    assert get_skill(skill.skill_id) is skill


@pytest.mark.anyio
async def test_acquire_skill_cached():
    bridge = LumynBridge(agent_id="test-agent")
    task = "Unique task for caching test"
    skill1 = await bridge.acquire_skill(task)
    skill2 = await bridge.acquire_skill(task)
    assert skill1.skill_id == skill2.skill_id


@pytest.mark.anyio
async def test_execute_skill_success():
    bridge = LumynBridge(agent_id="test-agent")
    skill = await bridge.acquire_skill("Compute the sum of a list")
    result = await bridge.execute_skill(skill, {"numbers": [1, 2, 3]})
    assert isinstance(result, SkillResult)
    assert result.skill_id == skill.skill_id
    # Skill telemetry updated
    assert skill.success_count + skill.failure_count == 1
    assert skill.last_used_at is not None


@pytest.mark.anyio
async def test_execute_skill_updates_telemetry():
    bridge = LumynBridge(agent_id="test-agent")
    skill = await bridge.acquire_skill("Telemetry test task")
    await bridge.execute_skill(skill)
    await bridge.execute_skill(skill)
    assert (skill.success_count + skill.failure_count) == 2
    assert skill.total_latency_ms > 0


@pytest.mark.anyio
async def test_soul_context_injection():
    bridge = LumynBridge(soul_context="# SOUL\nname: TestBot", agent_id="test-agent")
    skill = await bridge.acquire_skill("Task with soul context")
    assert "soul" in skill.code or "TestBot" in skill.code or "soul_context" in skill.code
