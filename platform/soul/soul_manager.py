"""SoulManager — loads and saves per-user SOUL.md personality files.

SOUL.md format (Markdown front-matter + free-form body):
  - name
  - personality
  - communication_style
  - preferred_model
  - skill_preferences (comma-separated)
  - memory_summary (last 20 interactions, auto-pruned)
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SOUL_DATA_ROOT = Path(__file__).resolve().parent / "data"
SOUL_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "default.md"
MAX_MEMORY_ENTRIES = 20


def _parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML-ish front-matter delimited by --- lines."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}, content

    meta: Dict[str, Any] = {}
    for line in lines[1:end]:
        m = re.match(r"^(\w+):\s*(.*)", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            meta[key] = value

    body = "\n".join(lines[end + 1:]).strip()
    return meta, body


def _render_soul(meta: Dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    if body:
        lines.append("")
        lines.append(body)
    return "\n".join(lines) + "\n"


class SoulManager:
    """Load, update, and persist per-user SOUL.md files."""

    def _soul_path(self, user_id: str) -> Path:
        p = SOUL_DATA_ROOT / user_id / "SOUL.md"
        return p

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, user_id: str) -> str:
        path = self._soul_path(user_id)
        if not path.exists():
            template = SOUL_TEMPLATE_PATH.read_text(encoding="utf-8")
            self._save_raw(user_id, template)
            return template
        return path.read_text(encoding="utf-8")

    def load_parsed(self, user_id: str) -> Dict[str, Any]:
        content = self.load(user_id)
        meta, body = _parse_frontmatter(content)
        meta["body"] = body
        return meta

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, user_id: str, fields: Dict[str, Any]) -> str:
        """Merge *fields* into the user's SOUL.md front-matter."""
        content = self.load(user_id)
        meta, body = _parse_frontmatter(content)
        for key, value in fields.items():
            if key != "body":
                meta[key] = str(value)
        if "body" in fields:
            body = str(fields["body"])
        updated = _render_soul(meta, body)
        self._save_raw(user_id, updated)
        return updated

    # ------------------------------------------------------------------
    # Memory append
    # ------------------------------------------------------------------

    def append_memory(self, user_id: str, interaction: str) -> str:
        """Append an interaction to memory_summary, pruning to last 20."""
        content = self.load(user_id)
        meta, body = _parse_frontmatter(content)

        # memory_summary stored as JSON array in front-matter
        existing_raw = meta.get("memory_summary", "[]")
        try:
            entries: List[str] = json.loads(existing_raw)
        except (json.JSONDecodeError, TypeError):
            entries = []

        entries.append(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}: {interaction}")
        if len(entries) > MAX_MEMORY_ENTRIES:
            entries = entries[-MAX_MEMORY_ENTRIES:]

        meta["memory_summary"] = json.dumps(entries)
        updated = _render_soul(meta, body)
        self._save_raw(user_id, updated)
        return updated

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save_raw(self, user_id: str, content: str) -> None:
        path = self._soul_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
