from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PullRequest(BaseModel):
    source: str = Field(..., description="hf://repo-id or github release URL")


class ModelResponse(BaseModel):
    model_id: str
    name: str
    source: str
    file_path: str
    sha256: str
    quantization: str
    size_gb: float
    pulled_at: datetime
    status: str
    benchmark_score: float | None = None
    tokens_per_sec: float | None = None


class BenchmarkResponse(BaseModel):
    model_id: str
    benchmark_score: float | None = None
    tokens_per_sec: float | None = None
