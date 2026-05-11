from __future__ import annotations

import pytest

from manifest_validator import ManifestValidator


def _validator() -> ManifestValidator:
    return ManifestValidator()


def _manifest() -> dict:
    return {
        "name": "test-app",
        "display_name": "Test App",
        "version": "1.0.0",
        "description": "A test SDK app",
        "author": "Test Author",
        "license": "MIT",
        "entry_point": "main.py",
        "icon": "icon.png",
        "permissions": ["model-inference", "notifications"],
        "capabilities": ["search:web", "send:notification"],
        "sandbox": {"memory_mb": 512, "cpu_shares": 256, "network_isolated": False, "read_only_root": True},
        "ui": {"type": "window", "width": 800, "height": 600, "resizable": True},
        "min_kryos_version": "1.0.0",
    }


def test_valid_manifest_passes_validation():
    result = _validator().validate(_manifest())
    assert result.valid is True
    assert result.errors == []


def test_missing_required_name_fails():
    manifest = _manifest()
    manifest.pop("name")
    result = _validator().validate(manifest)
    assert result.valid is False
    assert any("name" in err for err in result.errors)


def test_name_with_spaces_fails_kebab_case():
    manifest = _manifest()
    manifest["name"] = "bad app"
    result = _validator().validate(manifest)
    assert result.valid is False
    assert any("kebab-case" in err for err in result.errors)


def test_version_must_be_semver():
    manifest = _manifest()
    manifest["version"] = "1.0"
    result = _validator().validate(manifest)
    assert result.valid is False
    assert any("semver" in err for err in result.errors)


def test_unknown_permission_is_rejected():
    manifest = _manifest()
    manifest["permissions"] = ["camera-access"]
    result = _validator().validate(manifest)
    assert result.valid is False
    assert any("unknown permission" in err for err in result.errors)


def test_memory_above_max_is_rejected():
    manifest = _manifest()
    manifest["sandbox"]["memory_mb"] = 4096
    result = _validator().validate(manifest)
    assert result.valid is False
    assert any("memory_mb" in err for err in result.errors)


def test_memory_below_min_is_rejected():
    manifest = _manifest()
    manifest["sandbox"]["memory_mb"] = 32
    result = _validator().validate(manifest)
    assert result.valid is False
    assert any("below min" in err for err in result.errors)


def test_cpu_shares_above_max_is_rejected():
    manifest = _manifest()
    manifest["sandbox"]["cpu_shares"] = 4096
    result = _validator().validate(manifest)
    assert result.valid is False
    assert any("cpu_shares" in err for err in result.errors)


def test_capability_format_helper_accepts_valid_value():
    assert _validator().validate_capability_format("send:email") is True


def test_capability_format_helper_rejects_invalid_value():
    assert _validator().validate_capability_format("sendEmail") is False


def test_safe_path_rejects_traversal():
    assert _validator().is_safe_path("../etc/passwd") is False


def test_safe_path_accepts_relative_path():
    assert _validator().is_safe_path("data/output.txt") is True


def test_safe_path_rejects_absolute_path():
    assert _validator().is_safe_path("/absolute/path") is False
