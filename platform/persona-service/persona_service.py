from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import aiosqlite
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

_SHARED_PATH = Path(__file__).resolve().parents[1] / "shared"
if str(_SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(_SHARED_PATH))

from auth_middleware import require_auth

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "persona.db"
NOTIFICATION_BUS_URL = os.environ.get("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
SECURITY_POLICY_URL = os.environ.get("SECURITY_POLICY_URL", "http://security-policy:8117")
VYREX_URL = os.environ.get("VYREX_URL", "http://vyrex-proxy:8105")
MEMORY_SERVICE_URL = os.environ.get("MEMORY_SERVICE_URL", "http://memory-service:8108")
_PERSONA_NOT_FOUND_DETAIL = "persona not found"

MemoryPolicy = Literal["aggressive", "balanced", "minimal"]


class PersonaCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    avatar_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    system_prompt: str = Field(min_length=8, max_length=5000)
    preferred_model_id: str = Field(min_length=1, max_length=120)
    memory_policy: MemoryPolicy = "balanced"
    tags: list[str] = Field(default_factory=list, max_length=20)


class PersonaPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    avatar_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    system_prompt: str | None = Field(default=None, min_length=8, max_length=5000)
    preferred_model_id: str | None = Field(default=None, min_length=1, max_length=120)
    memory_policy: MemoryPolicy | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


class LegacyPersonaCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    system_prompt: str = Field(min_length=8, max_length=5000)
    model_id: str = Field(min_length=1, max_length=120)
    memory_scope: str = Field(default="balanced", min_length=1, max_length=32)


class LegacyPersonaPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    system_prompt: str | None = Field(default=None, min_length=8, max_length=5000)
    model_id: str | None = Field(default=None, min_length=1, max_length=120)
    memory_scope: str | None = Field(default=None, min_length=1, max_length=32)


class PersonaResponse(BaseModel):
    id: str
    name: str
    avatar_color: str
    system_prompt: str
    preferred_model_id: str
    memory_policy: MemoryPolicy
    tags: list[str]
    compressed_summary: str | None
    archived: bool
    created_at: str
    updated_at: str
    last_activated_at: str | None
    activation_count: int
    is_active: bool


class TopicCount(BaseModel):
    topic: str
    count: int


class MemorySummaryResponse(BaseModel):
    total_memories: int
    oldest_memory: str | None
    newest_memory: str | None
    top_topics: list[TopicCount]
    compression_ratio: float


class CompressMemoryResponse(BaseModel):
    accepted: bool
    persona_id: str
    status: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _to_persona(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "avatar_color": row["avatar_color"],
        "system_prompt": row["system_prompt"],
        "preferred_model_id": row["preferred_model_id"],
        "memory_policy": row["memory_policy"],
        "tags": json.loads(row["tags_json"] or "[]"),
        "compressed_summary": row["compressed_summary"],
        "archived": bool(row["archived"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_activated_at": row["last_activated_at"],
        "activation_count": int(row["activation_count"] or 0),
        "is_active": bool(row["is_active"]),
    }


def _extract_memory_window(memories: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    oldest: str | None = None
    newest: str | None = None
    for item in memories:
        created = str(item.get("created_at") or "")
        if not created:
            continue
        if oldest is None or created < oldest:
            oldest = created
        if newest is None or created > newest:
            newest = created
    return oldest, newest


def _compression_ratio(raw_chars: int, compressed_chars: int) -> float:
    if raw_chars <= 0:
        return 1.0
    if compressed_chars <= 0:
        return 1.0
    return round(min(compressed_chars / raw_chars, 1.0), 4)


def _top_topics(topics: list[dict[str, Any]]) -> list[TopicCount]:
    return [
        TopicCount(topic=str(item.get("topic", "")), count=int(item.get("count", 0)))
        for item in topics[:5]
        if item.get("topic")
    ]


async def _notify(type_: str, title: str, body: str, severity: str = "info") -> None:
    payload = {
        "type": type_,
        "title": title,
        "body": body,
        "source": "persona-service",
        "severity": severity,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{NOTIFICATION_BUS_URL}/notify", json=payload)
    except httpx.RequestError as exc:
        logger.warning("notification-bus unavailable: %s", exc)


async def _policy_check(subject_id: str, permission: str) -> tuple[bool, str]:
    """Check security policy for a persona action. Fail-open: log warning and allow on error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SECURITY_POLICY_URL}/policies/check",
                json={"subject_type": "persona", "subject_id": subject_id, "permission": permission},
            )
            data = resp.json()
            return bool(data.get("allowed", False)), str(data.get("reason", ""))
    except Exception as exc:
        logger.warning("security-policy unavailable, proceeding fail-open: %s", exc)
        return True, f"fail-open: {exc}"


async def _get_persona_or_404(db: aiosqlite.Connection, persona_id: str) -> dict[str, Any]:
    db.row_factory = aiosqlite.Row
    cur = await db.execute("SELECT * FROM personas WHERE id = ?", (persona_id,))
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        raise HTTPException(status_code=404, detail=_PERSONA_NOT_FOUND_DETAIL)
    return _to_persona(row)


async def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ddl = """
    CREATE TABLE IF NOT EXISTS personas (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      avatar_color TEXT NOT NULL,
      system_prompt TEXT NOT NULL,
      preferred_model_id TEXT NOT NULL,
      memory_policy TEXT NOT NULL,
      tags_json TEXT NOT NULL,
      compressed_summary TEXT,
      archived INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      last_activated_at TEXT,
      activation_count INTEGER NOT NULL DEFAULT 0,
      is_active INTEGER NOT NULL DEFAULT 0
    );

    CREATE UNIQUE INDEX IF NOT EXISTS ux_personas_name_active
      ON personas(name)
      WHERE archived = 0;
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(ddl)
        await db.commit()


async def _run_memory_compression(persona_id: str) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            persona = await _get_persona_or_404(db, persona_id)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{MEMORY_SERVICE_URL}/memories/by-persona/{persona_id}")
        if not resp.is_success:
            logger.warning("memory-service returned %s for compression", resp.status_code)
            return

        payload = resp.json()
        memories = payload.get("memories", []) if isinstance(payload, dict) else []
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        old_texts: list[str] = []
        for item in memories:
            created_at = _parse_iso(str(item.get("created_at") or ""))
            if created_at is not None and created_at < cutoff:
                old_texts.append(str(item.get("content") or ""))

        joined = "\n".join(t for t in old_texts if t.strip())
        compressed = joined[:2000] if joined else ""

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE personas SET compressed_summary = ?, updated_at = ? WHERE id = ?",
                (compressed, _now_iso(), persona_id),
            )
            await db.commit()

        await _notify(
            "persona.memory_compressed",
            f"Memory compressed: {persona['name']}",
            f"compressed_chars={len(compressed)}",
            "success",
        )
    except Exception as exc:
        logger.exception("memory compression failed for %s: %s", persona_id, exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _init_db()
    yield


app = FastAPI(title="Kryos Persona Service", version="2.0.0", lifespan=lifespan)


@app.get("/personas")
async def list_personas() -> dict[str, Any]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM personas WHERE archived = 0 ORDER BY updated_at DESC")
        rows = await cur.fetchall()
        await cur.close()
    personas = [_to_persona(r) for r in rows]
    return {"personas": personas, "total": len(personas)}


@app.post("/personas", response_model=PersonaResponse)
async def create_persona(req: PersonaCreateRequest) -> PersonaResponse:
    await _init_db()
    now = _now_iso()
    persona_id = str(uuid.uuid4())
    tags_json = json.dumps(req.tags)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT INTO personas (
                  id, name, avatar_color, system_prompt, preferred_model_id, memory_policy,
                  tags_json, compressed_summary, archived, created_at, updated_at,
                  last_activated_at, activation_count, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, NULL, 0, 0)
                """,
                (
                    persona_id,
                    req.name,
                    req.avatar_color,
                    req.system_prompt,
                    req.preferred_model_id,
                    req.memory_policy,
                    tags_json,
                    now,
                    now,
                ),
            )
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"persona create failed: {exc}") from exc

        persona = await _get_persona_or_404(db, persona_id)

    await _notify("persona.created", f"Persona created: {req.name}", req.preferred_model_id, "success")
    return PersonaResponse(**persona)


@app.get("/personas/{persona_id}", response_model=PersonaResponse)
async def get_persona(persona_id: str) -> PersonaResponse:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        persona = await _get_persona_or_404(db, persona_id)
    return PersonaResponse(**persona)


@app.patch("/personas/{persona_id}", response_model=PersonaResponse)
async def patch_persona(persona_id: str, req: PersonaPatchRequest) -> PersonaResponse:
    await _init_db()

    updates: list[str] = []
    values: list[Any] = []
    if req.name is not None:
        updates.append("name = ?")
        values.append(req.name)
    if req.avatar_color is not None:
        updates.append("avatar_color = ?")
        values.append(req.avatar_color)
    if req.system_prompt is not None:
        updates.append("system_prompt = ?")
        values.append(req.system_prompt)
    if req.preferred_model_id is not None:
        updates.append("preferred_model_id = ?")
        values.append(req.preferred_model_id)
    if req.memory_policy is not None:
        updates.append("memory_policy = ?")
        values.append(req.memory_policy)
    if req.tags is not None:
        updates.append("tags_json = ?")
        values.append(json.dumps(req.tags))

    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")

    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(persona_id)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute(f"UPDATE personas SET {', '.join(updates)} WHERE id = ?", tuple(values))
        except aiosqlite.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"persona update failed: {exc}") from exc
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=_PERSONA_NOT_FOUND_DETAIL)
        await db.commit()
        persona = await _get_persona_or_404(db, persona_id)

    return PersonaResponse(**persona)


@app.delete("/personas/{persona_id}")
async def archive_persona(persona_id: str) -> dict[str, Any]:
    await _init_db()
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE personas SET archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
            (now, persona_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=_PERSONA_NOT_FOUND_DETAIL)
        await db.commit()
        persona = await _get_persona_or_404(db, persona_id)

    await _notify("persona.deleted", f"Persona archived: {persona['name']}", persona_id, "warning")
    return {"ok": True, "archived": persona_id}


@app.post("/personas/{persona_id}/clone", response_model=PersonaResponse)
async def clone_persona(persona_id: str) -> PersonaResponse:
    await _init_db()
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        original = await _get_persona_or_404(db, persona_id)
        clone_id = str(uuid.uuid4())
        clone_name = f"Copy of {original['name']}"
        await db.execute(
            """
            INSERT INTO personas (
              id, name, avatar_color, system_prompt, preferred_model_id, memory_policy,
              tags_json, compressed_summary, archived, created_at, updated_at,
              last_activated_at, activation_count, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 0, 0)
            """,
            (
                clone_id,
                clone_name,
                original["avatar_color"],
                original["system_prompt"],
                original["preferred_model_id"],
                original["memory_policy"],
                json.dumps(original["tags"]),
                original["compressed_summary"],
                now,
                now,
            ),
        )
        await db.commit()
        clone = await _get_persona_or_404(db, clone_id)

    return PersonaResponse(**clone)


@app.post("/personas/{persona_id}/activate")
async def activate_persona(
    persona_id: str,
    _current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    allowed, reason = await _policy_check(persona_id, "persona-activation")
    if not allowed:
        logger.warning("policy denied persona-activation for %s: %s — proceeding fail-open", persona_id, reason)
    await _init_db()
    now = _now_iso()

    async with aiosqlite.connect(DB_PATH) as db:
        await _get_persona_or_404(db, persona_id)

        await db.execute("UPDATE personas SET is_active = 0, updated_at = ? WHERE is_active = 1", (now,))
        await db.execute(
            """
            UPDATE personas
            SET is_active = 1,
                updated_at = ?,
                last_activated_at = ?,
                activation_count = activation_count + 1
            WHERE id = ?
            """,
            (now, now, persona_id),
        )
        await db.commit()
        active = await _get_persona_or_404(db, persona_id)

    hot_swap: dict[str, Any] = {"attempted": False, "ok": False}
    preferred = active["preferred_model_id"]
    if preferred:
        hot_swap["attempted"] = True
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{VYREX_URL}/active-model",
                    json={"model_id": preferred, "model_path": f"/models/{preferred}"},
                )
            hot_swap["ok"] = resp.is_success
            if not resp.is_success:
                hot_swap["error"] = f"vyrex status {resp.status_code}"
        except httpx.RequestError as exc:
            hot_swap["ok"] = False
            hot_swap["error"] = str(exc)
            logger.warning("vyrex hot-swap failed for %s: %s", preferred, exc)

    await _notify(
        "persona.activated",
        f"Persona activated: {active['name']}",
        f"preferred_model_id={preferred}",
        "success",
    )

    return {"ok": True, "active": active, "hot_swap": hot_swap}


@app.get("/personas/{persona_id}/memory-summary", response_model=MemorySummaryResponse)
async def persona_memory_summary(persona_id: str) -> MemorySummaryResponse:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        persona = await _get_persona_or_404(db, persona_id)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            mem_resp = await client.get(f"{MEMORY_SERVICE_URL}/memories/by-persona/{persona_id}")
            topic_resp = await client.get(f"{MEMORY_SERVICE_URL}/memories/topics/{persona_id}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"memory-service unavailable: {exc}") from exc

    if not mem_resp.is_success:
        raise HTTPException(status_code=502, detail=f"memory-service error: {mem_resp.status_code}")
    if not topic_resp.is_success:
        raise HTTPException(status_code=502, detail=f"memory-service error: {topic_resp.status_code}")

    memories = mem_resp.json().get("memories", [])
    topics = topic_resp.json().get("topics", [])

    oldest, newest = _extract_memory_window(memories)

    raw_chars = sum(len(str(m.get("content") or "")) for m in memories)
    compressed = persona.get("compressed_summary") or ""
    compressed_chars = len(compressed)
    ratio = _compression_ratio(raw_chars, compressed_chars)

    top_topics = _top_topics(topics)

    return MemorySummaryResponse(
        total_memories=len(memories),
        oldest_memory=oldest,
        newest_memory=newest,
        top_topics=top_topics,
        compression_ratio=ratio,
    )


@app.post("/personas/{persona_id}/compress-memory", response_model=CompressMemoryResponse, status_code=202)
async def compress_persona_memory(persona_id: str, background_tasks: BackgroundTasks) -> CompressMemoryResponse:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await _get_persona_or_404(db, persona_id)

    background_tasks.add_task(_run_memory_compression, persona_id)
    return CompressMemoryResponse(accepted=True, persona_id=persona_id, status="queued")


@app.get("/health")
async def health() -> dict[str, Any]:
    await _init_db()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

@app.get("/persona")
async def legacy_list_persona() -> dict[str, Any]:
    data = await list_personas()
    mapped = []
    for p in data.get("personas", []):
        item = dict(p)
        item["model_id"] = item.get("preferred_model_id")
        item["memory_scope"] = item.get("memory_policy")
        mapped.append(item)
    return {"personas": mapped, "total": len(mapped)}


@app.post("/persona")
async def legacy_create_persona(req: LegacyPersonaCreateRequest) -> dict[str, Any]:
    mapped = PersonaCreateRequest(
        name=req.name,
        avatar_color="#5A67D8",
        system_prompt=req.system_prompt,
        preferred_model_id=req.model_id,
        memory_policy="balanced" if req.memory_scope not in {"aggressive", "minimal"} else req.memory_scope,
        tags=["legacy"],
    )
    persona = await create_persona(mapped)
    out = persona.model_dump()
    out["model_id"] = out["preferred_model_id"]
    out["memory_scope"] = out["memory_policy"]
    return out


@app.get("/persona/active")
async def legacy_get_active() -> dict[str, Any]:
    rows = await list_personas()
    active = next((p for p in rows["personas"] if p.get("is_active")), None)
    return {"active": active}


@app.get("/persona/{persona_id}")
async def legacy_get_persona(persona_id: str) -> dict[str, Any]:
    out = (await get_persona(persona_id)).model_dump()
    out["model_id"] = out["preferred_model_id"]
    out["memory_scope"] = out["memory_policy"]
    return out


@app.patch("/persona/{persona_id}")
async def legacy_patch_persona(persona_id: str, req: LegacyPersonaPatchRequest) -> dict[str, Any]:
    mapped = PersonaPatchRequest(
        name=req.name,
        system_prompt=req.system_prompt,
        preferred_model_id=req.model_id,
        memory_policy="balanced" if req.memory_scope not in {"aggressive", "minimal"} else req.memory_scope,
    )
    out = (await patch_persona(persona_id, mapped)).model_dump()
    out["model_id"] = out["preferred_model_id"]
    out["memory_scope"] = out["memory_policy"]
    return out


@app.delete("/persona/{persona_id}")
async def legacy_delete_persona(persona_id: str) -> dict[str, Any]:
    return await archive_persona(persona_id)


@app.post("/persona/{persona_id}/activate")
async def legacy_activate_persona(
    persona_id: str,
    current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    _ = current_user
    return await activate_persona(persona_id)
