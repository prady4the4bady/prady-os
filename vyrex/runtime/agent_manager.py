"""
AgentManager – spawn, track, and terminate agent subprocesses.

Each agent runs in its own OS process with policy-enforced resource limits
read from vyrex/policies/<policy_id>.yaml.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_POLICY_DIR = Path(__file__).parents[1] / "policies"
_DEFAULT_TIMEOUT_SECS = 5


@dataclass
class PolicyLimits:
    max_inference_tokens: int = 4096
    allow_network: bool = False
    allow_fs_write: bool = False
    allowed_write_paths: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    inference_quota_per_minute: int = 100


@dataclass
class AgentHandle:
    agent_id: str
    model_id: str
    policy_id: str
    pid: Optional[int]
    _proc: Optional[subprocess.Popen] = field(default=None, repr=False, compare=False)
    status: str = "running"   # running | stopped | killed | error
    started_at: float = field(default_factory=time.time)
    stopped_at: Optional[float] = None
    exit_code: Optional[int] = None


def _load_policy(policy_id: str) -> PolicyLimits:
    """Load and parse a Vyrex YAML policy into PolicyLimits."""
    policy_file = _POLICY_DIR / f"{policy_id}.yaml"
    if not policy_file.exists():
        logger.warning("Policy %s not found – using defaults", policy_id)
        return PolicyLimits()

    with open(policy_file) as fh:
        doc = yaml.safe_load(fh) or {}

    limits = PolicyLimits()
    rules: list[dict] = doc.get("rules", [])
    egress: dict = doc.get("egress", {})

    for rule in rules:
        _apply_policy_rule(limits, rule)

    if isinstance(egress.get("allow_domains"), list):
        limits.allowed_domains = egress["allow_domains"]

    limits_block: dict = doc.get("limits", {})
    _assign_int_limit(limits_block, "max_inference_tokens", lambda value: setattr(limits, "max_inference_tokens", value))
    _assign_int_limit(
        limits_block,
        "inference_quota_per_minute",
        lambda value: setattr(limits, "inference_quota_per_minute", value),
    )

    return limits


def _assign_int_limit(source: dict, key: str, setter: callable) -> None:
    if key in source:
        setter(int(source[key]))


def _apply_policy_rule(limits: PolicyLimits, rule: dict) -> None:
    effect = rule.get("effect", "deny")
    actions = rule.get("actions", [])
    resources = rule.get("resources", [])

    if effect == "allow":
        if "http:*" in actions or "tcp:*" in actions:
            limits.allow_network = True
        if "fs:write" in actions or "fs:create" in actions:
            limits.allow_fs_write = True
            limits.allowed_write_paths.extend(resources)
        return

    if effect == "deny" and "http:*" in actions and resources == ["*"]:
        limits.allow_network = False


class AgentManager:
    """Manage agent subprocesses with policy enforcement."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentHandle] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def spawn_agent(
        self,
        model_id: str,
        policy_id: str,
        *,
        command: Optional[list[str]] = None,
        env_extra: Optional[dict[str, str]] = None,
    ) -> AgentHandle:
        """Spawn a new agent process and return its handle."""
        agent_id = str(uuid.uuid4())
        limits = _load_policy(policy_id)

        agent_env = {**os.environ}
        agent_env.update({
            "AGENT_ID": agent_id,
            "AGENT_MODEL_ID": model_id,
            "AGENT_POLICY_ID": policy_id,
            "AGENT_MAX_TOKENS": str(limits.max_inference_tokens),
            "AGENT_ALLOW_NETWORK": "1" if limits.allow_network else "0",
        })
        if env_extra:
            agent_env.update(env_extra)

        # Default command: echo placeholder (real workload injected at deploy time)
        cmd = command or ["python3", "-c", _AGENT_STUB_CODE]

        try:
            proc = subprocess.Popen(
                cmd,
                env=agent_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
            handle = AgentHandle(
                agent_id=agent_id,
                model_id=model_id,
                policy_id=policy_id,
                pid=proc.pid,
                _proc=proc,
                status="running",
            )
            self._agents[agent_id] = handle
            logger.info("Spawned agent %s (pid=%s, model=%s, policy=%s)", agent_id, proc.pid, model_id, policy_id)
            return handle

        except Exception as exc:
            handle = AgentHandle(
                agent_id=agent_id,
                model_id=model_id,
                policy_id=policy_id,
                pid=None,
                status="error",
            )
            self._agents[agent_id] = handle
            logger.error("Failed to spawn agent %s: %s", agent_id, exc)
            raise RuntimeError(f"Spawn failed for agent {agent_id}: {exc}") from exc

    def list_agents(self) -> list[AgentHandle]:
        """Return all known agent handles after refreshing their statuses."""
        self._refresh_statuses()
        return list(self._agents.values())

    def kill_agent(self, agent_id: str, *, timeout: float = _DEFAULT_TIMEOUT_SECS) -> AgentHandle:
        """
        Gracefully stop an agent: SIGTERM then SIGKILL after *timeout* seconds.
        On Windows (dev/test only) immediately terminates.
        """
        handle = self._agents.get(agent_id)
        if handle is None:
            raise KeyError(f"Unknown agent: {agent_id}")

        if handle.pid is None or handle.status not in ("running",):
            _mark_stopped(handle)
            return handle

        pid = handle.pid
        try:
            _terminate_process(handle, pid)

            if not _wait_for_exit(handle, pid, timeout):
                _force_kill(handle, pid)
                handle.status = "killed"
                logger.warning("Agent %s (pid=%s) did not exit in %.1fs – SIGKILL sent", agent_id, pid, timeout)

        except ProcessLookupError:
            pass  # Already gone

        if handle.status != "killed":
            _mark_stopped(handle)
        else:
            handle.stopped_at = time.time()
        logger.info("Agent %s terminated (status=%s)", agent_id, handle.status)
        return handle

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refresh_statuses(self) -> None:
        for handle in self._agents.values():
            if handle.status != "running" or handle.pid is None:
                continue
            if _is_process_alive(handle, handle.pid):
                continue
            _mark_stopped(handle)


def _mark_stopped(handle: AgentHandle) -> None:
    handle.status = "stopped"
    handle.stopped_at = time.time()


def _terminate_process(handle: AgentHandle, pid: int) -> None:
    if os.name == "nt":
        if handle._proc is not None:
            handle._proc.terminate()
            return
        os.kill(pid, signal.SIGTERM)
        return
    os.killpg(os.getpgid(pid), signal.SIGTERM)


def _wait_for_exit(handle: AgentHandle, pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_process_alive(handle, pid):
            return True
        time.sleep(0.1)
    return False


def _force_kill(handle: AgentHandle, pid: int) -> None:
    try:
        if os.name == "nt":
            if handle._proc is not None:
                handle._proc.kill()
                return
            os.kill(pid, signal.SIGTERM)
            return
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


def _is_process_alive(handle: AgentHandle, pid: int) -> bool:
    try:
        if os.name == "nt" and handle._proc is not None:
            return handle._proc.poll() is None
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


# Minimal Python stub that keeps the process alive briefly for testing
_AGENT_STUB_CODE = (
    "import time, os; "
    "print('agent', os.environ.get('AGENT_ID','?'), 'ready'); "
    "time.sleep(3600)"
)
