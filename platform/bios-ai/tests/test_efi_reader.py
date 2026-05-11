from __future__ import annotations

from pathlib import Path

from efi_reader import EFIReader


def test_read_boot_decision_defaults_normal(tmp_path: Path):
    reader = EFIReader(efivar_root=tmp_path / "efivars")
    assert reader.read_boot_decision() == "NORMAL"


def test_write_and_read_fallback(tmp_path: Path, monkeypatch):
    reader = EFIReader(efivar_root=tmp_path / "efivars")
    fallback = tmp_path / "kryos_boot_decision"
    monkeypatch.setattr(reader, "DEV_FALLBACK", fallback)

    reader.write_boot_decision("repair")
    assert reader.read_boot_decision() == "REPAIR"


def test_read_from_efivar_utf16_payload(tmp_path: Path):
    efivars = tmp_path / "efivars"
    efivars.mkdir(parents=True)
    reader = EFIReader(efivar_root=efivars)

    path = reader.efi_var_path
    attrs = b"\x07\x00\x00\x00"
    payload = "SAFE".encode("utf-16-le") + b"\x00\x00"
    path.write_bytes(attrs + payload)

    assert reader.read_boot_decision() == "SAFE"
