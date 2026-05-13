from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from proposal_engine import ProposalCard, ProposalEngine


@pytest.fixture
def engine():
    return ProposalEngine()


@pytest.mark.asyncio
async def test_generate_returns_proposal_with_all_fields(engine: ProposalEngine, sample_research):
    engine._parse_response = lambda r, rs: ProposalCard(
        proposal_id="test-id",
        problem_summary="Test problem",
        why_it_matters="It matters",
        what_to_build="Build a tool",
        tools=[{"name": "Python", "license": "PSF-2.0", "purpose": "CLI"}],
        time_estimate_hours=8,
        deliverables=["CLI tool", "Tests"],
        confidence_level="high",
        honest_caveats=["May not work in all cases"],
        created_ts="2026-01-01T00:00:00Z",
    )
    proposal = await engine.generate(sample_research)
    assert isinstance(proposal, ProposalCard)
    assert proposal.proposal_id
    assert proposal.problem_summary
    assert proposal.why_it_matters
    assert proposal.what_to_build
    assert proposal.time_estimate_hours > 0
    assert len(proposal.deliverables) > 0
    assert proposal.confidence_level
    assert isinstance(proposal.honest_caveats, list)


@pytest.mark.asyncio
async def test_problem_summary_is_one_sentence(engine: ProposalEngine, sample_research):
    parsed = engine._parse_response("SUMMARY: This is one sentence.\nWHY: Helps\nWHAT: Tool\nTOOLS: Python\nLICENSES: MIT\nTIME_HOURS: 4\nDELIVERABLES: Code\nCONFIDENCE: high\nCAVEATS: None", sample_research)
    assert len(parsed.problem_summary.split(".")) <= 2
    assert "jargon" not in parsed.problem_summary.lower()


@pytest.mark.asyncio
async def test_confidence_is_valid_value(engine: ProposalEngine, sample_research):
    parsed = engine._parse_response("SUMMARY: Test\nWHY: Help\nWHAT: Tool\nTOOLS: Python\nLICENSES: MIT\nTIME_HOURS: 4\nDELIVERABLES: Code\nCONFIDENCE: experimental\nCAVEATS: Bugs", sample_research)
    assert parsed.confidence_level in ("high", "medium", "experimental")


@pytest.mark.asyncio
async def test_honest_caveats_is_non_empty(engine: ProposalEngine, sample_research):
    engine._parse_response = lambda r, rs: ProposalCard(
        proposal_id="test", problem_summary="Test", why_it_matters="Help",
        what_to_build="Tool", tools=[], time_estimate_hours=8,
        deliverables=[], confidence_level="medium",
        honest_caveats=["Unknown unknowns"], created_ts="",
    )
    proposal = await engine.generate(sample_research)
    assert len(proposal.honest_caveats) >= 1


@pytest.mark.asyncio
async def test_all_tools_have_license(engine: ProposalEngine, sample_research):
    parsed = engine._parse_response(
        "SUMMARY: Test\nWHY: Help\nWHAT: Tool\nTOOLS: Python, Click\nLICENSES: PSF-2.0, BSD-3-Clause\nTIME_HOURS: 4\nDELIVERABLES: Code\nCONFIDENCE: high\nCAVEATS: None",
        sample_research,
    )
    for tool in parsed.tools:
        assert "license" in tool
        assert tool["license"]


@pytest.mark.asyncio
async def test_time_estimate_is_positive_int(engine: ProposalEngine, sample_research):
    parsed = engine._parse_response("SUMMARY: Test\nWHY: Help\nWHAT: Tool\nTOOLS: Python\nLICENSES: MIT\nTIME_HOURS: 0\nDELIVERABLES: Code\nCONFIDENCE: medium\nCAVEATS: None", sample_research)
    assert parsed.time_estimate_hours >= 1
