from __future__ import annotations

import pytest

from registry_db import RegistryDB


@pytest.fixture
def manifest() -> dict:
    return {
        "name": "test-app",
        "display_name": "Test App",
        "version": "1.0.0",
        "description": "A test SDK app",
        "author": "Test Author",
        "license": "MIT",
        "permissions": ["model-inference", "notifications"],
        "capabilities": ["search:web", "send:notification"],
    }


@pytest.mark.asyncio
async def test_init_creates_installed_apps_table(db):
    cur = await db._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='installed_apps'")
    row = await cur.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_register_app_returns_app_id(db, manifest):
    app_id = await db.register_app(manifest)
    assert app_id.startswith("test-app-")


@pytest.mark.asyncio
async def test_get_app_returns_none_for_unknown(db):
    assert await db.get_app("missing") is None


@pytest.mark.asyncio
async def test_get_all_apps_parses_permissions_as_list(db, manifest):
    await db.register_app(manifest)
    apps = await db.get_all_apps()
    assert len(apps) == 1
    assert isinstance(apps[0]["permissions"], list)


@pytest.mark.asyncio
async def test_get_apps_by_capability_returns_matching(db, manifest):
    await db.register_app(manifest)
    await db.register_app({**manifest, "name": "other-app", "capabilities": ["play:music"]})
    apps = await db.get_apps_by_capability("search:web")
    assert len(apps) == 1
    assert apps[0]["display_name"] == "Test App"


@pytest.mark.asyncio
async def test_update_status_changes_status_field(db, manifest):
    app_id = await db.register_app(manifest)
    await db.update_status(app_id, "running", "container-1")
    app = await db.get_app(app_id)
    assert app is not None
    assert app["status"] == "running"


@pytest.mark.asyncio
async def test_remove_app_deletes_row(db, manifest):
    app_id = await db.register_app(manifest)
    removed = await db.remove_app(app_id)
    assert removed is True
    assert await db.get_app(app_id) is None


@pytest.mark.asyncio
async def test_get_running_count_tracks_running_rows(db, manifest):
    app_id = await db.register_app(manifest)
    await db.update_status(app_id, "running", "container-1")
    assert await db.get_running_count() == 1


@pytest.mark.asyncio
async def test_update_last_active_sets_timestamp(db, manifest):
    app_id = await db.register_app(manifest)
    await db.update_last_active(app_id)
    app = await db.get_app(app_id)
    assert app is not None
    assert app["last_active_ts"] is not None
