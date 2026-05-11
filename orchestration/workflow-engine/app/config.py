"""Configuration loader — reads env vars with sensible defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"


@dataclass
class Config:
    redis_url: str
    model_gateway_url: str
    playwright_runner_url: str
    log_dir: Path
    gateway_model: str
    planner_model: str
    screen_backend: str
    screen_ocr_enabled: bool
    screen_screenshot_dir: Path
    approval_timeout_seconds: float


def _parse_bool(value: str, default: bool = True) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def load_config() -> Config:
    return Config(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        model_gateway_url=os.getenv(
            "MODEL_GATEWAY_URL", "http://localhost:11430"
        ),
        playwright_runner_url=os.getenv(
            "PLAYWRIGHT_RUNNER_URL", "http://localhost:11432"
        ),
        log_dir=Path(os.getenv("ACTIVITY_LOG_DIR", str(_DEFAULT_LOG_DIR))),
        gateway_model=os.getenv("GATEWAY_MODEL", "llama3.2:3b"),
        planner_model=os.getenv("PLANNER_MODEL", "lumyn-agent"),
        screen_backend=os.getenv("SCREEN_BACKEND", "auto"),
        screen_ocr_enabled=_parse_bool(os.getenv("SCREEN_OCR_ENABLED", "true"), True),
        screen_screenshot_dir=Path(
            os.getenv("SCREEN_SCREENSHOT_DIR", "/tmp/kryos-screenshots")
        ),
        approval_timeout_seconds=float(
            os.getenv("APPROVAL_TIMEOUT_SECONDS", "300")
        ),
    )
