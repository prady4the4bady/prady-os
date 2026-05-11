"""Tests for eBPF hardening service — test_ebpf_loader.py

Unit tests with mocked subprocess (clang compilation).
"""
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, call

import pytest
import psutil
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Setup path to import service module
SERVICE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVICE_DIR))

import ebpf_loader as svc


@pytest.fixture
def app_client():
    """FastAPI test client."""
    return TestClient(svc.app)


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset global state before each test."""
    svc.PROGRAMS.clear()
    svc.DENIAL_EVENTS.clear()
    yield


class TestHealthEndpoint:
    def test_health_check(self, app_client):
        res = app_client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "ebpf-hardening"


class TestProgramManagement:
    @patch("ebpf_loader._compile_program")
    @patch("ebpf_loader._load_program")
    def test_load_program(self, mock_load, mock_compile, app_client):
        """Test loading an eBPF program."""
        # Mock compilation and loading
        mock_compile.return_value = "/fake/path/test_prog.bpf.o"
        mock_load.return_value = "handle-123"
        
        # Verify program not loaded yet
        assert "test_prog" not in svc.PROGRAMS
        
        # Load program
        res = app_client.post("/programs/test_prog/load")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["name"] == "test_prog"
        assert "handle" in data
        assert "loaded_at" in data
        
        # Verify program is in state
        assert "test_prog" in svc.PROGRAMS
        prog = svc.PROGRAMS["test_prog"]
        assert prog.name == "test_prog"
        assert prog.syscall_count == 0
        assert prog.denial_count == 0
        assert prog.attached_pids == []
    
    @patch("subprocess.run")
    def test_load_program_already_loaded(self, mock_run, app_client):
        """Test loading a program that's already loaded."""
        mock_run.return_value = MagicMock(returncode=0)
        with patch("pathlib.Path.exists", return_value=True):
            # Load once
            res1 = app_client.post("/programs/test_prog/load")
            assert res1.status_code == 200
            
            # Try to load again
            res2 = app_client.post("/programs/test_prog/load")
            assert res2.status_code == 409  # Conflict
            assert "already loaded" in res2.json()["detail"]
    
    @patch("subprocess.run")
    def test_unload_program(self, mock_run, app_client):
        """Test unloading an eBPF program."""
        mock_run.return_value = MagicMock(returncode=0)
        with patch("pathlib.Path.exists", return_value=True):
            # Load
            res1 = app_client.post("/programs/test_prog/load")
            assert res1.status_code == 200
            assert "test_prog" in svc.PROGRAMS
            
            # Unload
            res2 = app_client.delete("/programs/test_prog/unload")
            assert res2.status_code == 200
            data = res2.json()
            assert data["ok"] is True
            assert data["name"] == "test_prog"
            
            # Verify removed from state
            assert "test_prog" not in svc.PROGRAMS
    
    def test_unload_nonexistent_program(self, app_client):
        """Test unloading a program that doesn't exist."""
        res = app_client.delete("/programs/nonexistent/unload")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"]


class TestProgramStats:
    @patch("subprocess.run")
    def test_get_program_stats(self, mock_run, app_client):
        """Test getting stats for a loaded program."""
        mock_run.return_value = MagicMock(returncode=0)
        with patch("pathlib.Path.exists", return_value=True):
            # Load program
            res1 = app_client.post("/programs/test_prog/load")
            assert res1.status_code == 200
            
            # Get stats
            res2 = app_client.get("/programs/test_prog/stats")
            assert res2.status_code == 200
            data = res2.json()
            assert data["name"] == "test_prog"
            assert data["syscall_count"] == 0
            assert data["denial_count"] == 0
            assert data["attached_pids"] == []
            assert "loaded_at" in data
            assert "handle" in data
    
    def test_get_nonexistent_program_stats(self, app_client):
        """Test getting stats for a nonexistent program."""
        res = app_client.get("/programs/nonexistent/stats")
        assert res.status_code == 404


