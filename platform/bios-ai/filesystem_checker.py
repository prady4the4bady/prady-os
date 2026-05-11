"""Filesystem integrity scanner with tiered write access."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CheckItem:
    item_id: str
    path: str
    issue_type: str
    action: str
    zone: str
    approved: bool | None = None


@dataclass
class RepairResult:
    item_id: str
    path: str
    status: str
    action: str
    zone: str
    message: str = ""


class FilesystemChecker:
    FREE_ZONE = ["/var/kryos/", "/tmp/"]
    ASK_ZONE = ["/home/"]
    NEVER_ZONE = ["/etc/", "/boot/", "/sys/", "/proc/", "/dev/"]

    def __init__(self, roots: list[Path] | None = None) -> None:
        self.roots = roots or [Path("/var/kryos"), Path("/tmp"), Path("/home")]

    @staticmethod
    def _norm_path(path: str) -> str:
        text = path.replace("\\", "/")
        if not text.startswith("/"):
            text = "/" + text
        return text.lower().rstrip("/") + "/"

    def classify_zone(self, path: str) -> str:
        full = self._norm_path(str(path))
        for prefix in self.NEVER_ZONE:
            if full.startswith(prefix.lower()):
                return "never"
        for prefix in self.ASK_ZONE:
            if full.startswith(prefix.lower()):
                return "ask"
        for prefix in self.FREE_ZONE:
            if full.startswith(prefix.lower()):
                return "free"
        return "ask"

    async def scan(self) -> list[CheckItem]:
        return await asyncio.to_thread(self._scan_sync)

    def _scan_sync(self) -> list[CheckItem]:
        items: list[CheckItem] = []

        for root in self.roots:
            if not root.exists():
                continue

            for path in root.rglob("*"):
                item = self._check_path(path)
                if item:
                    items.append(item)

        return items

    def _check_path(self, path: Path) -> CheckItem | None:
        zone = self.classify_zone(str(path))

        if path.is_symlink() and not path.exists():
            return self._mk_item(path, "broken_symlink", "remove_symlink", zone)

        if path.is_file():
            if path.suffix in {".yaml", ".yml", ".json", ".toml"} and path.stat().st_size == 0:
                return self._mk_item(path, "zero_byte_config", "rebuild_config_stub", zone)

            parse_issue = self._validate_config(path)
            if parse_issue:
                return self._mk_item(path, "invalid_config", "quarantine_config", zone)

            if path.name.endswith(".lock"):
                return self._mk_item(path, "orphan_lock", "remove_lock", zone)

            # Specifically look for risky files in home directory.
            if self._norm_path(str(path)).startswith("/home/"):
                mode = path.stat().st_mode
                if bool(mode & stat.S_IWOTH):
                    return self._mk_item(path, "world_writable_home", "restrict_permissions", zone)

        return None

    def _validate_config(self, path: Path) -> bool:
        if path.suffix not in {".yaml", ".yml", ".json", ".toml"}:
            return False
        try:
            raw = path.read_text(encoding="utf-8")
            if path.suffix in {".yaml", ".yml"}:
                yaml.safe_load(raw)
            elif path.suffix == ".json":
                json.loads(raw)
            elif path.suffix == ".toml":
                tomllib.loads(raw)
            return False
        except Exception:
            return True

    def _mk_item(self, path: Path, issue: str, action: str, zone: str) -> CheckItem:
        return CheckItem(
            item_id=str(uuid.uuid4()),
            path=str(path),
            issue_type=issue,
            action=action,
            zone=zone,
            approved=None,
        )

    async def repair(self, item: CheckItem, force: bool = False) -> RepairResult:
        zone = item.zone or self.classify_zone(item.path)
        p = Path(item.path)

        if zone == "never":
            raise PermissionError(f"Path is in NEVER zone: {item.path}")

        if zone == "ask" and not force:
            return RepairResult(
                item_id=item.item_id,
                path=item.path,
                status="pending_approval",
                action=item.action,
                zone=zone,
                message="Approval required",
            )

        return await asyncio.to_thread(self._apply_repair_sync, item, p, zone)

    def _apply_repair_sync(self, item: CheckItem, path: Path, zone: str) -> RepairResult:
        try:
            if item.action == "remove_symlink" and path.is_symlink():
                path.unlink(missing_ok=True)

            elif item.action == "remove_lock" and path.exists():
                path.unlink(missing_ok=True)

            elif item.action == "restrict_permissions" and path.exists():
                mode = path.stat().st_mode
                new_mode = mode & ~stat.S_IWOTH
                os.chmod(path, new_mode)

            elif item.action == "quarantine_config" and path.exists():
                path.rename(path.with_suffix(path.suffix + ".invalid"))

            elif item.action == "rebuild_config_stub":
                path.parent.mkdir(parents=True, exist_ok=True)
                stub = "{}\n" if path.suffix == ".json" else "# regenerated by bios-ai\n"
                path.write_text(stub, encoding="utf-8")

            return RepairResult(
                item_id=item.item_id,
                path=item.path,
                status="applied",
                action=item.action,
                zone=zone,
            )
        except Exception as exc:
            return RepairResult(
                item_id=item.item_id,
                path=item.path,
                status="failed",
                action=item.action,
                zone=zone,
                message=str(exc),
            )
