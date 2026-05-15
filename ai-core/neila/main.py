"""neila — Desktop Agent Runtime for Prady OS

neila is the renamed neila-desktop integration for Prady OS.
It provides the AI-powered desktop supervisor, skill routing, and
autonomous workflow execution layer, formerly known as neila Desktop.

Integration path: compositor/neila (submodule) → ai-core/neila (service)
Renamed from: neila-desktop
Maintained by: prady4the4bady
"""

import os
import logging
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [neila] %(levelname)s %(message)s",
)
logger = logging.getLogger("neila")

# ── Config ────────────────────────────────────────────────────────────────────
NEILA_PORT = int(os.environ.get("NEILA_PORT", 8090))
NEILA_HOST = os.environ.get("NEILA_HOST", "0.0.0.0")
MODEL_GATEWAY_URL = os.environ.get("MODEL_GATEWAY_URL", "http://model-gateway:8000")
AHNIS_URL = os.environ.get("AHNIS_URL", "http://ahnis:8091")  # Memory service
NEILA_SUBMODULE_PATH = os.environ.get("NEILA_SUBMODULE_PATH", "/app/compositor/neila")


def get_health() -> dict:
    """Health check for neila service."""
    return {
        "service": "neila",
        "status": "ok",
        "version": "1.0.0",
        "formerly": "neila-desktop",
        "model_gateway": MODEL_GATEWAY_URL,
        "ahnis_memory": AHNIS_URL,
    }


def run_skill(
    skill_name: str,
    payload: Optional[dict] = None,
) -> dict:
    """Execute a named skill from the neila skill registry.

    Args:
        skill_name: Name of the skill (e.g. 'weather', 'search', 'code').
        payload: Optional parameters for the skill.

    Returns:
        Skill execution result dict.
    """
    logger.info("Running skill: %s", skill_name)
    # Skill dispatch will delegate to compositor/neila (neila-desktop) skills
    # at runtime via the mounted submodule path.
    return {
        "skill": skill_name,
        "status": "dispatched",
        "submodule": NEILA_SUBMODULE_PATH,
        "payload": payload or {},
    }


if __name__ == "__main__":
    import uvicorn
    from app import create_app  # type: ignore[import]

    app = create_app(model_gateway_url=MODEL_GATEWAY_URL, ahnis_url=AHNIS_URL)
    logger.info("neila service starting on %s:%s", NEILA_HOST, NEILA_PORT)
    uvicorn.run(app, host=NEILA_HOST, port=NEILA_PORT, log_level="info")