class TestListPrograms:
    @patch("subprocess.run")
    def test_list_empty(self, mock_run, app_client):
        """Test listing programs when none are loaded."""
        res = app_client.get("/programs")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["programs"] == []
    
    @patch("subprocess.run")
    def test_list_multiple(self, mock_run, app_client):
        """Test listing multiple loaded programs."""
        mock_run.return_value = MagicMock(returncode=0)
        with patch("pathlib.Path.exists", return_value=True):
            # Load two programs
            app_client.post("/programs/prog1/load")
            app_client.post("/programs/prog2/load")
            
            # List
            res = app_client.get("/programs")
            assert res.status_code == 200
            data = res.json()
            assert data["total"] == 2
            assert len(data["programs"]) == 2
            
            names = {p["name"] for p in data["programs"]}
            assert names == {"prog1", "prog2"}


class TestSandboxing:
    @patch("psutil.Process")
    @patch("subprocess.run")
    def test_sandbox_agent(self, mock_run, mock_process, app_client):
        """Test sandboxing a prax-agent process."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_process_inst = MagicMock()
        mock_process.return_value = mock_process_inst
        
        pid = 12345
        
        res = app_client.post(f"/sandbox/agent?pid={pid}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["program"] == "prax_agent_seccomp"
        assert data["pid"] == pid
        
        # Verify program is loaded and PID is attached
        assert "prax_agent_seccomp" in svc.PROGRAMS
        prog = svc.PROGRAMS["prax_agent_seccomp"]
        assert pid in prog.attached_pids
    
    @patch("psutil.Process")
    @patch("subprocess.run")
    def test_sandbox_computer_use(self, mock_run, mock_process, app_client):
        """Test sandboxing a computer-use process."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_process_inst = MagicMock()
        mock_process.return_value = mock_process_inst
        
        pid = 54321
        
        res = app_client.post(f"/sandbox/computer-use?pid={pid}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["program"] == "computer_use_lsm"
        assert data["pid"] == pid
        
        # Verify program is loaded and PID is attached
        assert "computer_use_lsm" in svc.PROGRAMS
        prog = svc.PROGRAMS["computer_use_lsm"]
        assert pid in prog.attached_pids
    
    @patch("psutil.Process")
    def test_sandbox_agent_invalid_pid(self, mock_process, app_client):
        """Test sandboxing with invalid PID."""
        mock_process.side_effect = psutil.NoSuchProcess(99999)
        
        res = app_client.post("/sandbox/agent?pid=99999")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
    
    @patch("psutil.Process")
    @patch("subprocess.run")
    def test_detach_agent(self, mock_run, mock_process, app_client):
        """Test detaching prax_agent_seccomp from a process."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_process_inst = MagicMock()
        mock_process.return_value = mock_process_inst
        
        pid = 12345
        
        # Attach
        res1 = app_client.post(f"/sandbox/agent?pid={pid}")
        assert res1.status_code == 200
        assert pid in svc.PROGRAMS["prax_agent_seccomp"].attached_pids
        
        # Detach
        res2 = app_client.post(f"/sandbox/agent/detach?pid={pid}")
        assert res2.status_code == 200
        data = res2.json()
        assert data["ok"] is True
        assert data["program"] == "prax_agent_seccomp"
        assert data["pid"] == pid
        
        # Verify PID is removed
        assert pid not in svc.PROGRAMS["prax_agent_seccomp"].attached_pids


class TestAuditDenials:
    def test_get_empty_denials(self, app_client):
        """Test getting denials when none exist."""
        res = app_client.get("/audit/denials")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["events"] == []
        assert data["limit"] == 50
        assert data["offset"] == 0
    
    def test_get_denials_with_pagination(self, app_client):
        """Test pagination of denial events."""
        # Manually add some denial events
        for i in range(100):
            svc.DENIAL_EVENTS.append({"event_id": i, "denied": True})
        
        # Get first page
        res1 = app_client.get("/audit/denials?limit=30&offset=0")
        assert res1.status_code == 200
        data1 = res1.json()
        assert len(data1["events"]) == 30
        assert data1["total"] == 100
        
        # Get second page
        res2 = app_client.get("/audit/denials?limit=30&offset=30")
        assert res2.status_code == 200
        data2 = res2.json()
        assert len(data2["events"]) == 30
        assert data2["offset"] == 30
