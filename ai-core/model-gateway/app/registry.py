"""Model registry: loads model-registry.yaml and answers lookup queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config import load_model_registry_data


@dataclass
class ModelEntry:
    id: str
    provider: str
    capabilities: List[str] = field(default_factory=list)
    privacy_level: str = "cloud"   # private | internal | cloud
    latency_profile: str = "medium"  # fast | medium | slow
    user_pullable: bool = False
    checksum: Optional[str] = None


class ModelRegistry:
    """In-memory model registry populated from model-registry.yaml."""

    def __init__(self) -> None:
        self._models: Dict[str, ModelEntry] = {}
        self._load()

    def _load(self) -> None:
        data = load_model_registry_data()
        for item in data.get("models") or []:
            entry = ModelEntry(
                id=item["id"],
                provider=item["provider"],
                capabilities=item.get("capabilities") or [],
                privacy_level=item.get("privacy_level", "cloud"),
                latency_profile=item.get("latency_profile", "medium"),
                user_pullable=bool(item.get("user_pullable", False)),
                checksum=item.get("checksum"),
            )
            self._models[entry.id] = entry

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def lookup(self, model_id: str) -> Optional[ModelEntry]:
        """Return the ModelEntry for *model_id*, or None if not registered."""
        return self._models.get(model_id)

    def all(self) -> List[ModelEntry]:
        """Return all registered models."""
        return list(self._models.values())

    def by_provider(self, provider: str) -> List[ModelEntry]:
        """Return all models registered to *provider*."""
        return [m for m in self._models.values() if m.provider == provider]

    def reload(self) -> None:
        """Re-read model-registry.yaml (useful after hot-reload)."""
        from app.config import load_model_registry_data as lmrd, reset_config_cache
        reset_config_cache()
        self._models.clear()
        self._load()

    def __len__(self) -> int:
        return len(self._models)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the singleton – useful in tests."""
    global _registry
    _registry = None
