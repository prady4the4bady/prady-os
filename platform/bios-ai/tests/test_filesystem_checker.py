from __future__ import annotations

import os
import platform
import stat
from pathlib import Path

import pytest

from filesystem_checker import CheckItem, FilesystemChecker


@pytest.mark.asyncio
async def test_scan_detects_broken_symlink(tmp_path: Path):
    if platform.system() == "Windows":
        pytest.skip("Windows symlink creation may require elevated privileges")

    root = tmp_path / "var" / "kryos"
    root.mkdir(parents=True)
    broken = root / "broken-link"
    broken.symlink_to(root / "missing-target")

    checker = FilesystemChecker(roots=[tmp_path])
    items = await checker.scan()

    assert any(i.issue_type == "broken_symlink" for i in items)


def test_classify_zone():
    checker = FilesystemChecker()
    assert checker.classify_zone("/var/kryos/test.conf") == "free"
    assert checker.classify_zone("/home/user/test.conf") == "ask"
    assert checker.classify_zone("/etc/passwd") == "never"


@pytest.mark.asyncio
async def test_repair_free_zone_applies(tmp_path: Path):
    file_path = tmp_path / "tmp" / "stale.lock"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("lock", encoding="utf-8")

    checker = FilesystemChecker(roots=[tmp_path])
    item = CheckItem(
        item_id="1",
        path=str(file_path),
        issue_type="orphan_lock",
        action="remove_lock",
        zone="free",
    )

    result = await checker.repair(item)
    assert result.status == "applied"
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_repair_ask_zone_pending(tmp_path: Path):
    file_path = tmp_path / "home" / "user" / "app.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}", encoding="utf-8")

    checker = FilesystemChecker(roots=[tmp_path])
    item = CheckItem(
        item_id="2",
        path=str(file_path),
        issue_type="invalid_config",
        action="quarantine_config",
        zone="ask",
    )

    result = await checker.repair(item)
    assert result.status == "pending_approval"
    assert file_path.exists()


@pytest.mark.asyncio
async def test_repair_never_zone_blocked():
    checker = FilesystemChecker()
    item = CheckItem(
        item_id="3",
        path="/etc/hosts",
        issue_type="invalid_config",
        action="quarantine_config",
        zone="never",
    )

    with pytest.raises(PermissionError):
        await checker.repair(item)


@pytest.mark.asyncio
async def test_repair_restrict_permissions(tmp_path: Path):
    if platform.system() == "Windows":
        pytest.skip("POSIX world-writable bit behavior differs on Windows")

    path = tmp_path / "home" / "user" / "world.txt"
    path.parent.mkdir(parents=True)
    path.write_text("x", encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IWOTH)

    checker = FilesystemChecker(roots=[tmp_path])
    item = CheckItem(
        item_id="4",
        path=str(path),
        issue_type="world_writable_home",
        action="restrict_permissions",
        zone="free",
    )
    result = await checker.repair(item)

    assert result.status == "applied"
    mode = path.stat().st_mode
    assert not bool(mode & stat.S_IWOTH)
