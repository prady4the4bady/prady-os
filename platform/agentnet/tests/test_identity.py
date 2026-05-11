"""Tests for platform/agentnet/identity.py"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from agentnet.identity import (
    AgentIdentity,
    generate_identity,
    get_all_public_keys,
    sign_message,
    verify_message,
)


@pytest.fixture
def tmp_keys(tmp_path, monkeypatch):
    """Redirect key storage to a temp dir."""
    monkeypatch.setenv("AGENTNET_KEY_DIR", str(tmp_path))
    # Reset module-level cache
    from agentnet import identity as _id_mod
    _id_mod._identities.clear()
    yield tmp_path
    _id_mod._identities.clear()


def test_generate_identity_creates_keys(tmp_keys):
    ident = generate_identity("test-agent-1")
    assert isinstance(ident, AgentIdentity)
    assert ident.agent_id == "test-agent-1"
    assert ident.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert ident.private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")


def test_generate_identity_idempotent(tmp_keys):
    ident1 = generate_identity("idem-agent")
    ident2 = generate_identity("idem-agent")
    assert ident1.public_key_pem == ident2.public_key_pem


def test_generate_identity_priv_key_permissions(tmp_keys):
    generate_identity("perm-agent")
    priv_path = tmp_keys / "perm-agent.priv"
    if os.name != "nt":  # skip on Windows
        mode = oct(priv_path.stat().st_mode)[-3:]
        assert mode == "600", f"Expected 600, got {mode}"


def test_sign_and_verify(tmp_keys):
    ident = generate_identity("sign-agent")
    payload = b"hello kryos"
    sig = sign_message("sign-agent", payload)
    assert isinstance(sig, str)  # base64 encoded
    assert verify_message(ident.public_key_pem, payload, sig)


def test_verify_fails_with_wrong_payload(tmp_keys):
    ident = generate_identity("verify-agent")
    payload = b"original"
    sig = sign_message("verify-agent", payload)
    assert not verify_message(ident.public_key_pem, b"tampered", sig)


def test_verify_fails_with_wrong_key(tmp_keys):
    generate_identity("agent-a")
    ident2 = generate_identity("agent-b")
    payload = b"test"
    sig = sign_message("agent-a", payload)
    assert not verify_message(ident2.public_key_pem, payload, sig)


def test_get_all_public_keys(tmp_keys):
    generate_identity("pk-agent-1")
    generate_identity("pk-agent-2")
    keys = get_all_public_keys()
    agent_ids = [k["agent_id"] for k in keys]
    assert "pk-agent-1" in agent_ids
    assert "pk-agent-2" in agent_ids
    for k in keys:
        assert k["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----")
