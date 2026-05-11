"""Session-wide Python startup customizations for local test compatibility."""

import builtins

try:
    import pytest
except Exception:  # pragma: no cover
    pytest = None  # type: ignore[assignment]

if pytest is not None and not hasattr(builtins, "PytestUnraisableExceptionWarning"):
    builtins.PytestUnraisableExceptionWarning = pytest.PytestUnraisableExceptionWarning
