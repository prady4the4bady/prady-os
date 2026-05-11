from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).parents[3]
LUMYN_DIR = REPO_ROOT / "platform" / "lumyn-bridge"
if str(LUMYN_DIR) not in sys.path:
    sys.path.insert(0, str(LUMYN_DIR))

import lumyn_bridge as bridge


@pytest.fixture()
def lumyn_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    policy_path = tmp_path / "lumyn_policy.yaml"
    policy_path.write_text(
        "name: lumyn-policy\n"
        "version: '1.0'\n"
        "allowed_task_types:\n"
        "  - general\n"
        "  - automation\n"
        "blocked_keywords:\n"
        "  - blocked\n"
        "max_task_duration_s: 120\n"
        "require_user_confirmation_for:\n"
        "  - file_delete\n"
        "model_sources_allowed:\n"
        "  - huggingface\n"
        "  - github\n"
        "  - ollama\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LUMYN_POLICY_PATH", str(policy_path))
    return policy_path


@pytest.fixture()
def lumyn_runtime_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models_dir = tmp_path / "models"
    skills_dir = tmp_path / "skills"
    registry_file = models_dir / "registry.json"

    monkeypatch.setattr(bridge, "MODELS_DIR", models_dir)
    monkeypatch.setattr(bridge, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(bridge, "REGISTRY_FILE", registry_file)
    bridge._running_tasks.clear()
    bridge._ensure_runtime_dirs()


@pytest_asyncio.fixture()
async def client(lumyn_policy: Path, lumyn_runtime_dirs: None) -> AsyncClient:
    transport = ASGITransport(app=bridge.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_task_dispatch_default_model(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        stdout = json.dumps({"message": "ok-default"})

    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: Proc())
    response = await client.post("/lumyn/task", json={"task": "Do thing", "model_id": "lumyn-default", "context": {"task_type": "general"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "lumyn-agent"
    assert payload["result"]["message"] == "ok-default"


@pytest.mark.asyncio
async def test_task_dispatch_custom_model(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        stdout = json.dumps({"message": "ok-custom"})

    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: Proc())
    response = await client.post("/lumyn/task", json={"task": "Do custom", "model_id": "nous-lumyn", "context": {"task_type": "general"}})
    assert response.status_code == 200
    assert response.json()["result"]["message"] == "ok-custom"


@pytest.mark.asyncio
async def test_model_pull_huggingface(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_snapshot_download(repo_id: str, local_dir: str, local_dir_use_symlinks: bool) -> str:
        captured["repo_id"] = repo_id
        captured["local_dir"] = local_dir
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        (Path(local_dir) / "weights.gguf").write_text("x", encoding="utf-8")
        return local_dir

    import types
    hf_module = types.SimpleNamespace(snapshot_download=fake_snapshot_download)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_module)

    response = await client.post(
        "/lumyn/model/pull",
        json={"source": "huggingface", "url": "https://huggingface.co/NousResearch/Lumyn-2-Pro-Llama-3-8B"},
    )
    assert response.status_code == 200
    assert captured["repo_id"] == "NousResearch/Lumyn-2-Pro-Llama-3-8B"


@pytest.mark.asyncio
async def test_model_pull_github(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRepo:
        @staticmethod
        def clone_from(url: str, target: str) -> None:
            Path(target).mkdir(parents=True, exist_ok=True)
            (Path(target) / "README.md").write_text("ok", encoding="utf-8")

    import types
    git_module = types.SimpleNamespace(Repo=FakeRepo)
    monkeypatch.setitem(sys.modules, "git", git_module)

    response = await client.post(
        "/lumyn/model/pull",
        json={"source": "github", "url": "https://github.com/NousResearch/Lumyn"},
    )
    assert response.status_code == 200
    assert response.json()["model"]["source"] == "github"


@pytest.mark.asyncio
async def test_policy_block(client: AsyncClient) -> None:
    response = await client.post("/lumyn/task", json={"task": "run blocked command", "model_id": "nous", "context": {"task_type": "general"}})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_model_list(client: AsyncClient) -> None:
    registry = bridge._load_registry()
    registry["models"].append(
        {
            "id": "seed-model",
            "source": "github",
            "url": "https://github.com/example/model",
            "path": str(bridge.MODELS_DIR / "seed-model"),
            "status": "ready",
            "updated_at": 0.0,
        }
    )
    (bridge.MODELS_DIR / "seed-model").mkdir(parents=True, exist_ok=True)
    (bridge.MODELS_DIR / "seed-model" / "weights.gguf").write_bytes(b"abc")
    bridge._save_registry(registry)

    response = await client.get("/lumyn/models")
    assert response.status_code == 200
    assert len(response.json()["models"]) >= 1


@pytest.mark.asyncio
async def test_model_delete(client: AsyncClient) -> None:
    target = bridge.MODELS_DIR / "delete-me"
    target.mkdir(parents=True, exist_ok=True)
    (target / "x.bin").write_bytes(b"x")
    bridge._register_model("delete-me", "github", "https://github.com/x/y", target)

    response = await client.delete("/lumyn/models/delete-me")
    assert response.status_code == 200
    assert response.json()["deleted"] == "delete-me"
    assert not target.exists()


@pytest.mark.asyncio
async def test_skill_list(client: AsyncClient) -> None:
    (bridge.SKILLS_DIR / "alpha.yaml").write_text("name: alpha\n", encoding="utf-8")
    response = await client.post("/lumyn/skills", json={"action": "list"})
    assert response.status_code == 200
    assert "alpha.yaml" in response.json()["skills"]
