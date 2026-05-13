from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from proposal_engine import ProposalCard

logger = logging.getLogger(__name__)

VYREX_URL = os.getenv("VYREX_URL", "http://vyrex-proxy:8105")
WORKSPACE_BASE = os.getenv("WORKSPACE_BASE", "/var/prady/projects")


@dataclass
class TestResult:
    __test__ = False
    passed: int = 0
    failed: int = 0
    failure_details: str = ""


@dataclass
class AgentResult:
    agent: str
    output: str = ""
    files_written: list[str] = field(default_factory=list)
    test_results: TestResult | None = None


@dataclass
class BuildResult:
    project_id: str
    workspace: str
    repo_path: str
    arch_output: AgentResult | None = None
    dev_output: AgentResult | None = None
    qa_output: AgentResult | None = None
    docs_output: AgentResult | None = None


class BuildTeam:
    async def build(self, proposal: ProposalCard, project_id: str) -> BuildResult:
        workspace = f"{WORKSPACE_BASE}/{project_id}"
        Path(workspace).mkdir(parents=True, exist_ok=True)

        subprocess.run(["git", "init"], cwd=workspace, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Prax"], cwd=workspace, capture_output=True)
        subprocess.run(["git", "config", "user.email", "prax@pradyos.local"], cwd=workspace, capture_output=True)

        arch = await self._run_architect(proposal, workspace)
        dev = await self._run_developer(proposal, arch, workspace)
        qa = await self._run_qa(proposal, dev, workspace)
        docs = await self._run_documenter(proposal, dev, qa, workspace)

        return BuildResult(
            project_id=project_id,
            workspace=workspace,
            repo_path=workspace,
            arch_output=arch,
            dev_output=dev,
            qa_output=qa,
            docs_output=docs,
        )

    async def _run_architect(self, proposal: ProposalCard, workspace: str) -> AgentResult:
        prompt = f"""You are the Architect Agent for Prax OS.
Your job is to design a complete system for this project.

Project: {proposal.what_to_build}
Problem: {proposal.problem_summary}
Tools available: {proposal.tools}
Time budget: {proposal.time_estimate_hours} hours

Produce:
1. System architecture document (ARCHITECTURE.md)
2. Complete file structure with every file listed
3. Tech stack decisions with justification
4. API contracts between components
5. Data models
6. Dependency list with exact versions

Be conservative. Only include what can be built in the time budget. Never overscope.
Write every document to {workspace}/docs/"""

        response = await self._call_vyrex(prompt, agent="architect")
        await self._write_files(response, workspace)
        await self._commit(workspace, "feat: architect — system design complete")
        return AgentResult(agent="architect", output=response, files_written=self._list_new_files(workspace))

    async def _run_developer(self, proposal: ProposalCard, arch: AgentResult, workspace: str) -> AgentResult:
        prompt = f"""You are the Developer Agent for Prax OS.
You write production-grade code.

Architecture: {arch.output[:3000]}
Project: {proposal.what_to_build}
Tools: {proposal.tools}

Rules:
- Write real working code, not placeholders
- Every function must do what its name says
- No TODO comments in production code
- No hardcoded secrets or API keys
- Use parameterized SQL, never f-string SQL
- Handle all errors gracefully
- Follow the exact file structure from Architecture

Write all source files to {workspace}/src/
After each major component, commit with a meaningful message.
Never commit broken code."""

        response = await self._call_vyrex(prompt, agent="developer")
        await self._write_files(response, workspace)
        await self._commit(workspace, "feat: developer — implementation complete")
        return AgentResult(agent="developer", output=response, files_written=self._list_new_files(workspace))

    async def _run_qa(self, proposal: ProposalCard, dev: AgentResult, workspace: str) -> AgentResult:
        prompt = f"""You are the QA Agent for Prax OS.
You write comprehensive tests and fix failures.

Code written: {dev.files_written}
Project: {proposal.what_to_build}

Write tests for:
- Every public function (happy path)
- Every public function (error path)
- Integration between components
- Edge cases for all user inputs

Rules:
- Use pytest for Python, vitest for TypeScript
- Mock all external HTTP calls with respx/msw
- Mock all filesystem operations in tests
- Never write a test that requires internet access
- Target: 100% of public functions covered
- Fix any code bugs you find during test writing

Run the tests and report results.
If tests fail: fix the source code, not the tests.
Keep fixing until all tests pass.
Write test files to {workspace}/tests/"""

        response = await self._call_vyrex(prompt, agent="qa")
        await self._write_files(response, workspace)

        test_result = await self._run_tests(workspace)
        retry = 0
        while test_result.failed > 0 and retry < 5:
            fix_prompt = f"""Tests are failing:
{test_result.failure_details}
Fix the source code to make these tests pass.
Do NOT change the test assertions. Only fix the implementation."""
            fix = await self._call_vyrex(fix_prompt, agent="qa")
            await self._write_files(fix, workspace)
            test_result = await self._run_tests(workspace)
            retry += 1

        await self._commit(workspace, f"test: qa — {test_result.passed} passing")
        return AgentResult(agent="qa", output=response, files_written=self._list_new_files(workspace), test_results=test_result)

    async def _run_documenter(self, proposal: ProposalCard, dev: AgentResult, qa: AgentResult, workspace: str) -> AgentResult:
        prompt = f"""You are the Documentation Agent for Prax OS.
You write clear honest documentation.

Project: {proposal.what_to_build}
Files written: {dev.files_written}
Tests passing: {qa.test_results.passed if qa.test_results else 0}

Write:
1. README.md — what it does, how to install, how to use, what it does NOT do (be honest)
2. API.md — every endpoint with examples
3. GUIDE.md — step by step for a new user
4. HONEST_LIMITATIONS.md — known limitations, what was not implemented, what might fail

Rules:
- Never claim a feature works if tests do not cover it
- If something is experimental, say experimental
- Installation steps must work from a clean machine
- Include the exact test command and expected output

Write all docs to {workspace}/docs/"""

        response = await self._call_vyrex(prompt, agent="documenter")
        await self._write_files(response, workspace)
        await self._commit(workspace, "docs: documenter — documentation complete")
        return AgentResult(agent="documenter", output=response, files_written=self._list_new_files(workspace))

    async def _call_vyrex(self, prompt: str, agent: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=120.0) as c:
                r = await c.post(
                    f"{VYREX_URL}/v1/chat/completions",
                    json={
                        "model": "active",
                        "messages": [
                            {
                                "role": "system",
                                "content": f"You are the {agent} agent inside Prax, the autonomous AI agent in Prady OS. You write production code only. You never fake output. You never write placeholders.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 8000,
                        "temperature": 0.2,
                    },
                )
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("vyrex call failed for agent %s: %s", agent, e)
            return ""

    async def _write_files(self, llm_output: str, workspace: str) -> None:
        pattern = r'```(\S+)\n(.*?)```'
        matches = re.findall(pattern, llm_output, re.DOTALL)
        for filename, content in matches:
            if filename in ("python", "typescript", "bash", "json", "yaml", "sh", "text", "plaintext"):
                continue
            filepath = Path(workspace) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content.strip())

    async def _run_tests(self, workspace: str) -> TestResult:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed = len(re.findall(r" PASSED", result.stdout))
            failed = len(re.findall(r" FAILED", result.stdout))
            return TestResult(passed=passed, failed=failed, failure_details=result.stdout if failed > 0 else "")
        except subprocess.TimeoutExpired:
            return TestResult(passed=0, failed=1, failure_details="Test suite timed out")
        except FileNotFoundError:
            return TestResult(passed=0, failed=0, failure_details="")

    async def _commit(self, workspace: str, message: str) -> None:
        subprocess.run(["git", "add", "-A"], cwd=workspace, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], cwd=workspace, capture_output=True)

    def _list_new_files(self, workspace: str) -> list[str]:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        out = result.stdout.strip()
        return out.split("\n") if out else []
