from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from build_team import BuildResult, BuildTeam
from proposal_engine import ProposalCard

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    verified: bool = False
    test_pass_rate: float = 0.0
    demo_ran: bool = False
    claims_match_reality: bool = False
    failure_details: list[str] = field(default_factory=list)
    retry_count: int = 0


class VerifierAgent:
    MAX_RETRIES = 3

    async def verify(self, build_result: BuildResult, proposal: ProposalCard) -> VerificationResult:
        last_result = VerificationResult()
        for attempt in range(self.MAX_RETRIES):
            result = await self._run_verification(build_result, proposal, attempt)
            last_result = result
            if result.verified:
                return result
            await self._request_fix(build_result, result.failure_details)

        last_result.retry_count = self.MAX_RETRIES
        return last_result

    async def _run_verification(self, build: BuildResult, proposal: ProposalCard, attempt: int) -> VerificationResult:
        failures: list[str] = []
        container_name = f"prax-verify-{build.project_id}-{attempt}"

        clean_env = subprocess.run(
            ["docker", "run", "-d", "--name", container_name, "--rm", "python:3.12-slim", "sleep", "300"],
            capture_output=True,
            text=True,
        )
        if clean_env.returncode != 0:
            failures.append("Could not create clean container")
            return VerificationResult(
                verified=False, test_pass_rate=0.0, demo_ran=False,
                claims_match_reality=False, failure_details=failures, retry_count=attempt,
            )

        try:
            subprocess.run(["docker", "cp", build.workspace, f"{container_name}:/project"], capture_output=True)

            readme_path = Path(build.workspace) / "README.md"
            if readme_path.exists():
                readme = readme_path.read_text()
                install_steps = self._extract_install_steps(readme)
                for step in install_steps:
                    r = subprocess.run(
                        ["docker", "exec", container_name, "bash", "-c", step],
                        capture_output=True, text=True, timeout=60,
                    )
                    if r.returncode != 0:
                        failures.append(f"Install step failed: {step}\n{r.stderr}")

            test_run = subprocess.run(
                ["docker", "exec", container_name, "bash", "-c",
                 "cd /project && python -m pytest tests/ -q --tb=short"],
                capture_output=True, text=True, timeout=120,
            )
            passed = len(re.findall(r" PASSED", test_run.stdout))
            total = len(re.findall(r" (PASSED|FAILED)", test_run.stdout))
            pass_rate = passed / total if total > 0 else 0.0

            if pass_rate < 1.0:
                failures.append(f"Tests: {passed}/{total} passing\n{test_run.stdout}")

            claims_verified = await self._verify_claims(container_name, proposal, build)
            if not claims_verified:
                failures.append("Claimed features do not match actual behavior")

            verified = len(failures) == 0
            return VerificationResult(
                verified=verified,
                test_pass_rate=pass_rate,
                demo_ran=True,
                claims_match_reality=claims_verified,
                failure_details=failures,
                retry_count=attempt,
            )
        finally:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    async def _verify_claims(self, container: str, proposal: ProposalCard, build: BuildResult) -> bool:
        for deliverable in proposal.deliverables:
            if "test suite" in deliverable.lower():
                continue
            if "readme" in deliverable.lower():
                readme = Path(build.workspace) / "README.md"
                if not readme.exists() or readme.stat().st_size < 100:
                    return False
            if "working demo" in deliverable.lower():
                demo = Path(build.workspace) / "demo.py"
                if demo.exists():
                    r = subprocess.run(
                        ["docker", "exec", container, "bash", "-c", "cd /project && python demo.py"],
                        capture_output=True, text=True, timeout=60,
                    )
                    if r.returncode != 0:
                        return False
        return True

    def _extract_install_steps(self, readme: str) -> list[str]:
        lines = readme.split("\n")
        steps = []
        in_install = False
        for line in lines:
            if "## install" in line.lower():
                in_install = True
                continue
            if in_install and line.startswith("## "):
                break
            if in_install and line.startswith("```"):
                continue
            if in_install and line.strip().startswith("pip "):
                steps.append(line.strip())
            if in_install and line.strip().startswith("npm "):
                steps.append(line.strip())
        return steps

    async def _request_fix(self, build: BuildResult, failures: list[str]) -> None:
        team = BuildTeam()
        fix_prompt = f"""Verification failed with these issues:
{chr(10).join(failures)}
Fix these specific problems in the code.
Do not rewrite everything — only fix what failed."""
        response = await team._call_vyrex(fix_prompt, agent="developer")
        await team._commit(build.workspace, "fix: verifier requested fixes applied")
