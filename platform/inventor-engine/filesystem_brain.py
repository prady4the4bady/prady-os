from __future__ import annotations

from pathlib import Path
from enum import Enum
import os


class Zone(Enum):
    FREE = "free"
    ASK = "ask"
    NEVER = "never"


FREE_PATHS = ["/var/prady/", "/tmp/prady/"]
ASK_PATHS = ["/home/"]
NEVER_PATHS = ["/etc/", "/boot/", "/sys/", "/proc/", "/dev/", "/root/"]


class FilesystemBrain:
    def classify(self, path: str) -> Zone:
        resolved = str(Path(path).resolve())
        for p in NEVER_PATHS:
            if resolved.startswith(p):
                return Zone.NEVER
        for p in ASK_PATHS:
            if resolved.startswith(p):
                return Zone.ASK
        for p in FREE_PATHS:
            if resolved.startswith(p):
                return Zone.FREE
        return Zone.ASK

    def read(self, path: str) -> str:
        zone = self.classify(path)
        if zone == Zone.NEVER:
            raise PermissionError(f"Prax cannot read from NEVER zone: {path}")
        return Path(path).read_text()

    def write(self, path: str, content: str, approved: bool = False) -> bool:
        zone = self.classify(path)
        if zone == Zone.NEVER:
            raise PermissionError(f"Prax cannot write to NEVER zone: {path}")
        if zone == Zone.ASK and not approved:
            return False
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        return True

    def delete(self, path: str, approved: bool = False) -> bool:
        zone = self.classify(path)
        if zone == Zone.NEVER:
            raise PermissionError(f"Prax cannot delete from NEVER zone: {path}")
        if zone != Zone.FREE:
            if not approved:
                return False
        Path(path).unlink(missing_ok=True)
        return True

    def list_dir(self, path: str) -> list[str]:
        zone = self.classify(path)
        if zone == Zone.NEVER:
            raise PermissionError(f"Prax cannot list NEVER zone: {path}")
        return [str(p) for p in Path(path).iterdir()]
