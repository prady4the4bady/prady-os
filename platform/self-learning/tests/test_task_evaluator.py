from __future__ import annotations

from task_evaluator import TaskEvaluator, TaskRecord


def _record(**overrides):
    base = dict(
        record_id="r1",
        task_id="t1",
        task_description="demo",
        outcome="success",
        score=0.0,
        duration_ms=2000,
        model_used="m",
        user_rating=5,
        error_message=None,
        skill_id=None,
        recorded_ts="2026-01-01T00:00:00Z",
    )
    base.update(overrides)
    return TaskRecord(**base)


def test_score_success_fast_high_rating():
    ev = TaskEvaluator()
    s = ev.score(_record())
    assert 0.8 <= s <= 1.0


def test_score_failure_with_error_is_low():
    ev = TaskEvaluator()
    s = ev.score(_record(outcome="failure", duration_ms=20000, user_rating=1, error_message="boom"))
    assert 0.0 <= s <= 0.4


def test_should_store_skill_gate():
    ev = TaskEvaluator()
    assert ev.should_store_as_skill(0.7, "success")
    assert not ev.should_store_as_skill(0.59, "success")
    assert not ev.should_store_as_skill(0.9, "failure")


def test_compute_improvement_rate():
    ev = TaskEvaluator()
    rate = ev.compute_improvement_rate([0.8, 0.9], [0.4, 0.5])
    assert rate > 0
    assert ev.compute_improvement_rate([], [0.1]) == 0.0
    assert ev.compute_improvement_rate([0.1], []) == 0.0
