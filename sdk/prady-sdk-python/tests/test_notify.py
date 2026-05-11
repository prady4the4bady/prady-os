from __future__ import annotations

import json

import pytest
import respx

from kryos_sdk.notify import KryosNotify


def request_body(route) -> dict:
    return json.loads(route.calls.last.request.content.decode())


@pytest.mark.asyncio
async def test_constructor_uses_default_base():
    notify = KryosNotify()
    assert notify.api_base == "http://localhost:8007"


@pytest.mark.asyncio
async def test_send_posts_default_severity():
    notify = KryosNotify("http://example")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://example/notify").respond(json={"ok": True})
        await notify.send("Title", "Body")
    assert request_body(route)["severity"] == "info"


@pytest.mark.asyncio
async def test_send_posts_custom_severity():
    notify = KryosNotify("http://example")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://example/notify").respond(json={"ok": True})
        await notify.send("Title", "Body", "critical")
    assert request_body(route)["severity"] == "critical"


@pytest.mark.asyncio
async def test_send_sets_sdk_source():
    notify = KryosNotify("http://example")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://example/notify").respond(json={"ok": True})
        await notify.send("Title", "Body")
    assert request_body(route)["source"] == "sdk-app"


@pytest.mark.asyncio
async def test_send_raises_on_error():
    notify = KryosNotify("http://example")
    with respx.mock() as mock:
        mock.post("http://example/notify").respond(status_code=500, text="boom")
        with pytest.raises(Exception):
            await notify.send("Title", "Body")
