"""
Tests for AgentManager and ModelRegistry.

Run from repo root:
    cd platform/agent-runtime && pytest tests -q
"""

from __future__ import annotations

import sys
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap – allow imports from repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from vyrex.runtime.agent_manager import AgentManager, AgentHandle, _load_policy
from vyrex.runtime.model_registry import ModelRegistry, ModelEntry


# ===========================================================================
# ModelRegistry tests
# ===========================================================================

class TestModelRegistry:
    def setup_method(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.registry = ModelRegistry(cache_dir=Path(self._tmpdir))

    # ------------------------------------------------------------------

    def test_register_stores_entry(self) -> None:
        entry = self.registry.register("llama3", "hf://meta-llama/Llama-3-8B/llama3.gguf")
        assert entry.model_id == "llama3"
        assert entry.status == "registered"

    def test_get_returns_entry(self) -> None:
        self.registry.register("phi3", "hf://microsoft/phi-3/phi3.gguf")
        entry = self.registry.get("phi3")
        assert entry is not None
        assert entry.source_url.startswith("hf://")

    def test_get_missing_returns_none(self) -> None:
        assert self.registry.get("no-such-model") is None

    def test_list_available_empty(self) -> None:
        assert self.registry.list_available() == []

    def test_list_available_returns_all(self) -> None:
        self.registry.register("a", "local:///tmp/a.gguf")
        self.registry.register("b", "local:///tmp/b.gguf")
        ids = {e.model_id for e in self.registry.list_available()}
        assert ids == {"a", "b"}

    def test_ensure_local_uses_local_file(self, tmp_path: Path) -> None:
        model_file = tmp_path / "model.gguf"
        model_file.write_bytes(b"\x00" * 64)
        self.registry.register("local-model", f"local://{model_file}")
        dest = self.registry.ensure_local("local-model")
        assert dest.exists()

    def test_ensure_local_raises_for_unknown(self) -> None:
        with pytest.raises(KeyError):
            self.registry.ensure_local("ghost-model")

    def test_ensure_local_already_ready(self, tmp_path: Path) -> None:
        model_file = tmp_path / "cached.gguf"
        model_file.write_bytes(b"\xff" * 32)
        self.registry.register("cached", f"local://{model_file}")
        path1 = self.registry.ensure_local("cached")
        path2 = self.registry.ensure_local("cached")  # second call, should reuse
        assert path1 == path2

    @patch("vyrex.runtime.model_registry.httpx.stream")
    def test_ensure_local_downloads_hf(self, mock_stream, tmp_path) -> None:
        """Verify that hf:// URIs are translated and downloaded via httpx."""
        import io
        # Build a fake streaming context manager
        fake_resp = MagicMock()
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = MagicMock(return_value=False)
        fake_resp.raise_for_status = MagicMock()
        fake_resp.iter_bytes = MagicMock(return_value=iter([b"fake-model-data"]))
        mock_stream.return_value = fake_resp

        registry = ModelRegistry(cache_dir=tmp_path)
        registry.register("hf-model", "hf://org/repo/model.gguf")
        path = registry.ensure_local("hf-model")
        assert path.exists()
        assert mock_stream.called
        called_url = mock_stream.call_args[0][1]
        assert "huggingface.co" in called_url


# ===========================================================================
# AgentManager tests
# ===========================================================================

class TestAgentManager:
    def setup_method(self) -> None:
        self.manager = AgentManager()

    # ------------------------------------------------------------------

    def test_spawn_creates_handle(self) -> None:
        handle = self.manager.spawn_agent("phi3", "task-executor")
        assert handle.agent_id
        assert handle.status == "running"
        assert handle.pid is not None
        # cleanup
        self.manager.kill_agent(handle.agent_id)

    def test_spawn_assigns_unique_ids(self) -> None:
        h1 = self.manager.spawn_agent("phi3", "task-executor")
        h2 = self.manager.spawn_agent("phi3", "task-executor")
        assert h1.agent_id != h2.agent_id
        self.manager.kill_agent(h1.agent_id)
        self.manager.kill_agent(h2.agent_id)

    def test_list_agents_returns_spawned(self) -> None:
        h = self.manager.spawn_agent("phi3", "task-executor")
        handles = self.manager.list_agents()
        ids = [x.agent_id for x in handles]
        assert h.agent_id in ids
        self.manager.kill_agent(h.agent_id)

    def test_kill_stops_agent(self) -> None:
        h = self.manager.spawn_agent("phi3", "task-executor")
        result = self.manager.kill_agent(h.agent_id)
        assert result.status in ("stopped", "killed")
        assert result.stopped_at is not None

    def test_kill_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            self.manager.kill_agent("no-such-id")

    def test_kill_already_dead_is_idempotent(self) -> None:
        h = self.manager.spawn_agent("phi3", "task-executor")
        self.manager.kill_agent(h.agent_id)
        # Second kill should not raise
        result = self.manager.kill_agent(h.agent_id)
        assert result.status in ("stopped", "killed")

    def test_spawn_records_model_and_policy(self) -> None:
        h = self.manager.spawn_agent("mistral-7b", "agent-runtime")
        assert h.model_id == "mistral-7b"
        assert h.policy_id == "agent-runtime"
        self.manager.kill_agent(h.agent_id)

    def test_spawn_sets_started_at(self) -> None:
        before = time.time()
        h = self.manager.spawn_agent("phi3", "task-executor")
        after = time.time()
        assert before <= h.started_at <= after
        self.manager.kill_agent(h.agent_id)


# ===========================================================================
# Policy loading tests
# ===========================================================================

class TestPolicyLoading:
    def test_missing_policy_returns_defaults(self) -> None:
        limits = _load_policy("no-such-policy-xyz")
        assert limits.max_inference_tokens == 4096  # default value

    def test_policy_file_parses(self, tmp_path: Path, monkeypatch) -> None:
        """Write a minimal policy YAML and verify parsing."""
        import vyrex.runtime.agent_manager as am

        policy_dir = tmp_path / "policies"
        policy_dir.mkdir()
        policy_file = policy_dir / "test-policy.yaml"
        policy_file.write_text(
            "name: test-policy\n"
            "version: '1.0'\n"
            "rules:\n"
            "  - id: allow.fs.write\n"
            "    effect: allow\n"
            "    actions: ['fs:write']\n"
            "    resources: ['/tmp/agent/*']\n"
            "limits:\n"
            "  max_inference_tokens: 1024\n"
        )
        monkeypatch.setattr(am, "_POLICY_DIR", policy_dir)
        limits = _load_policy("test-policy")
        assert limits.max_inference_tokens == 1024
        assert limits.allow_fs_write is True
        assert "/tmp/agent/*" in limits.allowed_write_paths


# ===========================================================================
# API integration tests (using TestClient)
# ===========================================================================

class TestAgentAPI:
    def setup_method(self) -> None:
        from fastapi.testclient import TestClient
        # agent_api.py lives in platform/agent-runtime/ — add that to sys.path
        _api_dir = Path(__file__).parents[1]
        if str(_api_dir) not in sys.path:
            sys.path.insert(0, str(_api_dir))
        from agent_api import app  # type: ignore[import]
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_list_agents_empty(self) -> None:
        resp = self.client.get("/agents/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_spawn_and_list(self) -> None:
        resp = self.client.post("/agents/spawn", json={"model_id": "phi3", "policy_id": "task-executor"})
        assert resp.status_code == 201
        agent = resp.json()
        assert agent["status"] == "running"
        agent_id = agent["agent_id"]

        list_resp = self.client.get("/agents/")
        ids = [a["agent_id"] for a in list_resp.json()]
        assert agent_id in ids

        # cleanup
        self.client.delete(f"/agents/{agent_id}")

    def test_kill_agent(self) -> None:
        spawn_resp = self.client.post("/agents/spawn", json={"model_id": "phi3", "policy_id": "task-executor"})
        agent_id = spawn_resp.json()["agent_id"]
        kill_resp = self.client.delete(f"/agents/{agent_id}")
        assert kill_resp.status_code == 200
        assert kill_resp.json()["status"] in ("stopped", "killed")

    def test_kill_unknown_returns_404(self) -> None:
        resp = self.client.delete("/agents/does-not-exist")
        assert resp.status_code == 404

    def test_prompt_unknown_agent_returns_404(self) -> None:
        resp = self.client.post(
            "/agents/ghost-id/prompt",
            json={"text": "hello"},
        )
        assert resp.status_code == 404

    def test_prompt_streams_sse(self) -> None:
        spawn = self.client.post("/agents/spawn", json={"model_id": "phi3", "policy_id": "task-executor"})
        agent_id = spawn.json()["agent_id"]

        with self.client.stream("POST", f"/agents/{agent_id}/prompt", json={"text": "hello"}) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            chunks = list(resp.iter_lines())
            # At least one SSE data line expected from stub
            data_lines = [c for c in chunks if c.startswith("data:")]
            assert len(data_lines) > 0

        self.client.delete(f"/agents/{agent_id}")
