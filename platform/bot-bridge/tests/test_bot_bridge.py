"""Tests for platform/bot-bridge/main.py"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx
from fastapi.testclient import TestClient

# Ensure bot tokens are empty (no real network calls)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("DISCORD_BOT_TOKEN", "")

SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from main import app


client = TestClient(app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_bot_status_no_tokens():
    resp = client.get("/bot/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["telegram"]["token_set"] is False
    assert data["discord"]["token_set"] is False


def test_telegram_webhook_ping():
    resp = client.post("/telegram/webhook", json={"ping": True})
    assert resp.status_code == 200


def test_telegram_webhook_unknown_cmd():
    with respx.mock:
        respx.post("https://api.telegram.org/botTEST/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        with patch("main.TELEGRAM_TOKEN", "TEST"):
            resp = client.post(
                "/telegram/webhook",
                json={
                    "message": {
                        "chat": {"id": 12345},
                        "text": "/unknown",
                    }
                },
            )
    assert resp.status_code == 200


def test_telegram_webhook_task_no_args():
    with respx.mock:
        respx.post("https://api.telegram.org/botTEST/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        with patch("main.TELEGRAM_TOKEN", "TEST"):
            resp = client.post(
                "/telegram/webhook",
                json={
                    "message": {
                        "chat": {"id": 99},
                        "text": "/task",
                    }
                },
            )
    assert resp.status_code == 200


def test_discord_webhook_ping():
    with patch("main.DISCORD_TOKEN", "TESTTOKEN"):
        resp = client.post(
            "/discord/webhook",
            json={"type": 1},
            headers={
                "X-Signature-Ed25519": "test",
                "X-Signature-Timestamp": "1234567890",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["type"] == 1


def test_discord_webhook_rejects_no_signature():
    with patch("main.DISCORD_TOKEN", ""):
        resp = client.post(
            "/discord/webhook",
            json={"type": 1},
            headers={},
        )
    assert resp.status_code == 401


def test_discord_task_command():
    with respx.mock:
        respx.post(f"{os.getenv('KRYOS_SWARM_URL', 'http://kryos-swarm:8000')}/swarm/start").mock(
            return_value=httpx.Response(200, json={"swarm_id": "abc123", "status": "running"})
        )
        with patch("main.DISCORD_TOKEN", "TEST"):
            resp = client.post(
                "/discord/webhook",
                json={
                    "type": 2,
                    "data": {
                        "name": "task",
                        "options": [{"name": "goal", "value": "Do something cool"}],
                    },
                },
                headers={
                    "X-Signature-Ed25519": "test",
                    "X-Signature-Timestamp": "1234567890",
                },
            )
    assert resp.status_code == 200
    assert resp.json()["type"] == 4
