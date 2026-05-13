from __future__ import annotations

import sys
from pathlib import Path

_PLATFORM_ROOT = Path(__file__).resolve().parent
for child in _PLATFORM_ROOT.iterdir():
    if not child.is_dir():
        continue
    child_path = str(child)
    if child_path not in sys.path:
        sys.path.insert(0, child_path)
