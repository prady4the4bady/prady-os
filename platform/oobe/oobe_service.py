from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

CONFIG_DIR = Path(os.getenv("KRYOS_CONFIG_DIR", "/opt/kryos-os/config"))
USER_CONFIG_PATH = CONFIG_DIR / "user.json"
OOBE_MARKER_PATH = CONFIG_DIR / ".oobe_complete"
OOBE_DIST = Path(os.getenv("OOBE_DIST", "/opt/kryos-os/ui/oobe-wizard/dist"))


class UserModel(BaseModel):
    name: str = Field(min_length=1)
    username: str = Field(min_length=3, max_length=20)
    avatar: str = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[a-z0-9_]{3,20}", value):
            raise ValueError("username must match [a-z0-9_]{3,20}")
        return value


class AIModel(BaseModel):
    model: str = Field(min_length=1)
    allow_cloud: bool


class LocaleModel(BaseModel):
    timezone: str = Field(min_length=1)
    language: Literal["English", "Spanish", "French", "German", "Japanese"]
    keyboard: Literal["US", "UK", "German", "French", "Japanese"]


class OOBEPayload(BaseModel):
    user: UserModel
    ai: AIModel
    locale: LocaleModel


app = FastAPI(title="Kryos OOBE Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ASSETS_DIR = OOBE_DIST / "assets"
if ASSETS_DIR.exists():
    app.mount("/oobe/assets", StaticFiles(directory=ASSETS_DIR), name="oobe-assets")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/oobe/status")
async def oobe_status() -> dict[str, bool]:
    return {"complete": OOBE_MARKER_PATH.exists()}


@app.post("/api/oobe/complete")
async def oobe_complete(payload: OOBEPayload) -> dict[str, str]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with USER_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, indent=2)

    os.chmod(USER_CONFIG_PATH, 0o600)
    OOBE_MARKER_PATH.write_text("complete\n", encoding="utf-8")
    os.chmod(OOBE_MARKER_PATH, 0o600)

    return {"status": "ok"}


@app.get("/oobe")
async def oobe_index() -> FileResponse:
    index_path = OOBE_DIST / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="OOBE UI not built")
    return FileResponse(index_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("oobe_service:app", host="0.0.0.0", port=8099, reload=False)
