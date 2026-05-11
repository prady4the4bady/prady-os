from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import auth_service
from jwt_utils import generate_keypair, sign_token
from user_db import get_or_create_user, init_db, revoke_refresh_token, set_user_role


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    db_path = Path(auth_service.os.environ["AUTH_DB_PATH"])
    if db_path.exists():
        db_path.unlink()
    priv = Path(auth_service.os.environ["JWT_PRIVATE_KEY_PATH"])
    pub = Path(auth_service.os.environ["JWT_PUBLIC_KEY_PATH"])
    if priv.exists():
        priv.unlink()
    if pub.exists():
        pub.unlink()


@pytest.fixture
def client() -> TestClient:
    with TestClient(auth_service.app) as c:
        yield c


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_login_valid_pam_creds(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        resp = client.post("/auth/login", json={"username": "alice", "password": "secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_login_wrong_password(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=False):
        resp = client.post("/auth/login", json={"username": "alice", "password": "bad"})
    assert resp.status_code == 401


def test_refresh_valid_token(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()
    resp = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_revoked_token(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()
    client.post("/auth/logout", json={"refresh_token": login["refresh_token"]})
    resp = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 401


def test_get_users_without_admin_forbidden(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()
    resp = client.get("/users", headers=_auth_header(login["access_token"]))
    assert resp.status_code == 403


def test_patch_user_role_as_admin(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        admin_login = client.post("/auth/login", json={"username": "admin", "password": "secret"}).json()
    
    import asyncio
    asyncio.run(set_user_role("admin", "admin"))

    # Re-login to pick up new role in token
    with patch("auth_service.validate_user_password", return_value=True):
        admin_login = client.post("/auth/login", json={"username": "admin", "password": "secret"}).json()

    with patch("auth_service.validate_user_password", return_value=True):
        client.post("/auth/login", json={"username": "bob", "password": "secret"})

    resp = client.post(
        "/users/bob/role",
        json={"role": "operator"},
        headers=_auth_header(admin_login["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "operator"


def test_get_auth_me_with_valid_token(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()
    resp = client.get("/auth/me", headers=_auth_header(login["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()
    out = client.post("/auth/logout", json={"refresh_token": login["refresh_token"]})
    assert out.status_code == 200
    again = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert again.status_code == 401


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_verify_returns_identity(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()
    resp = client.get("/auth/verify", headers=_auth_header(login["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_patch_preferences_self(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()
    resp = client.patch(
        "/users/alice/prefs",
        json={"theme": "dark", "voice": "en_US-amy-medium"},
        headers=_auth_header(login["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["theme"] == "dark"


def test_refresh_rotation_revokes_old_token(client: TestClient) -> None:
    with patch("auth_service.validate_user_password", return_value=True):
        login = client.post("/auth/login", json={"username": "alice", "password": "secret"}).json()

    refreshed = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200

    old_use = client.post("/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert old_use.status_code == 401
