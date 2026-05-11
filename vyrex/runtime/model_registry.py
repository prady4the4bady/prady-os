"""
ModelRegistry – resolves and caches model artifacts.

Supported URI schemes:
  hf://org/repo[/filename]          HuggingFace Hub
  gh://owner/repo/path/to/file      GitHub raw download
  local:///abs/path/to/file.gguf    Already-present local file
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = Path.home() / ".kryos" / "models"
_HF_BASE = "https://huggingface.co"
_GH_RAW_BASE = "https://raw.githubusercontent.com"
_LOCAL_SCHEME = "local://"


@dataclass
class ModelEntry:
    model_id: str
    source_url: str
    local_path: Optional[Path] = None
    sha256: Optional[str] = None
    size_bytes: int = 0
    status: str = "registered"  # registered | downloading | ready | error


class ModelRegistry:
    """Resolve, download, and cache model artifacts."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self._cache_dir: Path = cache_dir or _DEFAULT_CACHE
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, ModelEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, model_id: str, source_url: str) -> ModelEntry:
        """Register a model source URI without downloading."""
        entry = ModelEntry(model_id=model_id, source_url=source_url)
        self._entries[model_id] = entry
        logger.info("Registered model %s → %s", model_id, source_url)
        return entry

    def get(self, model_id: str) -> Optional[ModelEntry]:
        return self._entries.get(model_id)

    def list_available(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def ensure_local(self, model_id: str) -> Path:
        """Return local path, downloading if necessary."""
        entry = self._entries.get(model_id)
        if entry is None:
            raise KeyError(f"Model '{model_id}' not registered")

        if entry.local_path and entry.local_path.exists() and entry.status == "ready":
            return entry.local_path

        dest = self._resolve_dest(model_id, entry.source_url)
        if dest.exists():
            entry.local_path = dest
            entry.status = "ready"
            return dest

        url = self._to_download_url(entry.source_url)
        entry.status = "downloading"
        try:
            self._download(url, dest)
            entry.local_path = dest
            entry.sha256 = _sha256(dest)
            entry.size_bytes = dest.stat().st_size
            entry.status = "ready"
            logger.info("Model %s ready at %s", model_id, dest)
        except Exception as exc:
            entry.status = "error"
            raise RuntimeError(f"Failed to download model {model_id}: {exc}") from exc

        return dest

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_dest(self, model_id: str, source_url: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_\-.]", "_", model_id)
        ext = _infer_extension(source_url)
        return self._cache_dir / f"{safe_id}{ext}"

    def _to_download_url(self, source_url: str) -> str:
        if source_url.startswith("hf://"):
            # hf://org/repo[/filename]
            path = source_url[5:]
            parts = path.split("/", 2)
            if len(parts) < 2:
                raise ValueError(f"Invalid hf:// URI: {source_url}")
            org, repo = parts[0], parts[1]
            filename = parts[2] if len(parts) == 3 else f"{repo}.gguf"
            return f"{_HF_BASE}/{org}/{repo}/resolve/main/{filename}"

        if source_url.startswith("gh://"):
            # gh://owner/repo/path/to/file
            path = source_url[5:]
            parts = path.split("/", 2)
            if len(parts) < 3:
                raise ValueError(f"Invalid gh:// URI: {source_url}")
            owner, repo, file_path = parts[0], parts[1], parts[2]
            return f"{_GH_RAW_BASE}/{owner}/{repo}/main/{file_path}"

        if source_url.startswith(_LOCAL_SCHEME):
            local_path = source_url[len(_LOCAL_SCHEME):]
            p = Path(local_path)
            if not p.exists():
                raise FileNotFoundError(f"Local model not found: {local_path}")
            return source_url  # handled in _download

        # Plain HTTP(S)
        parsed = urlparse(source_url)
        if parsed.scheme in ("http", "https"):
            return source_url

        raise ValueError(f"Unsupported model source URI: {source_url}")

    def _download(self, url: str, dest: Path) -> None:
        if url.startswith(_LOCAL_SCHEME):
            src = Path(url[len(_LOCAL_SCHEME):])
            shutil.copy2(src, dest)
            return

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=300) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        fh.write(chunk)
            tmp.rename(dest)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_extension(source_url: str) -> str:
    for ext in (".gguf", ".bin", ".safetensors", ".pt"):
        if source_url.endswith(ext):
            return ext
    return ".gguf"
