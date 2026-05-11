from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class SearchItem:
    kind: str
    title: str
    subtitle: str
    payload: dict


class SearchService:
    def __init__(self) -> None:
        self._apps = self._load_desktop_apps()

    @staticmethod
    def _parse_desktop_entry(entry: Path) -> SearchItem | None:
        name = ""
        exec_cmd = ""
        lines = entry.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines:
            if line.startswith("Name="):
                name = line.split("=", 1)[1].strip()
            elif line.startswith("Exec="):
                exec_cmd = line.split("=", 1)[1].strip().split("%", 1)[0].strip()

        if not name or not exec_cmd:
            return None

        return SearchItem("app", name, exec_cmd, {"exec": exec_cmd})

    def _load_desktop_apps(self) -> list[SearchItem]:
        results: list[SearchItem] = []
        desktop_paths = [
            Path("/usr/share/applications"),
            Path.home() / ".local" / "share" / "applications",
        ]
        for root in desktop_paths:
            if not root.exists():
                continue
            for entry in root.glob("*.desktop"):
                app_entry = self._parse_desktop_entry(entry)
                if app_entry is not None:
                    results.append(app_entry)
        return results

    def _candidate_files(self) -> Iterable[Path]:
        roots = [Path.home() / "Downloads", Path.home() / "Documents", Path.home()]
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    yield path

    def _score(self, query: str, candidate: str) -> float:
        try:
            from rapidfuzz import fuzz

            return float(fuzz.WRatio(query.lower(), candidate.lower()))
        except Exception:
            import difflib

            return difflib.SequenceMatcher(a=query.lower(), b=candidate.lower()).ratio() * 100.0

    def search(self, query: str, limit: int = 20) -> list[SearchItem]:
        query = query.strip()
        if not query:
            return []

        candidates: list[tuple[float, SearchItem]] = []

        for app in self._apps:
            score = self._score(query, app.title)
            if score > 35:
                candidates.append((score, app))

        scanned = 0
        for path in self._candidate_files():
            score = self._score(query, path.name)
            if score > 40:
                candidates.append((score, SearchItem("file", path.name, str(path), {"path": str(path)})))
            scanned += 1
            if scanned > 600:
                break

        settings_entries = [
            SearchItem("setting", "Display Settings", "Open GNOME Settings", {"exec": "gnome-control-center display"}),
            SearchItem("setting", "Network Settings", "Open network settings", {"exec": "gnome-control-center network"}),
            SearchItem("setting", "Bluetooth Settings", "Open bluetooth settings", {"exec": "gnome-control-center bluetooth"}),
        ]
        for item in settings_entries:
            score = self._score(query, item.title)
            if score > 35:
                candidates.append((score, item))

        candidates.append((85.0, SearchItem("ai", f"Ask AI: {query}", "Start orchestration task", {"goal": query})))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in candidates[:limit]]
