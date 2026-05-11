from __future__ import annotations

import json

import pytest
import respx

from kryos_sdk.model import KryosModel


def request_body(route) -> dict:
    return json.loads(route.calls.last.request.content.decode())


@pytest.mark.asyncio
async def test_constructor_uses_default_base():
    model = KryosModel()
    assert model.api_base == "http://localhost:8000"


@pytest.mark.asyncio
async def test_query_returns_root_content():
    model = KryosModel("http://example")
    with respx.mock() as mock:
        mock.post("http://example/v1/chat/completions").respond(json={"content": "hello"})
        result = await model.query("hi")
    assert result == "hello"


@pytest.mark.asyncio
async def test_query_returns_first_choice_content():
    model = KryosModel("http://example")
    with respx.mock() as mock:
        mock.post("http://example/v1/chat/completions").respond(json={"choices": [{"message": {"content": "world"}}]})
        result = await model.query("hi")
    assert result == "world"


@pytest.mark.asyncio
async def test_query_sends_options():
    model = KryosModel("http://example")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://example/v1/chat/completions").respond(json={"content": "ok"})
        await model.query("hi", {"max_tokens": 12, "temperature": 0.4, "model": "x"})
    assert request_body(route) == {"prompt": "hi", "max_tokens": 12, "temperature": 0.4, "model": "x"}


@pytest.mark.asyncio
async def test_list_models_success():
    model = KryosModel()
    with respx.mock() as mock:
        mock.get("http://localhost:8003/models").respond(json={"models": [{"id": "m1", "name": "Model 1", "active": True}]})
        result = await model.listModels()
    assert result[0].id == "m1"


@pytest.mark.asyncio
async def test_list_models_raises_on_http_error():
    model = KryosModel()
    with respx.mock() as mock:
        mock.get("http://localhost:8003/models").respond(status_code=500, text="boom")
        with pytest.raises(Exception):
            await model.listModels()
