from __future__ import annotations

from pathlib import Path

import pytest

from brain_db import BrainDB
from filesystem_checker import CheckItem, FilesystemChecker, RepairResult
from repair_engine import RepairEngine


class FakeChecker(FilesystemChecker):
    def __init__(self) -> None:
        super().__init__(roots=[])

    async def repair(self, item: CheckItem, force: bool = False) -> RepairResult:
        if item.zone == "ask" and not force:
            return RepairResult(
                item_id=item.item_id,
                path=item.path,
                status="pending_approval",
                action=item.action,
                zone=item.zone,
                message="Approval required",
            )
        if item.zone == "never":
            raise PermissionError("never zone")
        return RepairResult(
            item_id=item.item_id,
            path=item.path,
            status="applied",
            action=item.action,
            zone=item.zone,
            message="ok",
        )


@pytest.mark.asyncio
async def test_run_handles_free_and_ask(tmp_path: Path):
    db = BrainDB(tmp_path / "bios.db")
    await db.init()
    checker = FakeChecker()
    engine = RepairEngine(db, checker)

    scan_id = "scan-1"
    await db.create_scan(scan_id)

    items = [
        CheckItem(item_id="a", path="/var/kryos/a.lock", issue_type="orphan_lock", action="remove_lock", zone="free"),
        CheckItem(item_id="b", path="/home/user/.config/a.json", issue_type="invalid_config", action="quarantine_config", zone="ask"),
    ]

    summary = await engine.run(items, audit_url="http://audit", notify_url="http://notify", scan_id=scan_id)

    assert summary.issues_found == 2
    assert summary.issues_fixed == 1
    assert summary.issues_pending_approval == 1


@pytest.mark.asyncio
async def test_apply_approved(tmp_path: Path):
    db = BrainDB(tmp_path / "bios.db")
    await db.init()
    checker = FakeChecker()
    engine = RepairEngine(db, checker)

    await db.add_repair_item(
        item_id="x",
        scan_id="scan-2",
        path="/home/user/file",
        issue_type="invalid_config",
        action="quarantine_config",
        zone="ask",
        status="pending_approval",
        approved=None,
    )

    result = await engine.apply_approved("x", audit_url="http://audit")
    assert result.status == "applied"


@pytest.mark.asyncio
async def test_reject_item(tmp_path: Path):
    db = BrainDB(tmp_path / "bios.db")
    await db.init()
    checker = FakeChecker()
    engine = RepairEngine(db, checker)

    await db.add_repair_item(
        item_id="y",
        scan_id="scan-3",
        path="/home/user/file",
        issue_type="invalid_config",
        action="quarantine_config",
        zone="ask",
        status="pending_approval",
        approved=None,
    )

    await engine.reject_item("y", audit_url="http://audit")
    row = await db.get_repair_item("y")
    assert row is not None
    assert row["status"] == "rejected"
