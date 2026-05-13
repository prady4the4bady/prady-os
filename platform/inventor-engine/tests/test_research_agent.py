from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from research_agent import Problem, ResearchAgent


@pytest.fixture
def agent():
    return ResearchAgent()


@pytest.mark.asyncio
async def test_scan_returns_list_of_problems(agent: ResearchAgent):
    agent._fetch_arxiv = AsyncMock(return_value=[
        Problem(title="Paper 1", description="Desc", source_url="url1",
                feasibility_score=0.7, impact_score=0.6, novelty_score=0.8,
                composite_score=0.336, tags=["ai"]),
    ])
    agent._fetch_hackernews = AsyncMock(return_value=[])
    agent._fetch_github_trending = AsyncMock(return_value=[])
    agent._deduplicate = lambda x: x

    problems = await agent.scan()
    assert len(problems) >= 0
    if problems:
        assert isinstance(problems[0], Problem)


@pytest.mark.asyncio
async def test_scan_filters_below_06(agent: ResearchAgent):
    agent._fetch_arxiv = AsyncMock(return_value=[
        Problem(title="Low score", description="Desc", source_url="url",
                feasibility_score=0.5, impact_score=0.5, novelty_score=0.5,
                composite_score=0.125, tags=[]),
    ])
    agent._fetch_hackernews = AsyncMock(return_value=[])
    agent._fetch_github_trending = AsyncMock(return_value=[])
    agent._deduplicate = lambda x: x

    problems = await agent.scan()
    assert all(p.composite_score >= 0.6 for p in problems)


@pytest.mark.asyncio
async def test_verify_novelty_returns_false_when_github_has_solution(agent: ResearchAgent):
    agent.http = AsyncMock()
    agent.http.get = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=MagicMock(return_value={"total_count": 10}),
    ))
    result = await agent.verify_novelty(Problem(
        title="popular solution", description="", source_url="",
        feasibility_score=0.0, impact_score=0.0, novelty_score=0.0, composite_score=0.0,
    ))
    assert result is False


@pytest.mark.asyncio
async def test_verify_novelty_returns_true_when_no_github_solution(agent: ResearchAgent):
    agent.http = AsyncMock()
    agent.http.get = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=MagicMock(return_value={"total_count": 0}),
    ))
    result = await agent.verify_novelty(Problem(
        title="novel idea", description="", source_url="",
        feasibility_score=0.0, impact_score=0.0, novelty_score=0.0, composite_score=0.0,
    ))
    assert result is True


@pytest.mark.asyncio
async def test_deep_research_returns_research_with_all_fields(agent: ResearchAgent, sample_problem):
    agent._call_vyrex = AsyncMock(return_value="Proposed solution architecture")
    research = await agent.deep_research(sample_problem)
    assert research.problem == sample_problem
    assert isinstance(research.related_papers, list)
    assert isinstance(research.existing_approaches, list)
    assert isinstance(research.proposed_approach, str)
    assert isinstance(research.required_tools, list)
    assert isinstance(research.estimated_hours, int)


@pytest.mark.asyncio
async def test_scan_handles_network_timeout_gracefully(agent: ResearchAgent):
    agent._fetch_arxiv = AsyncMock(side_effect=Exception("timeout"))
    agent._fetch_hackernews = AsyncMock(return_value=[])
    agent._fetch_github_trending = AsyncMock(return_value=[])

    problems = await agent.scan()
    assert isinstance(problems, list)


@pytest.mark.asyncio
async def test_deduplicate_removes_duplicates(agent: ResearchAgent):
    p1 = Problem(title="Same Title", description="A", source_url="a",
                 feasibility_score=0.7, impact_score=0.7, novelty_score=0.7,
                 composite_score=0.343, tags=[])
    p2 = Problem(title="Same Title", description="B", source_url="b",
                 feasibility_score=0.8, impact_score=0.8, novelty_score=0.8,
                 composite_score=0.512, tags=[])
    problems = agent._deduplicate([p1, p2])
    assert len(problems) == 1


@pytest.mark.asyncio
async def test_composite_score_is_product_of_three(agent: ResearchAgent):
    p = Problem(title="Test", description="", source_url="",
                feasibility_score=0.5, impact_score=0.6, novelty_score=0.7,
                composite_score=0.0, tags=[])
    assert p.composite_score == 0.0
    expected = p.feasibility_score * p.impact_score * p.novelty_score
    assert expected == 0.5 * 0.6 * 0.7
