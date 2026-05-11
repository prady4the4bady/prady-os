from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


class Manifest(BaseModel):
    version: str = Field(pattern=SEMVER_PATTERN)
    slot: Literal["a", "b"]
    sha256_full: str = Field(min_length=64, max_length=64)
    sha256_delta: str = Field(min_length=64, max_length=64)
    size_full: int = Field(ge=0)
    size_delta: int = Field(ge=0)
    delta_base_version: str = Field(pattern=SEMVER_PATTERN)
    changelog: list[str]
    min_version: str = Field(pattern=SEMVER_PATTERN)
    released_at: datetime

    @field_validator("sha256_full", "sha256_delta")
    @classmethod
    def _validate_sha(cls, value: str) -> str:
        lowered = value.lower()
        if any(ch not in "0123456789abcdef" for ch in lowered):
            raise ValueError("sha256 must be lowercase hex")
        return lowered


class ManifestValidator:
    def validate(self, raw_dict: dict) -> Manifest:
        return Manifest.model_validate(raw_dict)

    @staticmethod
    def _parse_semver(version: str) -> tuple[int, int, int]:
        parts = version.split(".")
        if len(parts) != 3:
            raise ValueError(f"invalid semver: {version}")
        return int(parts[0]), int(parts[1]), int(parts[2])

    def is_newer_than(self, manifest: Manifest, current_version: str) -> bool:
        return self._parse_semver(manifest.version) > self._parse_semver(current_version)


__all__ = ["Manifest", "ManifestValidator", "ValidationError"]
