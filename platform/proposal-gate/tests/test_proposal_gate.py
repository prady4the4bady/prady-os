from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response


@pytest.fixture
def gate(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import proposal_gate  # type: ignore[import-not-found]

    importlib.reload(proposal_gate)
    asyncio.new_event_loop().run_until_complete(proposal_gate._init_db())
    return proposal_gate


def _create(client: TestClient, title: str = "Build something useful") -> dict:
    resp = client.post(
        "/proposal",
        json={
            "title": title,
            "rationale": "There is a clear gap in public tooling for X.",
            "plan": ["Step A", "Step B", "Step C"],
            "sources": ["https://example.com/a"],
            "origin": "kryos-researcher",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@respx.mock
def test_health(gate):
    with TestClient(gate.app) as client:
        assert client.get("/health").json()["status"] == "ok"


@respx.mock
def test_create_and_get(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n1"})
    )
    with TestClient(gate.app) as client:
        p = _create(client)
        assert p["state"] == "PROPOSED"
        assert p["title"] == "Build something useful"
        assert len(p["history"]) == 1
        # Single-row genesis-chained create.
        assert p["history"][0]["from_state"] == "NONE"

        # Round-trip through GET /proposal/{id}
        p2 = client.get(f"/proposal/{p['id']}").json()
        assert p2["id"] == p["id"]


@respx.mock
def test_list_filtered(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n1"})
    )
    with TestClient(gate.app) as client:
        a = _create(client, "A")
        b = _create(client, "B")
        # Approve one
        respx.post(f"{gate.AGENT_RUNTIME_URL}/agents/spawn-from-proposal").mock(
            return_value=Response(202, json={"ok": True})
        )
        client.post(f"/proposal/{a['id']}/approve", json={"actor": "user"})

        proposed = client.get("/proposal?state=PROPOSED").json()
        approved = client.get("/proposal?state=APPROVED").json()
        assert len(proposed) == 1 and proposed[0]["id"] == b["id"]
        assert len(approved) == 1 and approved[0]["id"] == a["id"]


@respx.mock
def test_full_happy_path(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n"})
    )
    respx.post(f"{gate.AGENT_RUNTIME_URL}/agents/spawn-from-proposal").mock(
        return_value=Response(202, json={"ok": True})
    )
    with TestClient(gate.app) as client:
        p = _create(client)

        approved = client.post(
            f"/proposal/{p['id']}/approve", json={"actor": "user"}
        ).json()
        assert approved["state"] == "APPROVED"

        started = client.post(
            f"/proposal/{p['id']}/start", json={"actor": "prax"}
        ).json()
        assert started["state"] == "IN_PROGRESS"

        done = client.post(
            f"/proposal/{p['id']}/complete",
            json={"actor": "prax", "ok": True, "output": {"pr": "https://x/y/1"}},
        ).json()
        assert done["state"] == "DONE"
        assert done["result"] == {"ok": True, "output": {"pr": "https://x/y/1"}}


@respx.mock
def test_reject_from_proposed(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n"})
    )
    with TestClient(gate.app) as client:
        p = _create(client)
        r = client.post(
            f"/proposal/{p['id']}/reject",
            json={"actor": "user", "reason": "duplicate of earlier project"},
        ).json()
        assert r["state"] == "REJECTED"
        # Rejected terminal: cannot approve.
        resp = client.post(
            f"/proposal/{p['id']}/approve", json={"actor": "user"}
        )
        assert resp.status_code == 409


@respx.mock
def test_illegal_transition_proposed_to_done(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n"})
    )
    with TestClient(gate.app) as client:
        p = _create(client)
        resp = client.post(
            f"/proposal/{p['id']}/complete", json={"ok": True}
        )
        assert resp.status_code == 409


@respx.mock
def test_cannot_start_without_approve(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n"})
    )
    with TestClient(gate.app) as client:
        p = _create(client)
        resp = client.post(
            f"/proposal/{p['id']}/start", json={"actor": "prax"}
        )
        assert resp.status_code == 409


@respx.mock
def test_audit_chain_extends(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n"})
    )
    respx.post(f"{gate.AGENT_RUNTIME_URL}/agents/spawn-from-proposal").mock(
        return_value=Response(202, json={"ok": True})
    )
    with TestClient(gate.app) as client:
        p = _create(client)
        client.post(f"/proposal/{p['id']}/approve", json={"actor": "user"})
        client.post(f"/proposal/{p['id']}/start", json={"actor": "prax"})
        client.post(
            f"/proposal/{p['id']}/complete",
            json={"actor": "prax", "ok": True},
        )

        audit = client.get("/audit").json()
        # 1 create + 3 transitions = 4 rows for this single proposal.
        assert len([t for t in audit["transitions"] if t["proposal_id"] == p["id"]]) == 4

        # Chain must verify.
        v = client.get("/audit/verify").json()
        assert v["ok"] is True
        assert v["first_broken_id"] is None


@respx.mock
def test_agent_runtime_unreachable_does_not_block_approval(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "n"})
    )
    respx.post(f"{gate.AGENT_RUNTIME_URL}/agents/spawn-from-proposal").mock(
        return_value=Response(503, text="service down")
    )
    with TestClient(gate.app) as client:
        p = _create(client)
        r = client.post(
            f"/proposal/{p['id']}/approve", json={"actor": "user"}
        )
        # Approval still succeeds even though agent-runtime failed.
        assert r.status_code == 200
        assert r.json()["state"] == "APPROVED"


@respx.mock
def test_notification_bus_unreachable_does_not_block(gate):
    respx.post(f"{gate.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(503, text="bus down")
    )
    with TestClient(gate.app) as client:
        resp = client.post(
            "/proposal",
            json={
                "title": "still works",
                "rationale": "bus failures are not fatal",
                "plan": ["a"],
                "sources": [],
                "origin": "test",
            },
        )
        assert resp.status_code == 201
