from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import HTTPException

import jwt_utils


def test_sign_verify_round_trip() -> None:
    token = jwt_utils.sign_token({"sub": "alice", "role": "guest", "session_id": "alice:1"}, 60, "access")
    payload = jwt_utils.verify_token(token, expected_type="access")
    assert payload["sub"] == "alice"
    assert payload["role"] == "guest"


def test_expired_token_raises_401() -> None:
    token = jwt_utils.sign_token({"sub": "alice"}, -1, "access")
    with pytest.raises(HTTPException) as exc:
        jwt_utils.verify_token(token, expected_type="access")
    assert exc.value.status_code == 401


def test_wrong_key_raises_401(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    monkeypatch.setattr(jwt_utils, "PRIVATE_KEY_PATH", private)
    monkeypatch.setattr(jwt_utils, "PUBLIC_KEY_PATH", public)
    jwt_utils.generate_keypair()
    token = jwt_utils.sign_token({"sub": "alice"}, 60, "access")

    # Regenerate keys so public key changes.
    private.unlink()
    public.unlink()
    jwt_utils.generate_keypair()

    with pytest.raises(HTTPException) as exc:
        jwt_utils.verify_token(token, expected_type="access")
    assert exc.value.status_code == 401


def test_tampered_payload_raises_401() -> None:
    token = jwt_utils.sign_token({"sub": "alice"}, 60, "access")
    tampered = token[:-2] + "ab"
    with pytest.raises(HTTPException) as exc:
        jwt_utils.verify_token(tampered, expected_type="access")
    assert exc.value.status_code == 401


def test_refresh_not_usable_as_access() -> None:
    token = jwt_utils.sign_token({"sub": "alice", "jti": "1"}, 60, "refresh")
    with pytest.raises(HTTPException) as exc:
        jwt_utils.verify_token(token, expected_type="access")
    assert exc.value.status_code == 401


def test_generate_keypair_creates_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    monkeypatch.setattr(jwt_utils, "PRIVATE_KEY_PATH", private)
    monkeypatch.setattr(jwt_utils, "PUBLIC_KEY_PATH", public)

    pvt, pub = jwt_utils.generate_keypair()
    assert pvt.exists()
    assert pub.exists()


def test_verify_without_expected_type_succeeds() -> None:
    token = jwt_utils.sign_token({"sub": "alice"}, 60, "access")
    payload = jwt_utils.verify_token(token)
    assert payload["sub"] == "alice"


def test_iat_and_exp_present() -> None:
    token = jwt_utils.sign_token({"sub": "alice"}, 60, "access")
    payload = jwt_utils.verify_token(token, expected_type="access")
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] > int(time.time())
