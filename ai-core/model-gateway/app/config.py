"""Config loader: reads routing-policy.yaml and model-registry.yaml.

Environment variables (all optional):
  GATEWAY_CONFIG_DIR   - absolute path to config directory
                         (defaults to <repo-root>/config relative to this file)
  OLLAMA_BASE_URL      - override the Ollama base URL
  GATEWAY_ROUTING_MODE - override routing mode at runtime
  VYREX_ENABLED     - enable Vyrex middleware (default: false)
  VYREX_ENDPOINT    - NemoShell endpoint URL (default: http://localhost:8000)
  HUGGINGFACE_TOKEN    - token for private/model-gated HF pulls
  MODEL_STORAGE_DIR    - local path for pulled models (default: /opt/kryos/models)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


def _config_dir() -> Path:
    env = os.getenv("GATEWAY_CONFIG_DIR")
    if env:
        return Path(env)
    # app/config.py → ../config/
    return Path(__file__).parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    path = _config_dir() / filename
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------


class ProviderConfig:
    """Runtime configuration for a single backend provider."""

    def __init__(self, name: str, data: dict) -> None:
        self.name = name
        # Allow env-var override for Ollama base URL
        if name == "ollama":
            default_url = data.get("base_url", "http://localhost:11434")
            self.base_url: str = os.getenv("OLLAMA_BASE_URL", default_url).rstrip("/")
        else:
            self.base_url = data.get("base_url", "").rstrip("/")

        self.env_key: Optional[str] = data.get("env_key")
        self.timeout: float = float(data.get("timeout_seconds", 30))

    @property
    def api_key(self) -> Optional[str]:
        """Resolve the API key from environment, returns None if not set."""
        if self.env_key:
            return os.getenv(self.env_key) or None
        return None


# ---------------------------------------------------------------------------
# Routing policy config
# ---------------------------------------------------------------------------


def _parse_bool(value: str, default: bool = False) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class VyrexSettings:
    enabled: bool
    endpoint: str
    huggingface_token: Optional[str]
    model_storage_dir: Path


class RoutingPolicyConfig:
    """Parsed representation of routing-policy.yaml."""

    VALID_MODES = {"local-first", "local-only", "cloud-only"}

    def __init__(self, data: dict) -> None:
        raw_mode = data.get("mode", "local-first")
        # Allow runtime override via env var
        self.mode: str = os.getenv("GATEWAY_ROUTING_MODE", raw_mode)
        self.local_timeout: float = float(data.get("local_timeout_seconds", 10))
        self.fallback_order: List[str] = data.get("fallback_order", ["openai", "anthropic"])

        self.providers: Dict[str, ProviderConfig] = {}
        for name, cfg in (data.get("providers") or {}).items():
            self.providers[name] = ProviderConfig(name, cfg or {})

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        return self.providers.get(name)

    def validate(self) -> None:
        if self.mode not in self.VALID_MODES:
            raise ValueError(
                f"Invalid routing mode '{self.mode}'. "
                f"Expected one of: {sorted(self.VALID_MODES)}"
            )


# ---------------------------------------------------------------------------
# Singleton loaders
# ---------------------------------------------------------------------------

_routing_policy: Optional[RoutingPolicyConfig] = None
_registry_data: Optional[dict] = None


def load_routing_policy(force_reload: bool = False) -> RoutingPolicyConfig:
    """Return (and cache) the routing policy config."""
    global _routing_policy
    if _routing_policy is None or force_reload:
        data = _load_yaml("routing-policy.yaml")
        _routing_policy = RoutingPolicyConfig(data)
        _routing_policy.validate()
    return _routing_policy


def load_model_registry_data(force_reload: bool = False) -> dict:
    """Return (and cache) the raw model registry YAML data."""
    global _registry_data
    if _registry_data is None or force_reload:
        _registry_data = _load_yaml("model-registry.yaml")
    return _registry_data


def load_vyrex_settings() -> VyrexSettings:
    return VyrexSettings(
        enabled=_parse_bool(os.getenv("VYREX_ENABLED", "false"), False),
        endpoint=os.getenv("VYREX_ENDPOINT", "http://localhost:8000").rstrip("/"),
        huggingface_token=os.getenv("HUGGINGFACE_TOKEN") or None,
        model_storage_dir=Path(os.getenv("MODEL_STORAGE_DIR", "/opt/kryos/models")),
    )


def reset_config_cache() -> None:
    """Reset cached config objects. Useful in tests."""
    global _routing_policy, _registry_data
    _routing_policy = None
    _registry_data = None
