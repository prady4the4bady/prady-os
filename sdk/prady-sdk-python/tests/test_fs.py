from __future__ import annotations

import json

import pytest
import respx

from kryos_sdk.fs import KryosFS


def request_body(route) -> dict:
    return json.loads(route.calls.last.request.content.decode())


@pytest.mark.asyncio
async def test_constructor_stores_app_name():
    fs = KryosFS("demo")
    assert fs.app_name == "demo"


@pytest.mark.asyncio
async def test_read_returns_content():
    fs = KryosFS("demo", "http://example")
    with respx.mock() as mock:
        mock.get("http://example/sdk/fs/read").respond(json={"content": "hello"})
        result = await fs.read("notes.txt")
    assert result == "hello"


@pytest.mark.asyncio
async def test_write_sends_payload():
    fs = KryosFS("demo", "http://example")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://example/sdk/fs/write").respond(json={"written": True})
        await fs.write("notes.txt", "hello")
    assert request_body(route) == {"app": "demo", "path": "notes.txt", "content": "hello"}


@pytest.mark.asyncio
async def test_list_returns_entry_names():
    fs = KryosFS("demo", "http://example")
    with respx.mock() as mock:
        mock.get("http://example/sdk/fs/list").respond(json={"entries": [{"name": "a.txt"}, {"name": "b.txt"}]})
        result = await fs.list("/")
    assert result == ["a.txt", "b.txt"]


@pytest.mark.asyncio
async def test_delete_success():
    fs = KryosFS("demo", "http://example")
    with respx.mock() as mock:
        mock.delete("http://example/sdk/fs/delete").respond(json={"deleted": True})
        await fs.delete("a.txt")


@pytest.mark.asyncio
async def test_read_raises_on_error():
    fs = KryosFS("demo", "http://example")
    with respx.mock() as mock:
        mock.get("http://example/sdk/fs/read").respond(status_code=500, text="boom")
        with pytest.raises(Exception):
            await fs.read("notes.txt")
