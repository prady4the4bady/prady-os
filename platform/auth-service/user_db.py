from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

DB_PATH = Path(os.environ.get("AUTH_DB_PATH", "/data/auth.db"))
_SELECT_USER_BY_USERNAME_SQL = "SELECT * FROM users WHERE username = ?"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
      username TEXT PRIMARY KEY,
      role TEXT NOT NULL DEFAULT 'guest',
      persona_id TEXT,
      model_id TEXT,
      theme TEXT NOT NULL DEFAULT 'system',
      voice TEXT NOT NULL DEFAULT 'en_US-lessac-medium',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      locked INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS refresh_tokens (
      jti TEXT PRIMARY KEY,
      username TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      revoked INTEGER NOT NULL DEFAULT 0,
      revoked_at TEXT,
      created_at TEXT NOT NULL
    );
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(ddl)
        await db.commit()


async def get_or_create_user(username: str) -> dict[str, Any]:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_SELECT_USER_BY_USERNAME_SQL, (username,))
        row = await cur.fetchone()
        await cur.close()

        if row is None:
            now = _now_iso()
            await db.execute(
                "INSERT INTO users (username, role, persona_id, model_id, theme, voice, created_at, updated_at, locked) VALUES (?, 'guest', NULL, NULL, 'system', 'en_US-lessac-medium', ?, ?, 0)",
                (username, now, now),
            )
            await db.commit()
            cur = await db.execute(_SELECT_USER_BY_USERNAME_SQL, (username,))
            row = await cur.fetchone()
            await cur.close()

        if row is None:
            raise RuntimeError(f"failed to create user record for {username}")

        return dict(row)


async def get_user(username: str) -> dict[str, Any] | None:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(_SELECT_USER_BY_USERNAME_SQL, (username,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None


async def list_users() -> list[dict[str, Any]]:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT username, role, persona_id, model_id, theme, voice, locked, created_at, updated_at FROM users ORDER BY username")
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]


async def set_user_role(username: str, role: str) -> dict[str, Any]:
    await init_db()
    await get_or_create_user(username)
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET role = ?, updated_at = ? WHERE username = ?", (role, now, username))
        await db.commit()
    user = await get_user(username)
    if user is None:
        raise KeyError(username)
    return user


async def get_preferences(username: str) -> dict[str, Any]:
    user = await get_user(username)
    if user is None:
        raise KeyError(username)
    return {
        "username": username,
        "model_id": user.get("model_id"),
        "persona_id": user.get("persona_id"),
        "theme": user.get("theme"),
        "voice": user.get("voice"),
    }


async def update_preferences(username: str, patch: dict[str, Any]) -> dict[str, Any]:
    allowed = {"model_id", "persona_id", "theme", "voice"}
    updates = {k: v for k, v in patch.items() if k in allowed}
    if not updates:
        return await get_preferences(username)

    clauses = []
    values: list[Any] = []
    for key, value in updates.items():
        clauses.append(f"{key} = ?")
        values.append(value)
    clauses.append("updated_at = ?")
    values.append(_now_iso())
    values.append(username)

    sql = f"UPDATE users SET {', '.join(clauses)} WHERE username = ?"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, values)
        await db.commit()

    return await get_preferences(username)


async def store_refresh_token(jti: str, username: str, expires_at: int) -> None:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO refresh_tokens (jti, username, expires_at, revoked, revoked_at, created_at) VALUES (?, ?, ?, 0, NULL, ?)",
            (jti, username, expires_at, _now_iso()),
        )
        await db.commit()


async def revoke_refresh_token(jti: str) -> None:
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE refresh_tokens SET revoked = 1, revoked_at = ? WHERE jti = ?",
            (_now_iso(), jti),
        )
        await db.commit()


async def is_refresh_token_active(jti: str) -> bool:
    await init_db()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT jti FROM refresh_tokens WHERE jti = ? AND revoked = 0 AND expires_at > ?",
            (jti, now_ts),
        )
        row = await cur.fetchone()
        await cur.close()
        return row is not None
