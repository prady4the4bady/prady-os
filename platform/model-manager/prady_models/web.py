from __future__ import annotations

from fastapi import FastAPI
import uvicorn

from prady_models.platform_api import create_app as create_platform_app


def create_app() -> FastAPI:
    return create_platform_app()


def run_web(host: str = "127.0.0.1", port: int = 11432) -> None:
    uvicorn.run(create_app(), host=host, port=port)
