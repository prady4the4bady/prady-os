from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from research_agent import Research

logger = logging.getLogger(__name__)

VYREX_URL = os.getenv("VYREX_URL", "http://vyrex-proxy:8105")


@dataclass
class ProposalCard:
    proposal_id: str
    problem_summary: str
    why_it_matters: str
    what_to_build: str
    tools: list[dict] = field(default_factory=list)
    time_estimate_hours: int = 0
    deliverables: list[str] = field(default_factory=list)
    confidence_level: str = "medium"
    honest_caveats: list[str] = field(default_factory=list)
    created_ts: str = ""


class ProposalEngine:
    async def generate(self, research: Research) -> ProposalCard:
        system_prompt = (
            "You are Prax, an AI agent explaining a project proposal to "
            "the person who owns this computer. Be completely honest. "
            "Never exaggerate. Never use jargon. Explain as if the person "
            "is intelligent but not technical. If you are not sure "
            "something will work, say so."
        )

        user_prompt = f"""Based on this research, create a clear proposal:

Problem: {research.problem.title}
Description: {research.problem.description}
Proposed Approach: {research.proposed_approach}

Format your response EXACTLY as:

SUMMARY: <one plain English sentence, no jargon>
WHY: <who benefits and how>
WHAT: <12-year-old level explanation>
TOOLS: <comma-separated list of tools/libraries>
LICENSES: <comma-separated SPDX license IDs matching tools>
TIME_HOURS: <honest integer estimate>
DELIVERABLES: <comma-separated list>
CONFIDENCE: <high|medium|experimental>
CAVEATS: <comma-separated list of things that might not work>"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.post(
                    f"{VYREX_URL}/v1/chat/completions",
                    json={
                        "model": "active",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3,
                    },
                )
                response = r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("vyrex call failed for proposal: %s", e)
            response = ""

        parsed = self._parse_response(response, research)
        return parsed

    def _parse_response(self, response: str, research: Research) -> ProposalCard:
        lines = response.strip().split("\n")
        fields = {"SUMMARY": "", "WHY": "", "WHAT": "", "TOOLS": "", "LICENSES": "",
                   "TIME_HOURS": "8", "DELIVERABLES": "", "CONFIDENCE": "medium",
                   "CAVEATS": ""}
        for line in lines:
            for key in fields:
                if line.startswith(key + ":"):
                    fields[key] = line[len(key) + 1:].strip()

        tool_names = [t.strip() for t in fields["TOOLS"].split(",") if t.strip()]
        license_names = [l.strip() for l in fields["LICENSES"].split(",") if l.strip()]
        tools = []
        for i, name in enumerate(tool_names):
            lic = license_names[i] if i < len(license_names) else "Unknown"
            tools.append({"name": name, "license": lic, "purpose": name})

        try:
            time_hrs = max(1, int(fields["TIME_HOURS"]))
        except ValueError:
            time_hrs = 8

        deliverables = [d.strip() for d in fields["DELIVERABLES"].split(",") if d.strip()]
        if not deliverables:
            deliverables = ["Working CLI tool", "Test suite", "README documentation"]

        caveats = [c.strip() for c in fields["CAVEATS"].split(",") if c.strip()]

        confidence = fields["CONFIDENCE"].lower()
        if confidence not in ("high", "medium", "experimental"):
            confidence = "medium"

        return ProposalCard(
            proposal_id=str(uuid.uuid4()),
            problem_summary=fields["SUMMARY"] or research.problem.title,
            why_it_matters=fields["WHY"] or "Benefits developers and users",
            what_to_build=fields["WHAT"] or research.problem.description,
            tools=tools,
            time_estimate_hours=time_hrs,
            deliverables=deliverables,
            confidence_level=confidence,
            honest_caveats=caveats or ["Unknown unknowns may exist"],
            created_ts=datetime.now(timezone.utc).isoformat(),
        )
