from __future__ import annotations

import sys
from pathlib import Path

# Non-hyphen service directories are safe to expose globally for direct imports.
_PLATFORM_ROOT = Path(__file__).resolve().parent
for child in _PLATFORM_ROOT.iterdir():
	if not child.is_dir():
		continue
	if "-" in child.name:
		continue
	child_path = str(child)
	if child_path not in sys.path:
		sys.path.insert(0, child_path)


def pytest_sessionstart() -> None:
	# Hyphenated service folders are added after plugin discovery so test module
	# imports resolve without turning sibling conftest modules into `tests.conftest`.
	for child in _PLATFORM_ROOT.iterdir():
		if not child.is_dir() or "-" not in child.name:
			continue
		child_path = str(child)
		if child_path not in sys.path:
			sys.path.insert(0, child_path)
