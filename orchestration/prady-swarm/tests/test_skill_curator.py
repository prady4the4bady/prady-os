"""Tests for skill_curator.py"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.lumyn_bridge import Skill, _SKILL_REGISTRY, register_skill, get_skill
from app.skill_curator import (
    ELITE_MIN_USES,
    ELITE_SUCCESS_THRESHOLD,
    PRUNE_SUCCESS_THRESHOLD,
    PRUNE_UNUSED_DAYS,
    SkillCurator,
)


@pytest.fixture(autouse=True)
def clear_registry():
    _SKILL_REGISTRY.clear()
    yield
    _SKILL_REGISTRY.clear()


def _make_skill(skill_id: str, success: int = 0, failure: int = 0, last_used_delta_days: float = 0) -> Skill:
    s = Skill(
        skill_id=skill_id,
        name=skill_id,
        description="test",
        task_description="test",
        code="pass",
    )
    s.success_count = success
    s.failure_count = failure
    s.total_latency_ms = 100.0 * (success + failure)
    if last_used_delta_days != 0:
        s.last_used_at = time.time() - (last_used_delta_days * 86400)
    else:
        s.last_used_at = time.time()
    return s


@pytest.mark.anyio
async def test_curator_promotes_elite():
    skill = _make_skill("elite-1", success=12, failure=0)
    register_skill(skill)
    assert skill.elite is False

    curator = SkillCurator(interval=999999)
    with patch("app.skill_curator._write_audit"):
        await curator._grade_cycle()

    assert skill.elite is True


@pytest.mark.anyio
async def test_curator_does_not_promote_below_threshold():
    skill = _make_skill("no-elite-1", success=5, failure=5)
    register_skill(skill)

    curator = SkillCurator(interval=999999)
    with patch("app.skill_curator._write_audit"):
        await curator._grade_cycle()

    assert skill.elite is False


@pytest.mark.anyio
async def test_curator_deprecates_old_low_quality_skill():
    skill = _make_skill("old-1", success=2, failure=8, last_used_delta_days=10)
    register_skill(skill)

    curator = SkillCurator(interval=999999)
    with patch("app.skill_curator._write_audit"):
        await curator._grade_cycle()

    assert skill.status == "deprecated"


@pytest.mark.anyio
async def test_curator_does_not_deprecate_recent_skill():
    skill = _make_skill("recent-1", success=1, failure=9, last_used_delta_days=1)
    register_skill(skill)

    curator = SkillCurator(interval=999999)
    with patch("app.skill_curator._write_audit"):
        await curator._grade_cycle()

    assert skill.status == "active"


@pytest.mark.anyio
async def test_curator_deletes_after_ttl():
    skill = _make_skill("del-1", success=0, failure=10, last_used_delta_days=10)
    skill.status = "deprecated"
    skill._deprecated_at = time.time() - (25 * 3600)  # 25 hours ago
    register_skill(skill)

    curator = SkillCurator(interval=999999)
    with patch("app.skill_curator._write_audit"):
        await curator._grade_cycle()

    assert get_skill("del-1") is None


@pytest.mark.anyio
async def test_curator_demotes_elite_on_drop():
    skill = _make_skill("demote-1", success=10, failure=5)
    skill.elite = True
    register_skill(skill)

    curator = SkillCurator(interval=999999)
    with patch("app.skill_curator._write_audit"):
        await curator._grade_cycle()

    assert skill.elite is False
