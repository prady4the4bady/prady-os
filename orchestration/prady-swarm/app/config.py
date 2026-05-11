"""Configuration for kryos-swarm service."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_bool(value: str, default: bool = True) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class SwarmConfig:
    max_swarm_agents: int
    swarm_model: str
    workflow_engine_url: str
    model_gateway_url: str
    chromadb_path: Path
    log_level: str


def load_config() -> SwarmConfig:
    return SwarmConfig(
        max_swarm_agents=int(os.getenv("MAX_SWARM_AGENTS", "10")),
        swarm_model=os.getenv("SWARM_MODEL", "lumyn-agent"),
        workflow_engine_url=os.getenv(
            "WORKFLOW_ENGINE_URL", "http://localhost:11431"
        ),
        model_gateway_url=os.getenv(
            "MODEL_GATEWAY_URL", "http://localhost:11430"
        ),
        chromadb_path=Path(os.getenv("CHROMADB_PATH", "/opt/kryos/chromadb")),
        log_level=os.getenv("KRYOS_LOG_LEVEL", "INFO"),
    )
