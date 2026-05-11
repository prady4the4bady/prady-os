from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class TaskRequest(BaseModel):
    capability: str
    payload: dict
    timeout_ms: int = 5000


@app.post("/kryos/task")
async def handle_task(req: TaskRequest) -> dict:
    if req.capability == "get:weather":
        location = req.payload.get("location", "Dubai")
        return {
            "location": location,
            "temp_c": 28,
            "condition": "sunny",
            "humidity_pct": 45,
        }
    if req.capability == "get:forecast":
        location = req.payload.get("location", "Dubai")
        return {
            "location": location,
            "days": [
                {"date": "2026-05-12", "temp_c": 30, "condition": "sunny"},
                {"date": "2026-05-13", "temp_c": 29, "condition": "cloudy"},
                {"date": "2026-05-14", "temp_c": 27, "condition": "hazy"},
            ],
        }
    return {"error": f"Unknown capability: {req.capability}"}


@app.get("/health")
async def health():
    return {"status": "ok", "app": "weather-app"}
