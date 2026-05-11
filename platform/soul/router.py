"""FastAPI router for SOUL.md per-user personality endpoints."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from .soul_manager import SoulManager

router = APIRouter(prefix="/soul", tags=["soul"])
_manager = SoulManager()


class SoulUpdateRequest(BaseModel):
    name: str | None = None
    personality: str | None = None
    communication_style: str | None = None
    preferred_model: str | None = None
    skill_preferences: str | None = None
    body: str | None = None


class MemoryAppendRequest(BaseModel):
    interaction: str


@router.get("/{user_id}", summary="Get SOUL.md for a user")
async def get_soul(user_id: str) -> Dict[str, Any]:
    content = _manager.load(user_id)
    parsed = _manager.load_parsed(user_id)
    return {"user_id": user_id, "content": content, "fields": parsed}


@router.put("/{user_id}", summary="Update SOUL.md fields")
async def update_soul(user_id: str, body: SoulUpdateRequest) -> Dict[str, Any]:
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )
    updated = _manager.update(user_id, fields)
    return {"user_id": user_id, "content": updated}


@router.post("/{user_id}/memory", summary="Append interaction to memory summary")
async def append_memory(user_id: str, body: MemoryAppendRequest) -> Dict[str, Any]:
    if not body.interaction.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="interaction must not be empty",
        )
    updated = _manager.append_memory(user_id, body.interaction)
    return {"user_id": user_id, "content": updated}
