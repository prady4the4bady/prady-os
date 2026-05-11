from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any

VALID_PERMISSIONS = {
    "model-inference",
    "file-system:read",
    "file-system:write",
    "computer-use",
    "notifications",
    "audio-input",
    "audio-output",
    "network",
    "task-schedule",
}
MAX_MEMORY_MB = 2048
MAX_CPU_SHARES = 1024
MIN_CPU_SHARES = 64


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    manifest: dict | None = None


class ManifestValidator:
    def validate_capability_format(self, cap: str) -> bool:
        return bool(re.match(r"^[a-z]+:[a-z]+(-[a-z]+)*$", cap))

    def is_safe_path(self, path: str) -> bool:
        try:
            p = PurePosixPath(path)
            return (not p.is_absolute() and ".." not in p.parts and "\x00" not in path)
        except Exception:
            return False

    def validate(self, raw: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        required = ["name", "display_name", "version", "description", "author", "license", "entry_point", "icon", "permissions", "capabilities", "sandbox", "ui", "min_kryos_version"]
        for field in required:
            if field not in raw:
                errors.append(f"missing required field: {field}")

        name = raw.get("name", "")
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", str(name)):
            errors.append("name must be kebab-case")

        if not re.match(r"^\d+\.\d+\.\d+$", str(raw.get("version", ""))):
            errors.append("version must be semver")

        perms = raw.get("permissions", [])
        for perm in perms:
            if perm not in VALID_PERMISSIONS:
                errors.append(f"unknown permission: {perm}")

        sandbox = raw.get("sandbox", {}) or {}
        memory = int(sandbox.get("memory_mb", 0))
        cpu = int(sandbox.get("cpu_shares", 0))
        if memory > MAX_MEMORY_MB:
            errors.append("sandbox.memory_mb exceeds max")
        if memory < 64:
            errors.append("sandbox.memory_mb below min")
        if cpu > MAX_CPU_SHARES:
            errors.append("sandbox.cpu_shares exceeds max")
        if cpu < MIN_CPU_SHARES:
            errors.append("sandbox.cpu_shares below min")
        if sandbox.get("read_only_root") is not True:
            errors.append("sandbox.read_only_root must be true")

        for cap in raw.get("capabilities", []):
            if not self.validate_capability_format(cap):
                errors.append(f"invalid capability: {cap}")

        ui = raw.get("ui", {}) or {}
        if ui.get("type") not in {"window", "widget", "background"}:
            errors.append("ui.type invalid")

        return ValidationResult(valid=not errors, errors=errors, manifest=raw if not errors else None)
