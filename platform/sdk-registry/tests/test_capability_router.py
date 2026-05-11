from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from capability_router import CapabilityRouter, DelegationResult


@pytest.mark.asyncio
async def test_delegate_returns_error_when_no_apps(db):
    router = CapabilityRouter(db)
    result = await router.delegate("search:web", {}, 1000)
    assert result.success is False
    assert "No running app" in result.error


@pytest.mark.asyncio
async def test_delegate_returns_error_when_matching_apps_not_running(db, sample_manifest):
    app_id = await db.register_app(sample_manifest)
    await db.update_status(app_id, "stopped", None)
    router = CapabilityRouter(db)
    result = await router.delegate("search:web", {}, 1000)
    assert result.success is False


@pytest.mark.asyncio
async def test_delegate_posts_to_correct_url(db, sample_manifest):
    app_id = await db.register_app(sample_manifest)
    await db.update_status(app_id, "running", "container-1")
    router = CapabilityRouter(db)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"http://kryos-sdk-{app_id}:8080/kryos/task").respond(json={"answer": "ok"}, status_code=200)
        result = await router.delegate("search:web", {"q": "weather"}, 5000)
    assert route.called is True
    assert result.success is True
    assert result.result == {"answer": "ok"}


@pytest.mark.asyncio
async def test_delegate_latency_is_non_negative(db, sample_manifest):
    app_id = await db.register_app(sample_manifest)
    await db.update_status(app_id, "running", "container-1")
    router = CapabilityRouter(db)
    with respx.mock() as mock:
        mock.post(f"http://kryos-sdk-{app_id}:8080/kryos/task").respond(json={"answer": "ok"}, status_code=200)
        result = await router.delegate("search:web", {"q": "weather"}, 5000)
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_delegate_handles_timeout_gracefully(db, sample_manifest):
    app_id = await db.register_app(sample_manifest)
    await db.update_status(app_id, "running", "container-1")
    router = CapabilityRouter(db)
    with respx.mock() as mock:
        mock.post(f"http://kryos-sdk-{app_id}:8080/kryos/task").mock(side_effect=httpx.TimeoutException("timeout"))
        result = await router.delegate("search:web", {"q": "weather"}, 5000)
    assert result.success is False
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_delegate_handles_http_500(db, sample_manifest):
    app_id = await db.register_app(sample_manifest)
    await db.update_status(app_id, "running", "container-1")
    router = CapabilityRouter(db)
    with respx.mock() as mock:
        mock.post(f"http://kryos-sdk-{app_id}:8080/kryos/task").respond(status_code=500, json={"detail": "boom"})
        result = await router.delegate("search:web", {"q": "weather"}, 5000)
    assert result.success is False


@pytest.mark.asyncio
async def test_get_capability_map_returns_correct_structure(db, sample_manifest):
    app_id = await db.register_app(sample_manifest)
    await db.update_status(app_id, "running", "container-1")
    router = CapabilityRouter(db)
    caps = await router.get_capability_map()
    assert caps and caps[0]["capability"] == "search:web"
    assert caps[0]["app_id"] == app_id


@pytest.mark.asyncio
async def test_get_capability_map_only_includes_running(db, sample_manifest):
    app_id = await db.register_app(sample_manifest)
    await db.update_status(app_id, "stopped", None)
    router = CapabilityRouter(db)
    caps = await router.get_capability_map()
    assert caps == []
