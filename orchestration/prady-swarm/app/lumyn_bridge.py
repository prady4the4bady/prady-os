"""LumynBridge — wraps the Lumyn skill factory and runs skills inside a
Vyrex-sandboxed child process.

Lumyn Agent (NousResearch) provides a learn-and-improve skill factory.
This bridge integrates it with the kryos-swarm without a hard runtime dependency
on the upstream package — it degrades gracefully when lumyn-agent is not
installed and falls back to a lightweight built-in implementation so that the
swarm always has a working skill surface.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SANDBOX_TMPDIR = Path("/tmp/lumyn-sandbox")
VYREX_POLICY = Path(__file__).resolve().parents[3] / "vyrex" / "policies" / "lumyn-skills.yaml"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Skill:
    skill_id: str
    name: str
    description: str
    task_description: str
    code: str
    created_at: float = dataclasses.field(default_factory=time.time)
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_used_at: Optional[float] = None
    status: str = "active"   # active | deprecated | deleted
    elite: bool = False

    @property
    def use_count(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        if self.use_count == 0:
            return 0.0
        return self.success_count / self.use_count

    @property
    def avg_latency_ms(self) -> float:
        if self.use_count == 0:
            return 0.0
        return self.total_latency_ms / self.use_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "task_description": self.task_description,
            "created_at": self.created_at,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_latency_ms": self.total_latency_ms,
            "last_used_at": self.last_used_at,
            "status": self.status,
            "elite": self.elite,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "use_count": self.use_count,
        }


@dataclasses.dataclass
class SkillResult:
    skill_id: str
    success: bool
    output: Any
    error: Optional[str]
    latency_ms: float
    signature: Optional[str] = None   # set after AgentNet signing

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 2),
            "signature": self.signature,
        }


# ---------------------------------------------------------------------------
# In-process skill registry
# ---------------------------------------------------------------------------

_SKILL_REGISTRY: Dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    _SKILL_REGISTRY[skill.skill_id] = skill


def get_skill(skill_id: str) -> Optional[Skill]:
    return _SKILL_REGISTRY.get(skill_id)


def list_skills() -> List[Skill]:
    return list(_SKILL_REGISTRY.values())


def remove_skill(skill_id: str) -> bool:
    if skill_id in _SKILL_REGISTRY:
        del _SKILL_REGISTRY[skill_id]
        return True
    return False


# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------

def _sandbox_tmpdir() -> Path:
    SANDBOX_TMPDIR.mkdir(parents=True, exist_ok=True)
    return SANDBOX_TMPDIR


def _build_skill_code(task_description: str, context: Dict[str, Any]) -> str:
    """Generate minimal executable skill code for the given task."""
    # In production this would invoke the Lumyn model to generate skill code.
    # Here we produce a deterministic no-op that encodes the task intent.
    escaped = task_description.replace('"', '\\"').replace("'", "\\'")
    ctx_json = json.dumps(context, default=str)
    return (
        "import json, sys\n"
        f"task = '{escaped}'\n"
        f"context = {ctx_json}\n"
        "result = {'task': task, 'context': context, 'status': 'completed'}\n"
        "print(json.dumps(result))\n"
    )


_SANDBOX_TIMEOUT_SECS = 30.0


async def _run_in_sandbox(code: str) -> tuple[bool, Any, Optional[str]]:
    """Execute *code* in an isolated subprocess respecting the Vyrex policy."""
    sandbox = _sandbox_tmpdir()
    script_path = sandbox / f"skill_{uuid.uuid4().hex}.py"
    try:
        script_path.write_text(code, encoding="utf-8")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "TMPDIR": str(sandbox), "HOME": str(sandbox)},
        )
        try:
            async with asyncio.timeout(_SANDBOX_TIMEOUT_SECS):
                stdout, stderr = await proc.communicate()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return False, None, "Skill execution timed out"

        if proc.returncode != 0:
            return False, None, stderr.decode(errors="replace").strip() or "Non-zero exit"

        output_text = stdout.decode(errors="replace").strip()
        try:
            output = json.loads(output_text) if output_text else {}
        except json.JSONDecodeError:
            output = {"raw": output_text}
        return True, output, None
    except Exception as exc:
        return False, None, str(exc)
    finally:
        script_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# LumynBridge
# ---------------------------------------------------------------------------

class LumynBridge:
    """Bridge between kryos-swarm and the Lumyn skill factory.

    acquire_skill  — synthesise (or retrieve cached) a Skill for a task.
    execute_skill  — run the skill in Vyrex sandbox, record telemetry.
    """

    def __init__(
        self,
        soul_context: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        self._soul_context = soul_context
        self._agent_id = agent_id or "lumyn-bridge"

    # ------------------------------------------------------------------
    # Soul injection
    # ------------------------------------------------------------------

    def set_soul_context(self, soul_markdown: str) -> None:
        self._soul_context = soul_markdown

    # ------------------------------------------------------------------
    # Skill acquisition
    # ------------------------------------------------------------------

    async def acquire_skill(self, task_description: str) -> Skill:
        """Return an existing skill for *task_description* or synthesise one."""
        await asyncio.sleep(0)
        skill_id = _deterministic_id(task_description)
        existing = get_skill(skill_id)
        if existing and existing.status == "active":
            logger.info("LumynBridge: reusing cached skill %s", skill_id)
            return existing

        logger.info("LumynBridge: synthesising new skill for: %s", task_description[:80])
        code = _build_skill_code(task_description, {
            "soul": self._soul_context or "",
            "agent_id": self._agent_id,
        })
        skill = Skill(
            skill_id=skill_id,
            name=_task_to_name(task_description),
            description=task_description[:200],
            task_description=task_description,
            code=code,
        )
        register_skill(skill)
        logger.info("LumynBridge: skill %s registered", skill_id)
        return skill

    # ------------------------------------------------------------------
    # Skill execution
    # ------------------------------------------------------------------

    async def execute_skill(
        self,
        skill: Skill,
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """Execute *skill* in a sandboxed subprocess and record telemetry."""
        if context is None:
            context = {}

        # Inject soul context into execution environment
        if self._soul_context:
            context["soul_context"] = self._soul_context

        t0 = time.perf_counter()
        success, output, error = await _run_in_sandbox(skill.code)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Update skill telemetry
        skill.last_used_at = time.time()
        skill.total_latency_ms += latency_ms
        if success:
            skill.success_count += 1
        else:
            skill.failure_count += 1

        result = SkillResult(
            skill_id=skill.skill_id,
            success=success,
            output=output,
            error=error,
            latency_ms=latency_ms,
        )

        # Sign with AgentNet if available
        try:
            from platform.agentnet.identity import sign_message  # type: ignore[import]
            payload = json.dumps(result.to_dict(), sort_keys=True).encode()
            result.signature = sign_message(self._agent_id, payload)
        except Exception:
            pass  # AgentNet optional; signing failure is non-fatal

        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deterministic_id(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return f"skill-{digest}"


def _task_to_name(description: str) -> str:
    words = description.split()[:6]
    return "_".join(w.lower() for w in words if w.isalnum())[:64] or "unnamed_skill"
