from __future__ import annotations

import pathlib
import shutil

from neila.marketplace import neilahub


def test_neilahub_stages_under_target_root(monkeypatch, tmp_path):
    hub_root = tmp_path / "hub"
    monkeypatch.setattr(neilahub, "get_neilahub_skills_dir", lambda: hub_root)
    summary = neilahub.HubSkillSummary(slug="demo", name="demo", version="1.0.0", files=[{"path": "SKILL.md", "sha256": "x", "size": 1}])
    monkeypatch.setattr(neilahub, "load_catalog", lambda: {"raw_base_url": "https://raw.githubusercontent.com/joi-lab/neilaHub/main"})
    monkeypatch.setattr(neilahub, "_summaries", lambda _catalog: [summary])
    seen = {}

    def fake_download(_summary, _raw_base, staging_dir):
        seen["staging"] = pathlib.Path(staging_dir)
        (staging_dir / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")

    monkeypatch.setattr(neilahub, "_download_skill_files", fake_download)
    result = neilahub.install("demo")
    assert result.ok
    seen["staging"].relative_to(hub_root / ".staging")


def test_neilahub_persists_catalog_dependency_specs(monkeypatch, tmp_path):
    hub_root = tmp_path / "hub"
    monkeypatch.setattr(neilahub, "get_neilahub_skills_dir", lambda: hub_root)
    summary = neilahub.HubSkillSummary(
        slug="duckduckgo",
        name="duckduckgo",
        version="1.0.0",
        files=[{"path": "SKILL.md", "sha256": "x", "size": 1}],
        install_specs=[{"kind": "pip", "package": "ddgs"}],
    )
    monkeypatch.setattr(neilahub, "load_catalog", lambda: {"raw_base_url": "https://raw.githubusercontent.com/joi-lab/neilaHub/main"})
    monkeypatch.setattr(neilahub, "_summaries", lambda _catalog: [summary])

    def fake_download(_summary, _raw_base, staging_dir):
        (staging_dir / "SKILL.md").write_text("---\nname: duckduckgo\n---\n", encoding="utf-8")

    monkeypatch.setattr(neilahub, "_download_skill_files", fake_download)

    result = neilahub.install("duckduckgo")

    assert result.ok
    assert result.provenance["install_specs"]["auto"][0]["package"] == "ddgs"
    assert (hub_root / "duckduckgo" / ".neilahub.json").is_file()


def test_neilahub_preserves_dict_dependency_specs(monkeypatch, tmp_path):
    hub_root = tmp_path / "hub"
    monkeypatch.setattr(neilahub, "get_neilahub_skills_dir", lambda: hub_root)
    summary = neilahub.HubSkillSummary(
        slug="duckduckgo",
        name="duckduckgo",
        version="1.0.0",
        files=[{"path": "SKILL.md", "sha256": "x", "size": 1}],
        install_specs={"python": ["ddgs"]},
    )
    monkeypatch.setattr(neilahub, "load_catalog", lambda: {"raw_base_url": "https://raw.githubusercontent.com/joi-lab/neilaHub/main"})
    monkeypatch.setattr(neilahub, "_summaries", lambda _catalog: [summary])

    def fake_download(_summary, _raw_base, staging_dir):
        (staging_dir / "SKILL.md").write_text("---\nname: duckduckgo\n---\n", encoding="utf-8")

    monkeypatch.setattr(neilahub, "_download_skill_files", fake_download)

    result = neilahub.install("duckduckgo")

    assert result.ok
    assert result.provenance["install_specs"]["auto"][0]["package"] == "ddgs"
    assert summary.to_dict()["install_specs"] == {"python": ["ddgs"]}


def test_neilahub_atomic_land_restores_old_on_move_failure(monkeypatch, tmp_path):
    target = tmp_path / "demo"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")

    def boom(_src, _dst):
        raise OSError("boom")

    monkeypatch.setattr(shutil, "move", boom)
    try:
        neilahub._land_atomic(staging, target)
    except OSError:
        pass
    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (target / "new.txt").exists()


def test_neilahub_rejects_windows_and_review_opaque_paths():
    for value in (
        "..\\evil",
        "..\\..\\evil",
        "C:\\evil",
        "node_modules/dep/index.js",
        ".neila_env/bin/tool",
        "__pycache__/plugin.cpython-39.pyc",
        "plugin.pyc",
        "native.so",
        "module.wasm",
    ):
        try:
            neilahub._safe_rel(value)
        except Exception:
            continue
        raise AssertionError(f"expected unsafe path rejection for {value!r}")


