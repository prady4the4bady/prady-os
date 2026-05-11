from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from jwt_utils import generate_keypair, sign_token, verify_token
from pam_bridge import ServiceUnavailableError, validate_user_password
from user_db import (
    get_or_create_user,
    get_preferences,
    get_user,
    init_db,
    is_refresh_token_active,
    list_users,
    revoke_refresh_token,
    set_user_role,
    store_refresh_token,
    update_preferences,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth-service")

ACCESS_EXPIRY_SECONDS = int(os.environ.get("ACCESS_TOKEN_EXPIRY_SECONDS", "900"))
REFRESH_EXPIRY_SECONDS = int(os.environ.get("REFRESH_TOKEN_EXPIRY_SECONDS", str(7 * 24 * 3600)))
USER_NOT_FOUND_DETAIL = "user not found"


class _SecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        if "/run/secrets" in msg:
            record.msg = msg.replace("/run/secrets", "[redacted-secrets-path]")
            record.args = ()
        return True


logger.addFilter(_SecretsFilter())


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class RoleUpdateRequest(BaseModel):
    role: str


class PreferencesPatchRequest(BaseModel):
    model_id: str | None = None
    persona_id: str | None = None
    theme: str | None = None
    voice: str | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    generate_keypair()
    await init_db()
    yield


app = FastAPI(title="Kryos Auth Service", version="1.0.0", lifespan=lifespan)


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid authorization header")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return token


def _build_access_claims(username: str, role: str, session_id: str) -> dict[str, Any]:
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        "sub": username,
        "role": role,
        "session_id": session_id,
        "iat": now,
    }


def _build_refresh_claims(username: str, jti: str) -> dict[str, Any]:
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        "sub": username,
        "jti": jti,
        "iat": now,
    }


async def _issue_tokens(username: str, role: str) -> dict[str, Any]:
    session_id = f"{username}:{uuid.uuid4()}"
    refresh_jti = str(uuid.uuid4())

    access_token = sign_token(
        _build_access_claims(username, role, session_id),
        ACCESS_EXPIRY_SECONDS,
        token_type="access",
    )

    refresh_payload = _build_refresh_claims(username, refresh_jti)
    refresh_token = sign_token(refresh_payload, REFRESH_EXPIRY_SECONDS, token_type="refresh")
    exp = int(datetime.now(timezone.utc).timestamp()) + REFRESH_EXPIRY_SECONDS
    await store_refresh_token(refresh_jti, username, exp)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_EXPIRY_SECONDS,
        "session_id": session_id,
    }


async def require_auth(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = _extract_bearer(authorization)
    payload = verify_token(token, expected_type="access")
    username = str(payload.get("sub", ""))
    if not username:
        raise HTTPException(status_code=401, detail="invalid token")
    user = await get_user(username)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return {
        "username": username,
        "role": payload.get("role", user.get("role", "guest")),
        "session_id": payload.get("session_id"),
    }


def _ensure_admin(current_user: dict[str, Any]) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="insufficient permissions")


def _ensure_admin_or_self(current_user: dict[str, Any], username: str) -> None:
    if current_user.get("role") == "admin":
        return
    if current_user.get("username") != username:
        raise HTTPException(status_code=403, detail="insufficient permissions")


@app.post("/auth/login")
async def login(req: LoginRequest) -> dict[str, Any]:
    try:
        valid = await validate_user_password(req.username, req.password, service="kryos")
    except ServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail="pam service unavailable") from exc

    if not valid:
        raise HTTPException(status_code=401, detail="invalid credentials")

    user = await get_or_create_user(req.username)
    if bool(user.get("locked")):
        raise HTTPException(status_code=423, detail="account locked")

    tokens = await _issue_tokens(req.username, str(user.get("role", "guest")))
    return {
        **tokens,
        "user": {
            "username": req.username,
            "role": user.get("role", "guest"),
            "persona_id": user.get("persona_id"),
            "model_id": user.get("model_id"),
            "theme": user.get("theme"),
            "voice": user.get("voice"),
        },
    }


@app.post("/auth/refresh")
async def refresh(req: RefreshRequest) -> dict[str, Any]:
    payload = verify_token(req.refresh_token, expected_type="refresh")
    jti = str(payload.get("jti", ""))
    username = str(payload.get("sub", ""))
    if not jti or not username:
        raise HTTPException(status_code=401, detail="invalid refresh token")

    if not await is_refresh_token_active(jti):
        raise HTTPException(status_code=401, detail="refresh token revoked or expired")

    await revoke_refresh_token(jti)

    user = await get_user(username)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")

    tokens = await _issue_tokens(username, str(user.get("role", "guest")))
    return tokens


@app.post("/auth/logout")
async def logout(req: LogoutRequest) -> dict[str, Any]:
    payload = verify_token(req.refresh_token, expected_type="refresh")
    jti = str(payload.get("jti", ""))
    if not jti:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    await revoke_refresh_token(jti)
    return {"ok": True}


@app.get("/auth/me")
async def me(current_user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    user = await get_user(current_user["username"])
    if user is None:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_DETAIL)
    return {
        "username": user["username"],
        "role": user["role"],
        "persona_id": user.get("persona_id"),
        "model_id": user.get("model_id"),
        "theme": user.get("theme"),
        "voice": user.get("voice"),
        "session_id": current_user.get("session_id"),
    }


@app.get("/auth/verify")
async def verify(current_user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    return current_user


@app.get("/users")
async def users(current_user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _ensure_admin(current_user)
    entries = await list_users()
    return {"users": entries, "total": len(entries)}


@app.post("/users/{username}/role")
async def update_role(
    username: str,
    req: RoleUpdateRequest,
    current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    _ensure_admin(current_user)
    if req.role not in {"admin", "operator", "guest"}:
        raise HTTPException(status_code=422, detail="invalid role")
    user = await set_user_role(username, req.role)
    return {"username": user["username"], "role": user["role"]}


@app.get("/users/{username}/prefs")
async def user_prefs(username: str, current_user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _ensure_admin_or_self(current_user, username)
    try:
        return await get_preferences(username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_DETAIL) from exc


@app.patch("/users/{username}/prefs")
async def patch_user_prefs(
    username: str,
    req: PreferencesPatchRequest,
    current_user: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    _ensure_admin_or_self(current_user, username)
    try:
        return await update_preferences(username, req.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_DETAIL) from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
