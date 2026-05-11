from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import requests

from prady_models.db import ModelRecord, SessionLocal, init_db
from prady_models.platform_api import create_app


def _insert_model(model_id: str = "local-test-model") -> None:
    init_db()
    with SessionLocal() as session:
        existing = session.get(ModelRecord, model_id)
        if existing:
            session.delete(existing)
            session.commit()
        rec = ModelRecord(
            model_id=model_id,
            name="test.gguf",
            source="hf://org/test",
            file_path="/tmp/test.gguf",
            sha256="a" * 64,
            quantization="Q4_K_M",
            size_gb=1.2,
            pulled_at=datetime.now(timezone.utc),
            status="ready",
            benchmark_score=0.42,
            tokens_per_sec=88.0,
        )
        session.add(rec)
        session.commit()


def test_pull_endpoint_emits_error_event_on_invalid_source():
    app = create_app()
    client = TestClient(app)

    response = client.post("/models/pull", json={"source": "invalid-source"})
    assert response.status_code == 200
    assert "event: error" in response.text


def test_list_and_get_model():
    _insert_model("local-list-model")
    app = create_app()
    client = TestClient(app)

    response = client.get("/models/list")
    assert response.status_code == 200
    payload = response.json()
    assert any(item["model_id"] == "local-list-model" for item in payload)

    detail = client.get("/models/local-list-model")
    assert detail.status_code == 200
    assert detail.json()["status"] == "ready"


def test_benchmark_endpoint():
    _insert_model("local-bench-model")
    app = create_app()
    client = TestClient(app)

    response = client.get("/models/local-bench-model/benchmark")
    assert response.status_code == 200
    payload = response.json()
    assert abs(payload["benchmark_score"] - 0.42) < 1e-9
    assert abs(payload["tokens_per_sec"] - 88.0) < 1e-9


def test_delete_model_endpoint():
    _insert_model("local-delete-model")
    app = create_app()
    client = TestClient(app)

    delete_res = client.delete("/models/local-delete-model")
    assert delete_res.status_code == 200

    detail = client.get("/models/local-delete-model")
    assert detail.status_code == 404


def test_activate_endpoint(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

    def fake_post(url: str, timeout: int):
        assert "/models/local-activate-model/activate" in url
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    app = create_app()
    client = TestClient(app)

    response = client.post("/models/local-activate-model/activate")
    assert response.status_code == 200
    assert response.json()["ok"] is True
