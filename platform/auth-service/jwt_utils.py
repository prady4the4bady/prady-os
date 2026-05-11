from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

logger = logging.getLogger(__name__)

PRIVATE_KEY_PATH = Path(os.environ.get("JWT_PRIVATE_KEY_PATH", "/run/secrets/kryos-jwt-private.pem"))
PUBLIC_KEY_PATH = Path(os.environ.get("JWT_PUBLIC_KEY_PATH", "/run/secrets/kryos-jwt-public.pem"))


def generate_keypair() -> tuple[Path, Path]:
    PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return PRIVATE_KEY_PATH, PUBLIC_KEY_PATH

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    PRIVATE_KEY_PATH.write_bytes(private_pem)
    PUBLIC_KEY_PATH.write_bytes(public_pem)

    try:
        PRIVATE_KEY_PATH.chmod(0o600)
        PUBLIC_KEY_PATH.chmod(0o644)
    except Exception:
        pass

    return PRIVATE_KEY_PATH, PUBLIC_KEY_PATH


def _read_private_key() -> str:
    if not PRIVATE_KEY_PATH.exists():
        generate_keypair()
    return PRIVATE_KEY_PATH.read_text(encoding="utf-8")


def _read_public_key() -> str:
    if not PUBLIC_KEY_PATH.exists():
        generate_keypair()
    return PUBLIC_KEY_PATH.read_text(encoding="utf-8")


def sign_token(payload: dict[str, Any], expiry_seconds: int, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    claims = dict(payload)
    claims["token_type"] = token_type
    claims["iat"] = int(now.timestamp())
    claims["exp"] = int((now + timedelta(seconds=expiry_seconds)).timestamp())
    return jwt.encode(claims, _read_private_key(), algorithm="RS256")


def verify_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _read_public_key(), algorithms=["RS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    token_type = payload.get("token_type")
    if expected_type is not None and token_type != expected_type:
        raise HTTPException(status_code=401, detail="invalid token type")

    return payload
