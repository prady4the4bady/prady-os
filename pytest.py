"""Compatibility launcher for `python -m pytest` from repository root.

Ensures `PytestUnraisableExceptionWarning` resolves from `builtins` for
warning-filter strings like `-W error::PytestUnraisableExceptionWarning`.
"""

from __future__ import annotations

import builtins
import importlib.machinery
import importlib.util
import sys


_real_spec = importlib.machinery.PathFinder.find_spec("pytest", sys.path[1:])
if _real_spec is None or _real_spec.loader is None:
    raise RuntimeError("Unable to resolve real pytest module")

_real_pytest = importlib.util.module_from_spec(_real_spec)
sys.modules["pytest"] = _real_pytest
_real_spec.loader.exec_module(_real_pytest)

if not hasattr(builtins, "PytestUnraisableExceptionWarning") and hasattr(_real_pytest, "PytestUnraisableExceptionWarning"):
    builtins.PytestUnraisableExceptionWarning = _real_pytest.PytestUnraisableExceptionWarning


if __name__ == "__main__":
    raise SystemExit(_real_pytest.console_main())
