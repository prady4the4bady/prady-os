"""EFI variable reader/writer for KryosBootDecision."""

from __future__ import annotations

from pathlib import Path


class EFIReader:
    GUID = "12345678-1234-1234-1234-123456789abc"
    DEV_FALLBACK = Path("/tmp/kryos_boot_decision")

    def __init__(self, efivar_root: Path = Path("/sys/firmware/efi/efivars")) -> None:
        self.efivar_root = efivar_root

    @property
    def efi_var_path(self) -> Path:
        return self.efivar_root / f"KryosBootDecision-{self.GUID}"

    def is_uefi_boot(self) -> bool:
        return Path("/sys/firmware/efi").exists()

    def read_boot_decision(self) -> str:
        """Read from EFI var if available, then /tmp fallback, otherwise NORMAL."""
        decision = self._read_from_efivar()
        if decision:
            return decision

        if self.DEV_FALLBACK.exists():
            raw = self.DEV_FALLBACK.read_text(encoding="utf-8").strip().upper()
            if raw in {"NORMAL", "REPAIR", "SAFE", "RECOVERY"}:
                return raw

        return "NORMAL"

    def _read_from_efivar(self) -> str | None:
        path = self.efi_var_path
        if not path.exists():
            return None

        try:
            data = path.read_bytes()
        except OSError:
            return None

        if not data:
            return None

        # Linux efivars expose first 4 bytes as attributes.
        payload = data[4:] if len(data) > 4 else data
        try:
            text = payload.decode("utf-16-le", errors="ignore").strip("\x00\n\r ").upper()
        except Exception:
            return None

        if text in {"NORMAL", "REPAIR", "SAFE", "RECOVERY"}:
            return text
        return None

    def write_boot_decision(self, decision: str) -> None:
        """Stage 2 dev simulation write only; never writes real EFI vars."""
        normalized = decision.strip().upper()
        if normalized not in {"NORMAL", "REPAIR", "SAFE", "RECOVERY"}:
            raise ValueError(f"Invalid decision: {decision}")
        self.DEV_FALLBACK.write_text(normalized, encoding="utf-8")
