"""Tests for platform/soul/soul_manager.py"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from soul.soul_manager import SoulManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    import soul.soul_manager as sm
    monkeypatch.setattr(sm, "SOUL_DATA_ROOT", tmp_path)
    return SoulManager()


def test_load_returns_default_when_missing(manager):
    content = manager.load("new-user")
    assert "---" in content
    assert "name:" in content


def test_load_parsed_returns_dict(manager):
    parsed = manager.load_parsed("new-user")
    assert isinstance(parsed, dict)
    assert "name" in parsed


def test_update_modifies_field(manager):
    manager.update("user-1", {"name": "Kryos User"})
    parsed = manager.load_parsed("user-1")
    assert parsed["name"] == "Kryos User"


def test_update_creates_file(manager, tmp_path):
    manager.update("user-2", {"personality": "curious"})
    path = tmp_path / "user-2" / "SOUL.md"
    assert path.exists()


def test_append_memory(manager):
    manager.append_memory("user-3", "hello world chat")
    parsed = manager.load_parsed("user-3")
    memories_raw = parsed.get("memory_summary", "[]")
    import json
    memories = json.loads(memories_raw) if isinstance(memories_raw, str) else memories_raw
    assert len(memories) >= 1
    assert "hello world chat" in memories[-1]


def test_memory_pruned_to_20(manager):
    for i in range(25):
        manager.append_memory("user-4", f"msg-{i}")
    parsed = manager.load_parsed("user-4")
    memories_raw = parsed.get("memory_summary", "[]")
    import json
    memories = json.loads(memories_raw) if isinstance(memories_raw, str) else memories_raw
    assert len(memories) <= 20


def test_load_parses_existing_soul(manager, tmp_path):
    path = tmp_path / "user-5" / "SOUL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nname: TestBot\npersonality: helpful\nmemory_summary: []\n---\n\n## Profile\nHello.\n"
    )
    parsed = manager.load_parsed("user-5")
    assert parsed["name"] == "TestBot"
    assert parsed["personality"] == "helpful"


def test_update_preserves_unknown_fields(manager):
    manager.update("user-6", {"custom_field": "value123"})
    parsed = manager.load_parsed("user-6")
    assert parsed.get("custom_field") == "value123"
