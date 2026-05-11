"""Routing policy engine.

Translates the policy mode into an ordered list of backend names to attempt.
The gateway will try them left-to-right and stop on the first success.
"""

from __future__ import annotations

from typing import List, Optional

from app.config import RoutingPolicyConfig, load_routing_policy


class PolicyDecision:
    """Result returned by :meth:`RoutingPolicyEngine.decide`."""

    def __init__(self, allowed: bool, backends: List[str], reason: str) -> None:
        self.allowed = allowed
        # Ordered list of provider names to try (e.g. ["ollama", "openai"])
        self.backends = backends
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"PolicyDecision(allowed={self.allowed}, "
            f"backends={self.backends}, reason={self.reason!r})"
        )


class RoutingPolicyEngine:
    """Derives backend routing decisions from a :class:`RoutingPolicyConfig`."""

    def __init__(self, policy: RoutingPolicyConfig) -> None:
        self.policy = policy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, model_id: str) -> PolicyDecision:
        """Return the routing decision for *model_id*.

        The *model_id* parameter is accepted for future per-model overrides
        (e.g. "this model is cloud-only regardless of policy mode").
        Currently the decision is purely mode-driven.
        """
        mode = self.policy.mode
        model_name = model_id.strip() or "unknown"

        if mode == "local-only":
            return PolicyDecision(
                allowed=True,
                backends=["ollama"],
                reason="local-only: only the Ollama backend is permitted",
            )

        if mode == "local-first":
            backends: List[str] = ["ollama"] + list(self.policy.fallback_order)
            return PolicyDecision(
                allowed=True,
                backends=backends,
                reason="local-first: Ollama attempted first, then cloud fallback order",
            )

        if mode == "cloud-only":
            return PolicyDecision(
                allowed=True,
                backends=list(self.policy.fallback_order),
                reason="cloud-only: local backend skipped",
            )

        # Unknown mode – block and report
        return PolicyDecision(
            allowed=False,
            backends=[],
            reason=f"unknown routing mode '{mode}' for model '{model_name}': request blocked",
        )

    def is_local_only(self) -> bool:
        """Return True when cloud fallback is forbidden."""
        return self.policy.mode == "local-only"

    def ordered_backends(self) -> List[str]:
        """Return the canonical backend order for the current mode."""
        return self.decide("*").backends


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: Optional[RoutingPolicyEngine] = None


def get_policy_engine() -> RoutingPolicyEngine:
    global _engine
    if _engine is None:
        _engine = RoutingPolicyEngine(load_routing_policy())
    return _engine


def reset_policy_engine() -> None:
    """Reset the singleton – useful in tests."""
    global _engine
    _engine = None
