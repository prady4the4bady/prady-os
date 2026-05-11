from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from embedding_engine import EmbeddingEngine
from skill_library import SkillLibrary
from task_evaluator import TaskRecord


@pytest.mark.asyncio
async def test_store_retrieve_delete_skill(tmp_path: Path):
    eng = EmbeddingEngine()
    lib = SkillLibrary(tmp_path / "self_learning.db", eng)
    await lib.init()

    emb = eng.embed("open browser and search")
    skill_id = await lib.store_skill(
        "open browser and search",
        [{"step": "open_browser"}, {"step": "type_query"}],
        emb,
        0.91,
        "success",
    )
    assert skill_id

    q = eng.embed("search in browser")
    matches = await lib.retrieve_similar(q, top_k=3)
    assert matches
    assert matches[0].skill_id == skill_id

    deleted = await lib.delete_skill(skill_id)
    assert deleted


@pytest.mark.asyncio
async def test_record_task_and_stats(tmp_path: Path):
    eng = EmbeddingEngine()
    lib = SkillLibrary(tmp_path / "self_learning.db", eng)
    await lib.init()

    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=60)).isoformat()
    new_ts = (now - timedelta(days=1)).isoformat()

    await lib.record_task(
        TaskRecord(
            record_id="r_old",
            task_id="t_old",
            task_description="old",
            outcome="success",
            score=0.4,
            duration_ms=1000,
            model_used="m",
            user_rating=None,
            error_message=None,
            skill_id=None,
            recorded_ts=old_ts,
        )
    )

    await lib.record_task(
        TaskRecord(
            record_id="r_new",
            task_id="t_new",
            task_description="new",
            outcome="success",
            score=0.8,
            duration_ms=1000,
            model_used="m",
            user_rating=None,
            error_message=None,
            skill_id=None,
            recorded_ts=new_ts,
        )
    )

    stats = await lib.get_stats()
    assert stats.total_tasks_recorded == 2
    assert 0.0 <= stats.avg_task_score <= 1.0
    assert len(stats.recent_scores) == 1
    assert len(stats.older_scores) == 1
