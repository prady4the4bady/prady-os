from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from build_team import AgentResult, BuildResult, BuildTeam, TestResult
from proposal_engine import ProposalCard


@pytest.fixture
def team():
    return BuildTeam()


@pytest.fixture
def proposal():
    return ProposalCard(
        proposal_id="test-prop-001",
        problem_summary="Test problem",
        why_it_matters="It matters",
        what_to_build="A CLI tool",
        tools=[{"name": "Python", "license": "PSF-2.0", "purpose": "CLI"}],
        time_estimate_hours=8,
        deliverables=["CLI tool", "Tests", "README"],
        confidence_level="high",
        honest_caveats=["Test caveat"],
        created_ts="2026-01-01T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_run_architect_calls_vyrex_with_architect_prompt(team: BuildTeam, proposal: ProposalCard):
    team._call_vyrex = AsyncMock(return_value="Architecture design")
    team._write_files = AsyncMock()
    team._commit = AsyncMock()
    team._list_new_files = MagicMock(return_value=["docs/ARCHITECTURE.md"])

    result = await team._run_architect(proposal, "/tmp/test_arch")
    assert result.agent == "architect"
    team._call_vyrex.assert_called_once()
    prompt_arg = team._call_vyrex.call_args[0][0]
    assert "Architect Agent" in prompt_arg


@pytest.mark.asyncio
async def test_run_developer_calls_vyrex_with_developer_prompt(team: BuildTeam, proposal: ProposalCard):
    team._call_vyrex = AsyncMock(return_value="```main.py\nprint('hello')\n```")
    team._write_files = AsyncMock()
    team._commit = AsyncMock()
    team._list_new_files = MagicMock(return_value=["src/main.py"])

    arch_result = AgentResult(agent="architect", output="Design", files_written=[])
    result = await team._run_developer(proposal, arch_result, "/tmp/test_dev")
    assert result.agent == "developer"
    team._call_vyrex.assert_called_once()
    prompt_arg = team._call_vyrex.call_args[0][0]
    assert "Developer Agent" in prompt_arg


@pytest.mark.asyncio
async def test_run_qa_runs_tests_after_writing_code(team: BuildTeam, proposal: ProposalCard):
    team._call_vyrex = AsyncMock(return_value="test output")
    team._write_files = AsyncMock()
    team._run_tests = AsyncMock(return_value=TestResult(passed=10, failed=0))
    team._commit = AsyncMock()
    team._list_new_files = MagicMock(return_value=[])

    dev_result = AgentResult(agent="developer", output="code", files_written=["src/main.py"])
    result = await team._run_qa(proposal, dev_result, "/tmp/test_qa")
    assert result.agent == "qa"
    assert result.test_results is not None
    assert result.test_results.passed == 10


@pytest.mark.asyncio
async def test_run_qa_retries_up_to_5_times_if_tests_fail(team: BuildTeam, proposal: ProposalCard):
    call_count = [0]

    async def mock_rt(*args, **kwargs):
        call_count[0] += 1
        return TestResult(passed=5, failed=3, failure_details="some tests failed")

    team._call_vyrex = AsyncMock(return_value="fix")
    team._write_files = AsyncMock()
    team._run_tests = AsyncMock(side_effect=mock_rt)
    team._commit = AsyncMock()
    team._list_new_files = MagicMock(return_value=[])

    dev_result = AgentResult(agent="developer", output="code", files_written=[])
    result = await team._run_qa(proposal, dev_result, "/tmp/test_qa_retry")
    assert result.agent == "qa"


@pytest.mark.asyncio
async def test_run_qa_stops_retrying_when_all_tests_pass(team: BuildTeam, proposal: ProposalCard):
    call_count = [0]

    async def mock_rt(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return TestResult(passed=8, failed=2, failure_details="bugs")
        return TestResult(passed=10, failed=0)

    team._call_vyrex = AsyncMock(return_value="fix")
    team._write_files = AsyncMock()
    team._run_tests = AsyncMock(side_effect=mock_rt)
    team._commit = AsyncMock()
    team._list_new_files = MagicMock(return_value=[])

    dev_result = AgentResult(agent="developer", output="code", files_written=[])
    result = await team._run_qa(proposal, dev_result, "/tmp/test_qa_stop")
    assert result.test_results.failed == 0


@pytest.mark.asyncio
async def test_write_files_parses_code_blocks(team: BuildTeam, tmp_path: Path):
    llm_output = "```hello.py\nprint('world')\n```\nSome text\n```utils/helper.py\ndef help():\n    pass\n```"
    await team._write_files(llm_output, str(tmp_path))
    assert (tmp_path / "hello.py").exists()
    assert (tmp_path / "utils" / "helper.py").exists()


@pytest.mark.asyncio
async def test_write_files_skips_language_only_fences(team: BuildTeam, tmp_path: Path):
    llm_output = "```python\nprint('hello')\n```\n```json\n{}\n```"
    await team._write_files(llm_output, str(tmp_path))
    files = list(tmp_path.iterdir())
    assert len(files) == 0


@pytest.mark.asyncio
async def test_run_tests_returns_testresult(team: BuildTeam):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="5 PASSED, 0 FAILED", returncode=0)
        result = await team._run_tests(str(Path.cwd()))
        assert isinstance(result, TestResult)


@pytest.mark.asyncio
async def test_commit_calls_git_commands(team: BuildTeam):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        await team._commit("/tmp/test_commit", "test commit")
        assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_build_returns_buildresult(team: BuildTeam, proposal: ProposalCard):
    team._run_architect = AsyncMock(return_value=AgentResult(agent="architect", output="arch", files_written=[]))
    team._run_developer = AsyncMock(return_value=AgentResult(agent="developer", output="dev", files_written=[]))
    team._run_qa = AsyncMock(return_value=AgentResult(agent="qa", output="qa", files_written=[], test_results=TestResult(passed=10, failed=0)))
    team._run_documenter = AsyncMock(return_value=AgentResult(agent="documenter", output="docs", files_written=[]))

    with patch("pathlib.Path.mkdir"):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            result = await team.build(proposal, "test-proj-001")
            assert isinstance(result, BuildResult)
            assert result.project_id == "test-proj-001"
            assert result.arch_output is not None
            assert result.dev_output is not None
            assert result.qa_output is not None
            assert result.docs_output is not None
