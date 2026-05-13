from __future__ import annotations

import sys
from pathlib import Path

_service_dir = Path(__file__).resolve().parent.parent
if str(_service_dir) not in sys.path:
    sys.path.insert(0, str(_service_dir))

import pytest
from research_agent import Problem, Research
from proposal_engine import ProposalCard


@pytest.fixture
def sample_problem() -> Problem:
    return Problem(
        title="No open-source tool for detecting unused env vars",
        description="Developer teams waste hours debugging misconfigured deployments",
        source_url="https://github.com/example",
        feasibility_score=0.8,
        impact_score=0.9,
        novelty_score=0.7,
        composite_score=0.8 * 0.9 * 0.7,
        tags=["devtools", "cli"],
    )


@pytest.fixture
def sample_research(sample_problem: Problem) -> Research:
    return Research(
        problem=sample_problem,
        related_papers=["arxiv:1234"],
        existing_approaches=["dotenv-linter"],
        proposed_approach="A CLI tool that scans polyglot codebases for unused env vars",
        required_tools=["Python", "Click", "Pytest"],
        estimated_hours=8,
    )


@pytest.fixture
def sample_proposal() -> ProposalCard:
    return ProposalCard(
        proposal_id="test-prop-001",
        problem_summary="No open-source tool exists to detect unused environment variables",
        why_it_matters="Developer teams waste hours debugging misconfigured deployments",
        what_to_build="A CLI tool that scans projects for unused env vars",
        tools=[{"name": "Python", "license": "PSF-2.0", "purpose": "CLI"}],
        time_estimate_hours=8,
        deliverables=["Working CLI tool", "Test suite", "README"],
        confidence_level="high",
        honest_caveats=["May not detect dynamic env var names"],
        created_ts="2026-05-13T00:00:00Z",
    )



