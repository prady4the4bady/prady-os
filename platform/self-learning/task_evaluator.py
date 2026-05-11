"""Task scoring logic for self-learning loop."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskRecord:
    record_id: str
    task_id: str
    task_description: str
    outcome: str
    score: float
    duration_ms: int
    model_used: str
    user_rating: int | None
    error_message: str | None
    skill_id: str | None
    recorded_ts: str


class TaskEvaluator:
    def score(self, task_record: TaskRecord) -> float:
        outcome = task_record.outcome.lower()
        if outcome == "success":
            outcome_score = 1.0
        elif outcome == "partial":
            outcome_score = 0.5
        else:
            outcome_score = 0.0

        duration = max(0, int(task_record.duration_ms))
        speed_score = max(0.0, min(1.0, 1.0 - (duration - 5000) / 15000)) if duration > 5000 else 1.0

        if task_record.user_rating is None:
            user_score = 0.7
        else:
            rating = max(1, min(5, int(task_record.user_rating)))
            user_score = rating / 5.0

        error_penalty = -0.2 if task_record.error_message else 0.0

        weighted = (
            (outcome_score * 0.5)
            + (speed_score * 0.2)
            + (user_score * 0.2)
            + ((1.0 + error_penalty) * 0.1)
        )

        return max(0.0, min(1.0, float(weighted)))

    def should_store_as_skill(self, score: float, outcome: str) -> bool:
        return score >= 0.6 and outcome.lower() != "failure"

    def compute_improvement_rate(self, recent_scores: list[float], older_scores: list[float]) -> float:
        if not recent_scores or not older_scores:
            return 0.0
        old_avg = sum(older_scores) / len(older_scores)
        if old_avg <= 0:
            return 0.0
        new_avg = sum(recent_scores) / len(recent_scores)
        return ((new_avg - old_avg) / old_avg) * 100.0
