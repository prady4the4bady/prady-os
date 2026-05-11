"""SkillCurator — background asyncio task that grades, prunes, and promotes
skills in the Lumyn skill registry every 30 minutes.

Grading criteria
----------------
- success_rate   : fraction of executions that succeeded
- avg_latency_ms : average execution time (lower is better)
- last_used_at   : prune if >7 days unused AND success_rate < 0.6
- elite flag     : success_rate > 0.92 for 10+ uses

Lifecycle
---------
deprecated  → after 24 h without recovery → deleted from registry
active      → normal state
elite       → high-performing, highlighted in UI
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path("platform/audit/skill_events.jsonl")
CURATION_INTERVAL_SECONDS = 30 * 60   # 30 minutes
PRUNE_UNUSED_DAYS = 7
PRUNE_SUCCESS_THRESHOLD = 0.6
ELITE_SUCCESS_THRESHOLD = 0.92
ELITE_MIN_USES = 10
DEPRECATION_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _write_audit(event_type: str, data: dict) -> None:  # type: ignore[type-arg]
    """Append a JSON line to the audit log."""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"event": event_type, "ts": time.time(), **data}
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _maybe_promote(skill: object) -> bool:
    if getattr(skill, "elite", False):
        return False
    if getattr(skill, "use_count", 0) < ELITE_MIN_USES:
        return False
    if getattr(skill, "success_rate", 0.0) <= ELITE_SUCCESS_THRESHOLD:
        return False
    skill.elite = True
    _write_audit(
        "skill_promoted",
        {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "success_rate": skill.success_rate,
            "use_count": skill.use_count,
        },
    )
    logger.info("SkillCurator: promoted skill %s to elite", skill.skill_id)
    return True


def _maybe_demote(skill: object) -> None:
    if not getattr(skill, "elite", False):
        return
    if getattr(skill, "success_rate", 0.0) > ELITE_SUCCESS_THRESHOLD:
        return
    skill.elite = False
    _write_audit(
        "skill_demoted",
        {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "success_rate": skill.success_rate,
        },
    )


def _get_unused_days(now: float, skill: object) -> float:
    last_used_at = getattr(skill, "last_used_at", None)
    if not last_used_at:
        return 0
    return (now - last_used_at) / 86400


def _should_prune(skill: object, unused_days: float) -> bool:
    return (
        getattr(skill, "use_count", 0) > 0
        and unused_days > PRUNE_UNUSED_DAYS
        and getattr(skill, "success_rate", 0.0) < PRUNE_SUCCESS_THRESHOLD
    )


def _maybe_deprecate(skill: object, now: float, unused_days: float) -> bool:
    if not _should_prune(skill, unused_days):
        return False
    if getattr(skill, "status", "") != "active":
        return False
    skill.status = "deprecated"
    skill._deprecated_at = now  # type: ignore[attr-defined]
    _write_audit(
        "skill_deprecated",
        {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "unused_days": round(unused_days, 1),
            "success_rate": skill.success_rate,
        },
    )
    logger.info("SkillCurator: deprecated skill %s", skill.skill_id)
    return True


def _should_delete(skill: object, now: float) -> bool:
    deprecated_at: Optional[float] = getattr(skill, "_deprecated_at", None)
    return (
        getattr(skill, "status", "") == "deprecated"
        and deprecated_at is not None
        and (now - deprecated_at) > DEPRECATION_TTL_SECONDS
    )


class SkillCurator:
    """Runs as an asyncio background task; grades/prunes/promotes skills."""

    def __init__(self, interval: float = CURATION_INTERVAL_SECONDS) -> None:
        self._interval = interval
        self._task: Optional[asyncio.Task[None]] = None
        self._stopped = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stopped = False
        self._task = asyncio.ensure_future(self._run())
        logger.info("SkillCurator started (interval=%.0fs)", self._interval)

    def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
        logger.info("SkillCurator stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while not self._stopped:
            try:
                self._grade_cycle()
            except Exception as exc:
                logger.exception("SkillCurator grade cycle failed: %s", exc)
            await asyncio.sleep(self._interval)

    # ------------------------------------------------------------------
    # Grade cycle
    # ------------------------------------------------------------------

    def _grade_cycle(self) -> None:
        from app.lumyn_bridge import list_skills, remove_skill  # local import to avoid circular

        skills = list_skills()
        now = time.time()
        promoted = 0
        deprecated_count = 0
        deleted_count = 0

        for skill in skills:
            if skill.status == "deleted":
                continue

            if _maybe_promote(skill):
                promoted += 1
            _maybe_demote(skill)

            unused_days = _get_unused_days(now, skill)
            if _maybe_deprecate(skill, now, unused_days):
                deprecated_count += 1

            if _should_delete(skill, now):
                remove_skill(skill.skill_id)
                deleted_count += 1
                _write_audit("skill_deleted", {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                })
                logger.info("SkillCurator: deleted skill %s", skill.skill_id)

        logger.info(
            "SkillCurator cycle: %d skills — promoted=%d deprecated=%d deleted=%d",
            len(skills),
            promoted,
            deprecated_count,
            deleted_count,
        )
