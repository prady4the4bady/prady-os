"""Regression: git.py must be importable after _UNIFIED_REVIEW_MODELS was removed from review.py."""


def test_git_tool_importable():
    """git.py should import cleanly — no stale references to removed symbols."""
    import neila.tools.git  # noqa: F401 — import side-effects checked implicitly
    assert hasattr(neila.tools.git, "get_tools")


