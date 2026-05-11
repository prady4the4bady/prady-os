from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel


class SystemAbout(BaseModel):
    name: str
    version: str
    channel: str
    build: str


app = FastAPI(title="Kryos System Health", version="1.0.0")


def _about() -> SystemAbout:
    return SystemAbout(
        name=os.getenv("RELEASE_NAME", "Prady OS"),
        version=os.getenv("RELEASE_VERSION", "1.0.0"),
        channel=os.getenv("RELEASE_CHANNEL", "stable"),
        build=os.getenv("RELEASE_BUILD", "phase-38"),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/about")
async def system_about() -> SystemAbout:
    return _about()


@app.get("/api/system/health")
async def system_health() -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "status": "healthy",
        "timestamp": now,
        "checks": {
            "oobe": "ok",
            "hardware": "ok",
            "sdk_registry": "ok",
        },
        "release": _about().model_dump(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("system_health_service:app", host="0.0.0.0", port=8021, reload=False)
