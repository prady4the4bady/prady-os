from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from delta_patcher import DeltaPatcher


class TestDeltaPatcher:
    def test_verify_file_true(self):
        patcher = DeltaPatcher()
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "test.bin"
            file_path.write_bytes(b"hello")
            sha = hashlib.sha256(b"hello").hexdigest()
            assert patcher.verify_file(file_path, sha) is True

    def test_verify_file_false(self):
        patcher = DeltaPatcher()
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "test.bin"
            file_path.write_bytes(b"hello")
            assert patcher.verify_file(file_path, "0" * 64) is False

    @patch("subprocess.run")
    def test_apply_patch_invokes_bspatch(self, mock_run):
        patcher = DeltaPatcher()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "old.bin"
            patch_file = Path(tmp) / "change.delta"
            target = Path(tmp) / "new.bin"
            source.write_bytes(b"old")
            patch_file.write_bytes(b"patch")

            result = patcher.apply_patch(source, patch_file, target)
            assert result is True
            mock_run.assert_called_once_with(
                ["bspatch", str(source), str(target), str(patch_file)],
                check=False,
                capture_output=True,
                text=True,
            )

    @patch("subprocess.run")
    @patch.object(DeltaPatcher, "verify_file", return_value=False)
    def test_apply_patch_sha_mismatch_returns_false(self, _mock_verify, _mock_run):
        patcher = DeltaPatcher()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "old.bin"
            patch_file = Path(tmp) / "change.delta"
            target = Path(tmp) / "new.bin"
            source.write_bytes(b"old")
            patch_file.write_bytes(b"patch")

            result = patcher.apply_patch(source, patch_file, target, expected_sha256="a" * 64)
            assert result is False

    @patch("delta_patcher.bsdiff4.file_diff")
    def test_create_patch_returns_size(self, mock_diff):
        patcher = DeltaPatcher()
        with tempfile.TemporaryDirectory() as tmp:
            old_file = Path(tmp) / "old.bin"
            new_file = Path(tmp) / "new.bin"
            patch_file = Path(tmp) / "change.delta"
            old_file.write_bytes(b"old")
            new_file.write_bytes(b"new")

            def _write_patch(*_args, **_kwargs):
                patch_file.write_bytes(b"delta-bytes")

            mock_diff.side_effect = _write_patch
            size = patcher.create_patch(old_file, new_file, patch_file)
            assert isinstance(size, int)
            assert size > 0
