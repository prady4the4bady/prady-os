"""Shared pytest fixtures.

The fixtures here wire up isolated, in-memory versions of every singleton so
tests never touch real YAML files, real HTTP endpoints, or real disk paths.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest
import yaml

from app.audit import AuditLogger, reset_audit_logger
from app.config import ProviderConfig, RoutingPolicyConfig, reset_config_cache
from app.gateway import ModelGateway
from app.policy import RoutingPolicyEngine, reset_policy_engine
from app.registry import ModelRegistry, reset_registry

# ---------------------------------------------------------------------------
# Minimal YAML fixtures written to a temp directory
# ---------------------------------------------------------------------------

ROUTING_POLICY_LOCAL_FIRST = {
    "mode": "local-first",
    "local_timeout_seconds": 5,
    "providers": {
        "ollama": {"base_url": "http://localhost:11434", "timeout_seconds": 5},
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "env_key": "OPENAI_API_KEY",
            "timeout_seconds": 30,
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "env_key": "ANTHROPIC_API_KEY",
            "timeout_seconds": 30,
        },
    },
    "fallback_order": ["openai", "anthropic"],
}

MODEL_REGISTRY_DATA = {
    "models": [
        {
            "id": "llama3.2:3b",
            "provider": "ollama",
            "capabilities": ["chat", "completion"],
            "privacy_level": "private",
            "latency_profile": "fast",
        },
        {
            "id": "gpt-4o",
            "provider": "openai",
            "capabilities": ["chat", "completion"],
            "privacy_level": "cloud",
            "latency_profile": "medium",
        },
        {
            "id": "claude-3-5-sonnet-20241022",
            "provider": "anthropic",
            "capabilities": ["chat", "completion"],
            "privacy_level": "cloud",
            "latency_profile": "medium",
        },
    ]
}

_ROUTING_POLICY_FILENAME = "routing-policy.yaml"


@pytest.fixture()
def config_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Write minimal YAML config files into a temp directory and point the
    GATEWAY_CONFIG_DIR env var at it.  Resets singleton caches after the test.
    """
    (tmp_path / _ROUTING_POLICY_FILENAME).write_text(
        yaml.dump(ROUTING_POLICY_LOCAL_FIRST), encoding="utf-8"
    )
    (tmp_path / "model-registry.yaml").write_text(
        yaml.dump(MODEL_REGISTRY_DATA), encoding="utf-8"
    )

    old = os.environ.get("GATEWAY_CONFIG_DIR")
    os.environ["GATEWAY_CONFIG_DIR"] = str(tmp_path)

    reset_config_cache()
    reset_registry()
    reset_policy_engine()

    yield tmp_path

    # cleanup
    reset_config_cache()
    reset_registry()
    reset_policy_engine()
    if old is None:
        os.environ.pop("GATEWAY_CONFIG_DIR", None)
    else:
        os.environ["GATEWAY_CONFIG_DIR"] = old


@pytest.fixture()
def audit_logger(tmp_path: Path) -> AuditLogger:
    """Return an AuditLogger backed by a temp directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    logger = AuditLogger(log_dir=log_dir)
    return logger


@pytest.fixture()
def policy_local_first(config_dir: Path) -> RoutingPolicyConfig:
    from app.config import load_routing_policy

    return load_routing_policy()


@pytest.fixture()
def policy_local_only(config_dir: Path, tmp_path: Path) -> RoutingPolicyConfig:
    data = {**ROUTING_POLICY_LOCAL_FIRST, "mode": "local-only"}
    (config_dir / _ROUTING_POLICY_FILENAME).write_text(yaml.dump(data), encoding="utf-8")
    reset_config_cache()
    from app.config import load_routing_policy

    return load_routing_policy()


@pytest.fixture()
def policy_cloud_only(config_dir: Path) -> RoutingPolicyConfig:
    data = {**ROUTING_POLICY_LOCAL_FIRST, "mode": "cloud-only"}
    (config_dir / _ROUTING_POLICY_FILENAME).write_text(yaml.dump(data), encoding="utf-8")
    reset_config_cache()
    from app.config import load_routing_policy

    return load_routing_policy()


@pytest.fixture()
def registry(config_dir: Path) -> ModelRegistry:
    return ModelRegistry()


def make_gateway(
    policy_cfg: RoutingPolicyConfig,
    audit: AuditLogger,
) -> ModelGateway:
    engine = RoutingPolicyEngine(policy_cfg)
    return ModelGateway(policy_cfg=policy_cfg, policy_engine=engine, audit=audit)
