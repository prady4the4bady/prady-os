"""Regression tests for issue #185 — gitignore protection on `AHNIS init`.

Issue #185 reports that `AHNIS init <dir>` writes `AHNIS.yaml` and
`entities.json` into the project root, where they could be committed by
accident. The fix adds `_ensure_AHNIS_files_gitignored()` which appends
the two filenames to `.gitignore` when `<dir>` is a git repository.
"""

from pathlib import Path

from AHNIS.cli import _ensure_AHNIS_files_gitignored


def _git_init(path: Path) -> None:
    """Mark a directory as a git repo without invoking git itself."""
    (path / ".git").mkdir()


def test_no_op_when_not_a_git_repo(tmp_path):
    assert _ensure_AHNIS_files_gitignored(tmp_path) is False
    assert not (tmp_path / ".gitignore").exists()


def test_creates_gitignore_with_both_entries(tmp_path):
    _git_init(tmp_path)
    assert _ensure_AHNIS_files_gitignored(tmp_path) is True
    contents = (tmp_path / ".gitignore").read_text()
    assert "AHNIS.yaml" in contents
    assert "entities.json" in contents
    assert "issue #185" in contents


def test_appends_only_missing_entries(tmp_path):
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\nAHNIS.yaml\n")
    assert _ensure_AHNIS_files_gitignored(tmp_path) is True
    contents = (tmp_path / ".gitignore").read_text()
    # AHNIS.yaml must not be duplicated
    assert contents.count("AHNIS.yaml") == 1
    # entities.json was missing → must now be present
    assert "entities.json" in contents
    # original entries preserved
    assert "node_modules/" in contents


def test_idempotent_when_both_already_present(tmp_path):
    _git_init(tmp_path)
    initial = "AHNIS.yaml\nentities.json\n"
    (tmp_path / ".gitignore").write_text(initial)
    assert _ensure_AHNIS_files_gitignored(tmp_path) is False
    assert (tmp_path / ".gitignore").read_text() == initial


def test_handles_gitignore_without_trailing_newline(tmp_path):
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text("dist")  # no trailing newline
    assert _ensure_AHNIS_files_gitignored(tmp_path) is True
    contents = (tmp_path / ".gitignore").read_text()
    # Original entry preserved on its own line, not glued to the new block
    assert "dist\n" in contents
    assert "AHNIS.yaml" in contents
    assert "entities.json" in contents
