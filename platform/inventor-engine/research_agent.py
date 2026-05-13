from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

VYREX_URL = os.getenv("VYREX_URL", "http://vyrex-proxy:8105")


@dataclass
class Problem:
    title: str
    description: str
    source_url: str
    feasibility_score: float
    impact_score: float
    novelty_score: float
    composite_score: float
    tags: list[str] = field(default_factory=list)


@dataclass
class Research:
    problem: Problem
    related_papers: list[str] = field(default_factory=list)
    existing_approaches: list[str] = field(default_factory=list)
    proposed_approach: str = ""
    required_tools: list[str] = field(default_factory=list)
    estimated_hours: int = 0


class ResearchAgent:
    def __init__(self):
        self.http: httpx.AsyncClient = httpx.AsyncClient(timeout=15.0)

    async def scan(self) -> list[Problem]:
        try:
            results = await asyncio.gather(
                self._fetch_arxiv(),
                self._fetch_hackernews(),
                self._fetch_github_trending(),
                return_exceptions=True,
            )
        except Exception as e:
            logger.warning("scan sources failed: %s", e)
            return []

        all_problems: list[Problem] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("source fetch error: %s", r)
                continue
            all_problems.extend(r)

        scored = [p for p in all_problems if p.composite_score >= 0.6]
        scored.sort(key=lambda p: p.composite_score, reverse=True)
        deduplicated = self._deduplicate(scored)
        return deduplicated[:5]

    async def _fetch_arxiv(self) -> list[Problem]:
        try:
            url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.SE&sortBy=submittedDate&sortOrder=descending&max_results=10"
            r = await self.http.get(url, timeout=15.0)
            r.raise_for_status()
            import feedparser
            feed = feedparser.parse(r.text)
            problems = []
            for entry in feed.entries[:5]:
                title = entry.get("title", "").replace("\n", " ").strip()
                summary = entry.get("summary", "").replace("\n", " ").strip()[:300]
                problems.append(Problem(
                    title=title,
                    description=summary,
                    source_url=entry.get("link", ""),
                    feasibility_score=0.7,
                    impact_score=0.6,
                    novelty_score=0.8,
                    composite_score=0.7 * 0.6 * 0.8,
                    tags=["research", "ai"],
                ))
            return problems
        except Exception as e:
            logger.warning("arxiv fetch failed: %s", e)
            return []

    async def _fetch_hackernews(self) -> list[Problem]:
        try:
            r = await self.http.get(
                "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=20",
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            problems = []
            for hit in data.get("hits", [])[:5]:
                title = hit.get("title", "")
                url = hit.get("url") or hit.get("hnURL", "")
                points = hit.get("points", 0)
                impact = min(0.9, 0.3 + (points / 100) * 0.6)
                problems.append(Problem(
                    title=title,
                    description=f"HackerNews story with {points} points",
                    source_url=url,
                    feasibility_score=0.6,
                    impact_score=impact,
                    novelty_score=0.5,
                    composite_score=0.6 * impact * 0.5,
                    tags=["hackernews", "trending"],
                ))
            return problems
        except Exception as e:
            logger.warning("hackernews fetch failed: %s", e)
            return []

    async def _fetch_github_trending(self) -> list[Problem]:
        try:
            r = await self.http.get(
                "https://api.github.com/search/repositories?q=stars:>1000+pushed:>2024-01-01&sort=stars&order=desc&per_page=10",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            problems = []
            for item in data.get("items", [])[:5]:
                desc = item.get("description") or ""
                problems.append(Problem(
                    title=item.get("full_name", ""),
                    description=desc,
                    source_url=item.get("html_url", ""),
                    feasibility_score=0.8,
                    impact_score=0.7,
                    novelty_score=0.4,
                    composite_score=0.8 * 0.7 * 0.4,
                    tags=["github", "trending"],
                ))
            return problems
        except Exception as e:
            logger.warning("github fetch failed: %s", e)
            return []

    def _deduplicate(self, problems: list[Problem]) -> list[Problem]:
        seen_titles: set[str] = set()
        unique: list[Problem] = []
        for p in problems:
            key = p.title.lower().strip()[:60]
            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(p)
        return unique

    async def verify_novelty(self, problem: Problem) -> bool:
        try:
            query = problem.title.replace(" ", "+")
            r = await self.http.get(
                f"https://api.github.com/search/repositories?q={query}&per_page=3",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()
            total = data.get("total_count", 0)
            return total < 5
        except Exception:
            return True

    async def deep_research(self, problem: Problem) -> Research:
        try:
            prompt = f"""Research this problem and design a solution:

Problem: {problem.title}
Description: {problem.description}

1. Find related academic papers
2. Analyze existing open-source approaches
3. Design a proposed solution architecture
4. List required tools and estimated time

Be specific and realistic. Output in plain text."""
            response = await self._call_vyrex(prompt)
            return Research(
                problem=problem,
                related_papers=[],
                existing_approaches=[],
                proposed_approach=response[:2000] if response else "",
                required_tools=[],
                estimated_hours=8,
            )
        except Exception as e:
            logger.warning("deep_research failed: %s", e)
            return Research(problem=problem)

    async def _call_vyrex(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.post(
                    f"{VYREX_URL}/v1/chat/completions",
                    json={
                        "model": "active",
                        "messages": [
                            {"role": "system", "content": "You are a research assistant for Prax OS. Be thorough and specific."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3,
                    },
                )
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("vyrex call failed: %s", e)
            return ""
