"""Tests for the Kryos Researcher service.

All network I/O is either monkey-patched or intercepted with respx so
the test suite remains fully offline and deterministic.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response


@pytest.fixture
def researcher_module(tmp_path, monkeypatch):
    """Import the service module with a throw-away DATA_DIR so each test
    gets its own sqlite database and does not pollute the workspace."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Freeze the schedule so nothing runs on its own during tests.
    monkeypatch.setenv("RESEARCH_ENABLED", "false")
    # Force fresh import every test so module-level state reflects env.
    import importlib
    import asyncio

    import kryos_researcher  # type: ignore[import-not-found]

    importlib.reload(kryos_researcher)
    # Pre-create the schema so tests can hit the DB without a lifespan.
    asyncio.new_event_loop().run_until_complete(kryos_researcher._init_db())
    return kryos_researcher


def test_health_endpoint(researcher_module):
    with TestClient(researcher_module.app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "kryos-researcher"


def test_status_empty_db(researcher_module):
    with TestClient(researcher_module.app) as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_notes"] == 0
        assert body["total_proposals"] == 0
        assert body["daily_proposals_used"] == 0


def test_make_note_content_hash_is_stable(researcher_module):
    n1 = researcher_module._make_note(
        source="arxiv",
        source_id="2601.12345",
        title="Some title",
        summary="Some summary",
        url="http://arxiv.org/abs/2601.12345",
        tags=["cs.AI"],
    )
    n2 = researcher_module._make_note(
        source="arxiv",
        source_id="2601.12345",
        title="Some title",
        summary="Some summary",
        url="http://arxiv.org/abs/2601.12345",
        tags=["cs.AI"],
    )
    assert n1.content_hash == n2.content_hash
    assert n1.id != n2.id  # ids are random per call


@pytest.mark.anyio
async def test_save_notes_dedupes_on_hash(researcher_module):
    await researcher_module._init_db()
    n1 = researcher_module._make_note(
        source="arxiv", source_id="x", title="t", summary="s",
        url="u", tags=[],
    )
    # Second note, same content → same hash.
    n2 = researcher_module._make_note(
        source="arxiv", source_id="x", title="t", summary="s",
        url="u", tags=[],
    )
    inserted_first = await researcher_module._save_notes([n1])
    inserted_second = await researcher_module._save_notes([n2])
    assert inserted_first == 1
    assert inserted_second == 0  # duplicate


@respx.mock
@pytest.mark.anyio
async def test_fetch_arxiv_parses_atom_feed(researcher_module):
    feed = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.00001</id>
    <title>Test paper</title>
    <summary>A short abstract.</summary>
  </entry>
</feed>
"""
    respx.get(
        "http://export.arxiv.org/api/query",
        params={"search_query": "cat:cs.AI"},
    ).mock(return_value=Response(200, text=feed))

    async with httpx.AsyncClient() as client:
        notes = await researcher_module._fetch_arxiv(client, "cs.AI")

    assert len(notes) == 1
    assert notes[0].title == "Test paper"
    assert notes[0].source == "arxiv"
    assert notes[0].source_id == "http://arxiv.org/abs/2601.00001"


@respx.mock
@pytest.mark.anyio
async def test_fetch_arxiv_swallows_http_errors(researcher_module):
    respx.get(
        "http://export.arxiv.org/api/query",
        params={"search_query": "cat:cs.AI"},
    ).mock(return_value=Response(503, text=""))

    async with httpx.AsyncClient() as client:
        notes = await researcher_module._fetch_arxiv(client, "cs.AI")

    assert notes == []


@respx.mock
@pytest.mark.anyio
async def test_fetch_rss_parses_items(researcher_module):
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Feed</title>
    <item>
      <title>An item</title>
      <link>https://example.com/a</link>
      <description>Body</description>
      <guid>guid-1</guid>
    </item>
    <item>
      <title>Another item</title>
      <link>https://example.com/b</link>
      <description>Body 2</description>
    </item>
  </channel>
</rss>
"""
    respx.get("https://news.ycombinator.com/rss").mock(
        return_value=Response(200, text=rss)
    )

    async with httpx.AsyncClient() as client:
        notes = await researcher_module._fetch_rss(
            client, "https://news.ycombinator.com/rss"
        )

    assert len(notes) == 2
    assert notes[0].source == "rss"
    assert notes[0].title == "An item"


@respx.mock
@pytest.mark.anyio
async def test_fetch_github_trending_parses_json(researcher_module):
    payload = {
        "items": [
            {
                "full_name": "example/repo",
                "description": "cool repo",
                "html_url": "https://github.com/example/repo",
                "stargazers_count": 42,
            }
        ]
    }
    respx.get("https://api.github.com/search/repositories").mock(
        return_value=Response(200, json=payload)
    )

    async with httpx.AsyncClient() as client:
        notes = await researcher_module._fetch_github_trending(
            client, "python"
        )

    assert len(notes) == 1
    assert notes[0].source == "github"
    assert "example/repo" in notes[0].title
    assert notes[0].url == "https://github.com/example/repo"


@respx.mock
@pytest.mark.anyio
async def test_run_proposal_cycle_skips_when_few_notes(researcher_module):
    # With an empty DB, we shouldn't call the model-gateway at all.
    result = await researcher_module._run_proposal_cycle()
    assert result is None


@respx.mock
@pytest.mark.anyio
async def test_run_proposal_cycle_skips_when_budget_exhausted(
    researcher_module, monkeypatch
):
    # Pre-load the DB with the daily budget worth of proposals.
    await researcher_module._init_db()
    from kryos_researcher import ProposalResponse  # type: ignore[import-not-found]

    for i in range(researcher_module.DAILY_PROPOSAL_BUDGET):
        p = ProposalResponse(
            id=f"p{i}",
            title=f"t{i}",
            rationale="r",
            plan=[],
            sources=[],
            created_at=researcher_module._now_iso(),
        )
        await researcher_module._save_proposal(p, notification_id=None)

    result = await researcher_module._run_proposal_cycle()
    assert result is None


@respx.mock
@pytest.mark.anyio
async def test_run_proposal_cycle_emits_proposal_and_notification(
    researcher_module,
):
    # Seed enough notes.
    notes = [
        researcher_module._make_note(
            source="arxiv",
            source_id=f"x{i}",
            title=f"title {i}",
            summary=f"summary {i}",
            url=f"http://example/a{i}",
            tags=["cs.AI"],
        )
        for i in range(6)
    ]
    await researcher_module._save_notes(notes)

    # Stub the model-gateway to return a plausible JSON proposal.
    proposal_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "title": "Tiny graph benchmark",
                            "rationale": "Recent arXiv notes show a gap.",
                            "plan": ["Fork X", "Wire Y", "Measure Z"],
                            "sources": ["http://example/a0"],
                        }
                    ),
                }
            }
        ]
    }
    respx.post(
        f"{researcher_module.MODEL_GATEWAY_URL}/v1/chat/completions"
    ).mock(return_value=Response(200, json=proposal_payload))

    respx.post(
        f"{researcher_module.PROPOSAL_GATE_URL}/proposal"
    ).mock(return_value=Response(201, json={"id": "gate-xyz"}))

    respx.post(f"{researcher_module.NOTIFICATION_BUS_URL}/notify").mock(
        return_value=Response(201, json={"id": "notif-abc"})
    )

    proposal = await researcher_module._run_proposal_cycle()
    assert proposal is not None
    assert proposal.title == "Tiny graph benchmark"
    assert proposal.plan == ["Fork X", "Wire Y", "Measure Z"]
    # Gate id replaces the locally generated uuid.
    assert proposal.id == "gate-xyz"
    # Notification should have been emitted.
    notify_call = respx.calls.last
    assert notify_call.request.url.path == "/notify"


@respx.mock
@pytest.mark.anyio
async def test_run_proposal_cycle_skips_on_non_json_model_output(
    researcher_module,
):
    notes = [
        researcher_module._make_note(
            source="arxiv",
            source_id=f"x{i}",
            title=f"title {i}",
            summary="summary",
            url=f"http://example/a{i}",
            tags=[],
        )
        for i in range(6)
    ]
    await researcher_module._save_notes(notes)

    respx.post(
        f"{researcher_module.MODEL_GATEWAY_URL}/v1/chat/completions"
    ).mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "I cannot comply right now.",
                        }
                    }
                ]
            },
        )
    )

    proposal = await researcher_module._run_proposal_cycle()
    assert proposal is None


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"
