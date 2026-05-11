"""Repair orchestration for BIOS AI stage 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from brain_db import BrainDB
from filesystem_checker import CheckItem, FilesystemChecker, RepairResult


@dataclass
class RepairSummary:
    scan_id: str
    issues_found: int
    issues_fixed: int
    issues_pending_approval: int
    items: list[dict[str, Any]]


class RepairEngine:
    def __init__(self, db: BrainDB, checker: FilesystemChecker) -> None:
        self.db = db
        self.checker = checker

    async def run(self, scan_results: list[CheckItem], audit_url: str, notify_url: str, scan_id: str) -> RepairSummary:
        fixed = 0
        pending = 0
        items: list[dict[str, Any]] = []

        for item in scan_results:
            status = "skipped"
            approved: bool | None = None
            message = ""

            if item.zone == "free":
                result = await self.checker.repair(item)
                status = result.status
                message = result.message
                approved = True if status == "applied" else None
                if status == "applied":
                    fixed += 1
                await self._audit_event(audit_url, item, result)

            elif item.zone == "ask":
                status = "pending_approval"
                pending += 1
                await self._notify_approval_request(notify_url, item)
                await self._audit_event(
                    audit_url,
                    item,
                    RepairResult(
                        item_id=item.item_id,
                        path=item.path,
                        status=status,
                        action=item.action,
                        zone=item.zone,
                        message="Waiting for user approval",
                    ),
                )

            elif item.zone == "never":
                status = "blocked_never_zone"
                await self._audit_event(
                    audit_url,
                    item,
                    RepairResult(
                        item_id=item.item_id,
                        path=item.path,
                        status=status,
                        action=item.action,
                        zone=item.zone,
                        message="Never zone is read-only",
                    ),
                )

            await self.db.add_repair_item(
                item_id=item.item_id,
                scan_id=scan_id,
                path=item.path,
                issue_type=item.issue_type,
                action=item.action,
                zone=item.zone,
                status=status,
                approved=approved,
                message=message,
            )

            items.append(
                {
                    "item_id": item.item_id,
                    "path": item.path,
                    "issue_type": item.issue_type,
                    "action": item.action,
                    "zone": item.zone,
                    "approved": approved,
                    "status": status,
                    "message": message,
                }
            )

        return RepairSummary(
            scan_id=scan_id,
            issues_found=len(scan_results),
            issues_fixed=fixed,
            issues_pending_approval=pending,
            items=items,
        )

    async def apply_approved(self, item_id: str, audit_url: str) -> RepairResult:
        row = await self.db.get_repair_item(item_id)
        if not row:
            raise KeyError(f"Unknown item_id: {item_id}")

        item = CheckItem(
            item_id=row["item_id"],
            path=row["path"],
            issue_type=row["issue_type"],
            action=row["action"],
            zone=row["zone"],
            approved=True,
        )

        if item.zone == "never":
            raise PermissionError("Cannot apply repairs in NEVER zone")

        result = await self.checker.repair(item, force=True)
        await self.db.update_repair_item(
            item_id,
            status=result.status,
            approved=(result.status == "applied"),
            message=result.message,
        )
        await self._audit_event(audit_url, item, result)
        return result

    async def reject_item(self, item_id: str, audit_url: str) -> None:
        row = await self.db.get_repair_item(item_id)
        if not row:
            raise KeyError(f"Unknown item_id: {item_id}")

        await self.db.update_repair_item(item_id, status="rejected", approved=False, message="Rejected by user")

        item = CheckItem(
            item_id=row["item_id"],
            path=row["path"],
            issue_type=row["issue_type"],
            action=row["action"],
            zone=row["zone"],
            approved=False,
        )
        await self._audit_event(
            audit_url,
            item,
            RepairResult(
                item_id=item.item_id,
                path=item.path,
                status="rejected",
                action=item.action,
                zone=item.zone,
                message="Rejected by user",
            ),
        )

    async def _audit_event(self, audit_url: str, item: CheckItem, result: RepairResult) -> None:
        payload = {
            "service": "bios-ai",
            "event": "bios_ai_repair",
            "item_id": item.item_id,
            "path": item.path,
            "issue_type": item.issue_type,
            "action": item.action,
            "zone": item.zone,
            "status": result.status,
            "message": result.message,
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{audit_url.rstrip('/')}/audit/events", json=payload)
        except Exception:
            # Non-fatal: repair pipeline must continue even if telemetry endpoint is down.
            pass

    async def _notify_approval_request(self, notify_url: str, item: CheckItem) -> None:
        payload = {
            "service": "bios-ai",
            "topic": "Repair approval needed",
            "message": f"Approval needed for {item.path}",
            "item_id": item.item_id,
            "zone": item.zone,
            "action": item.action,
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{notify_url.rstrip('/')}/notify", json=payload)
        except Exception:
            pass
