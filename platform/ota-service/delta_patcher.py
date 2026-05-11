from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

try:
    import bsdiff4
except Exception:  # pragma: no cover
    class _BsdiffFallback:
        @staticmethod
        def file_patch_inplace(*_args, **_kwargs):
            raise RuntimeError("bsdiff4 is not installed")

        @staticmethod
        def file_diff(*_args, **_kwargs):
            raise RuntimeError("bsdiff4 is not installed")

    bsdiff4 = _BsdiffFallback()


class DeltaPatcher:
    def verify_file(self, path: str | Path, expected_sha256: str) -> bool:
        file_path = Path(path)
        if not file_path.exists():
            return False
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        return digest == expected_sha256.lower()

    def apply_patch(
        self,
        source_path: str | Path,
        patch_path: str | Path,
        target_path: str | Path,
        expected_sha256: str | None = None,
    ) -> bool:
        source = Path(source_path)
        patch = Path(patch_path)
        target = Path(target_path)

        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                ["bspatch", str(source), str(target), str(patch)],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            shutil.copy2(source, target)
            bsdiff4.file_patch_inplace(str(target), str(patch))

        if expected_sha256:
            return self.verify_file(target, expected_sha256)
        return True

    def create_patch(self, old_path: str | Path, new_path: str | Path, patch_path: str | Path) -> int:
        old_file = Path(old_path)
        new_file = Path(new_path)
        patch_file = Path(patch_path)
        patch_file.parent.mkdir(parents=True, exist_ok=True)

        bsdiff4.file_diff(str(old_file), str(new_file), str(patch_file))
        return patch_file.stat().st_size
