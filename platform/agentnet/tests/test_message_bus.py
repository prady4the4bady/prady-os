"""Tests for platform/agentnet/message_bus.py"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentnet.identity import generate_identity
from agentnet.message_bus import MessageBus, SignedMessage


@pytest.fixture
def tmp_keys(tmp_path, monkeypatch):
    from agentnet import identity as _id_mod
    monkeypatch.setenv("AGENTNET_KEY_DIR", str(tmp_path))
    _id_mod._identities.clear()
    yield tmp_path
    _id_mod._identities.clear()


@pytest.fixture
def bus(tmp_path, tmp_keys):
    return MessageBus()


def test_create_message_fields(bus, tmp_keys):
    generate_identity("sender-1")
    msg = bus.create_message(
        from_agent="sender-1",
        to_agent="receiver-1",
        payload={"action": "greet"},
    )
    assert isinstance(msg, SignedMessage)
    assert msg.from_agent == "sender-1"
    assert msg.to_agent == "receiver-1"
    assert msg.payload == {"action": "greet"}
    assert isinstance(msg.signature, str)
    assert msg.timestamp > 0


def test_receive_message_valid(bus, tmp_keys):
    generate_identity("alice")
    msg = bus.create_message("alice", "bob", {"hello": "world"})
    alice_identity = generate_identity("alice")
    result = bus.receive_message(msg.to_dict(), sender_pub_key_pem=alice_identity.public_key_pem)
    assert result is not None
    assert result.from_agent == "alice"


def test_receive_message_no_pub_key_passes(bus, tmp_keys):
    """Without a sender key, the message is accepted without sig verification."""
    generate_identity("charlie")
    msg = bus.create_message("charlie", "dave", {"val": 42})
    result = bus.receive_message(msg.to_dict())
    assert result is not None


def test_receive_message_tampered_payload(bus, tmp_keys):
    generate_identity("eve")
    msg = bus.create_message("eve", "frank", {"val": 42})
    eve_identity = generate_identity("eve")
    # Tamper with payload in the dict
    d = msg.to_dict()
    d["payload"] = {"val": 99}  # changed
    result = bus.receive_message(d, sender_pub_key_pem=eve_identity.public_key_pem)
    assert result is None


def test_create_message_appends_log(bus, tmp_keys, monkeypatch, tmp_path):
    import agentnet.message_bus as mb
    log_path = tmp_path / "messages.jsonl"
    monkeypatch.setattr(mb, "MESSAGES_LOG", log_path)

    generate_identity("log-sender")
    bus.create_message("log-sender", "log-receiver", {"ping": True})
    assert log_path.exists()
    lines = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1
    assert lines[-1]["from"] == "log-sender"
