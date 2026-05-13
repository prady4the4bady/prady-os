from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from build_team import AgentResult, BuildResult, TestResult
from verifier_agent import VerifierAgent, VerificationResult


@pytest.fixture
def verifier():
    return VerifierAgent()


@pytest.fixture
def sample_build(tmp_path: Path) -> BuildResult:
    return BuildResult(
        project_id="test-proj-001",
        workspace=str(tmp_path),
        repo_path=str(tmp_path),
        arch_output=AgentResult(agent="architect", output="arch", files_written=[]),
        dev_output=AgentResult(agent="developer", output="dev", files_written=[]),
        qa_output=AgentResult(agent="qa", output="qa", files_written=[], test_results=TestResult(passed=10, failed=0)),
        docs_output=AgentResult(agent="documenter", output="docs", files_written=[]),
    )


@pytest.mark.asyncio
async def test_verify_returns_verification_result_with_all_fields(verifier: VerifierAgent, sample_build: BuildResult, sample_proposal):
    verifier._run_verification = AsyncMock(return_value=VerificationResult(
        verified=True, test_pass_rate=1.0, demo_ran=True,
        claims_match_reality=True, failure_details=[], retry_count=0,
    ))

    result = await verifier.verify(sample_build, sample_proposal)
    assert isinstance(result, VerificationResult)
    assert hasattr(result, "verified")
    assert hasattr(result, "test_pass_rate")
    assert hasattr(result, "demo_ran")
    assert hasattr(result, "claims_match_reality")
    assert hasattr(result, "failure_details")
    assert hasattr(result, "retry_count")


@pytest.mark.asyncio
async def test_verify_returns_verified_true_when_all_checks_pass(verifier: VerifierAgent, sample_build: BuildResult, sample_proposal):
    verifier._run_verification = AsyncMock(return_value=VerificationResult(
        verified=True, test_pass_rate=1.0, demo_ran=True,
        claims_match_reality=True, failure_details=[], retry_count=0,
    ))

    result = await verifier.verify(sample_build, sample_proposal)
    assert result.verified is True
    assert result.test_pass_rate == 1.0


@pytest.mark.asyncio
async def test_verify_returns_verified_false_when_tests_fail(verifier: VerifierAgent, sample_build: BuildResult, sample_proposal):
    verifier._run_verification = AsyncMock(return_value=VerificationResult(
        verified=False, test_pass_rate=0.5, demo_ran=True,
        claims_match_reality=False, failure_details=["Tests failed: 5/10 passing"], retry_count=0,
    ))
    verifier._request_fix = AsyncMock()

    result = await verifier.verify(sample_build, sample_proposal)
    assert result.verified is False
    assert result.test_pass_rate == 0.5


@pytest.mark.asyncio
async def test_verify_retries_up_to_max_retries(verifier: VerifierAgent, sample_build: BuildResult, sample_proposal):
    call_count = [0]

    async def mock_run_ver(build, proposal, attempt):
        call_count[0] += 1
        return VerificationResult(
            verified=False, test_pass_rate=0.0, demo_ran=False,
            claims_match_reality=False, failure_details=["fail"], retry_count=attempt,
        )

    verifier._run_verification = AsyncMock(side_effect=mock_run_ver)
    verifier._request_fix = AsyncMock()

    result = await verifier.verify(sample_build, sample_proposal)
    assert result.verified is False
    assert verifier._run_verification.call_count == VerifierAgent.MAX_RETRIES


@pytest.mark.asyncio
async def test_cleanup_container_on_failure(verifier: VerifierAgent, sample_build: BuildResult, sample_proposal):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # docker run
            MagicMock(returncode=0, stdout="", stderr=""),  # docker cp
            MagicMock(returncode=0, stdout="test_a.py::test_1 FAILED\ntest_a.py::test_2 PASSED\ntest_a.py::test_3 FAILED", stderr=""),  # docker exec pytest
            MagicMock(returncode=0, stdout="", stderr=""),  # docker rm -f
        ]
        result = await verifier._run_verification(sample_build, sample_proposal, 0)
        assert result.verified is False

    cleanup_calls = [c for c in mock_run.call_args_list if "rm" in str(c)]
    assert len(cleanup_calls) >= 1


@pytest.mark.asyncio
async def test_cleanup_container_on_success(verifier: VerifierAgent, sample_build: BuildResult, sample_proposal):
    (Path(sample_build.workspace) / "README.md").write_text("x" * 200)
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # docker run
            MagicMock(returncode=0, stdout="", stderr=""),  # docker cp
            MagicMock(returncode=0, stdout="test_x.py::test_a PASSED\ntest_x.py::test_b PASSED\ntest_x.py::test_c PASSED", stderr=""),  # docker exec pytest
            MagicMock(returncode=0, stdout="", stderr=""),  # docker rm -f
        ]
        result = await verifier._run_verification(sample_build, sample_proposal, 0)
        assert result.verified is True

    cleanup_calls = [c for c in mock_run.call_args_list if "rm" in str(c)]
    assert len(cleanup_calls) >= 1


def test_extract_install_steps(verifier: VerifierAgent):
    readme = """# Project
## Install
pip install -r requirements.txt
npm install
## Usage
do something"""
    steps = verifier._extract_install_steps(readme)
    assert "pip install -r requirements.txt" in steps
    assert "npm install" in steps


def test_extract_install_steps_skips_code_blocks(verifier: VerifierAgent):
    readme = """## Install
```
pip install something
```
pip install real-package"""
    steps = verifier._extract_install_steps(readme)
    assert "pip install real-package" in steps


@pytest.mark.asyncio
async def test_verify_claims_returns_false_when_readme_empty(verifier: VerifierAgent, sample_build: BuildResult, sample_proposal):
    (Path(sample_build.workspace) / "README.md").write_text("")
    result = await verifier._verify_claims("container", sample_proposal, sample_build)
    assert result is False
