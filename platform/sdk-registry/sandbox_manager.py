from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker

SANDBOX_NETWORK = "kryos-sdk-net"
WORKSPACE_BASE = "/home/user/kryos-apps"


@dataclass
class ContainerInfo:
    container_id: str
    status: str
    workspace_path: str


@dataclass
class AppStatus:
    status: str
    container_id: str | None
    uptime_seconds: int
    memory_used_mb: float
    cpu_pct: float


class SandboxManager:
    def __init__(self, docker_client=None, workspace_base: str = WORKSPACE_BASE):
        self._client = docker_client or docker.from_env()
        self.workspace_base = workspace_base

    def ensure_network(self) -> None:
        networks = self._client.networks.list(names=[SANDBOX_NETWORK])
        if not networks:
            self._client.networks.create(SANDBOX_NETWORK, driver="bridge", internal=False)

    def start_app(self, app_id: str, manifest: dict[str, Any]) -> ContainerInfo:
        self.ensure_network()
        workspace_path = Path(self.workspace_base) / app_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        image = f"{manifest['name']}:{manifest['version']}"
        run_kwargs: dict[str, Any] = {
            "image": image,
            "name": f"kryos-sdk-{app_id}",
            "network": SANDBOX_NETWORK,
            "mem_limit": f"{manifest['sandbox']['memory_mb']}m",
            "cpu_shares": manifest['sandbox']['cpu_shares'],
            "read_only": manifest['sandbox']['read_only_root'],
            "volumes": {str(workspace_path): {"bind": "/app/data", "mode": "rw"}},
            "environment": {
                "KRYOS_APP_ID": app_id,
                "KRYOS_API_BASE": "http://sdk-registry:8020",
                "KRYOS_VYREX_URL": "http://vyrex-proxy:8000",
            },
            "restart_policy": {"Name": "unless-stopped"},
        }
        if "network" not in manifest.get("permissions", []):
            run_kwargs.pop("network", None)
            run_kwargs["network_mode"] = "none"
        container = self._client.containers.run(**run_kwargs)
        return ContainerInfo(container_id=container.id, status=getattr(container, "status", "running"), workspace_path=str(workspace_path))

    def stop_app(self, app_id: str) -> bool:
        try:
            container = self._client.containers.get(f"kryos-sdk-{app_id}")
            container.stop(timeout=10)
            return True
        except Exception:
            return False

    def get_status(self, app_id: str) -> AppStatus:
        try:
            container = self._client.containers.get(f"kryos-sdk-{app_id}")
        except Exception:
            return AppStatus(status="stopped", container_id=None, uptime_seconds=0, memory_used_mb=0.0, cpu_pct=0.0)
        attrs = getattr(container, "attrs", {}) or {}
        state = attrs.get("State", {})
        started_at = state.get("StartedAt")
        uptime_seconds = 0
        if started_at:
            from datetime import datetime

            try:
                started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                uptime_seconds = max(0, int((datetime.utcnow() - started.replace(tzinfo=None)).total_seconds()))
            except Exception:
                uptime_seconds = 0
        stats = container.stats(stream=False)
        memory_used_mb = float(stats.get("memory_stats", {}).get("usage", 0)) / 1024 / 1024
        cpu_stats = stats.get("cpu_stats", {}).get("cpu_usage", {})
        precpu_stats = stats.get("precpu_stats", {}).get("cpu_usage", {})
        cpu_total = float(cpu_stats.get("total_usage", 0))
        cpu_prev = float(precpu_stats.get("total_usage", 0))
        sys_cpu = float(stats.get("cpu_stats", {}).get("system_cpu_usage", 1))
        sys_prev = float(stats.get("precpu_stats", {}).get("system_cpu_usage", 0))
        cpu_pct = 0.0
        cpu_delta = cpu_total - cpu_prev
        sys_delta = sys_cpu - sys_prev
        if cpu_delta > 0 and sys_delta > 0:
            cpu_pct = (cpu_delta / sys_delta) * 100.0
        return AppStatus(status=getattr(container, "status", "running"), container_id=container.id, uptime_seconds=uptime_seconds, memory_used_mb=memory_used_mb, cpu_pct=cpu_pct)

    def remove_app(self, app_id: str) -> bool:
        stopped = self.stop_app(app_id)
        try:
            container = self._client.containers.get(f"kryos-sdk-{app_id}")
            container.remove(force=True)
            workspace = Path(self.workspace_base) / app_id
            if workspace.exists():
                try:
                    workspace.rmdir()
                except OSError:
                    pass
            return True
        except Exception:
            return stopped
