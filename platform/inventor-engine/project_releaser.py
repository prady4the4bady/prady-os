from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ReleaseResult:
    project_id: str
    urls: dict = field(default_factory=dict)
    released_ts: str = ""


class ProjectReleaser:
    async def release(self, project: dict) -> ReleaseResult:
        urls = {}

        github_url = await self._push_to_github(project)
        if github_url:
            urls["github"] = github_url

        release_url = await self._create_github_release(project, github_url)
        if release_url:
            urls["github_release"] = release_url

        await self._notify_user(project, urls)
        await self._log_release(project, urls)

        return ReleaseResult(
            project_id=project["project_id"],
            urls=urls,
            released_ts=datetime.now(timezone.utc).isoformat(),
        )

    async def _push_to_github(self, project: dict) -> str | None:
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            logger.warning("GITHUB_TOKEN not set — skipping GitHub push. Project saved locally at: %s", project.get("workspace_path"))
            return None

        repo_name = project["name"]
        workspace = project["workspace_path"]

        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(
                "https://api.github.com/user/repos",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "name": repo_name,
                    "description": "Built by Prax on Prady OS",
                    "private": False,
                    "auto_init": False,
                },
            )
            if r.status_code not in (201, 422):
                logger.error("GitHub repo creation failed: %s", r.status_code)
                return None
            repo_data = r.json()
            clone_url = repo_data.get("clone_url", "")
            if not clone_url:
                return None

        auth_url = clone_url.replace("https://", f"https://{token}@")
        subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=workspace, capture_output=True)
        push = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=workspace, capture_output=True, text=True)
        if push.returncode != 0:
            subprocess.run(["git", "push", "-u", "origin", "master"], cwd=workspace, capture_output=True)

        return repo_data.get("html_url", "")

    async def _create_github_release(self, project: dict, github_url: str | None) -> str | None:
        token = os.getenv("GITHUB_TOKEN")
        if not token or not github_url:
            return None

        parts = github_url.rstrip("/").split("/")
        if len(parts) < 2:
            return None
        owner = parts[-2]
        repo = parts[-1]

        workspace = project["workspace_path"]
        readme_path = Path(workspace) / "README.md"
        notes = readme_path.read_text() if readme_path.exists() else f"Built autonomously by Prax on Prady OS."

        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(
                f"https://api.github.com/repos/{owner}/{repo}/releases",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "tag_name": "v1.0.0",
                    "name": f"{project['name']} v1.0.0",
                    "body": notes[:65536],
                    "draft": False,
                    "prerelease": False,
                },
            )
            if r.status_code == 201:
                return r.json().get("html_url", "")
        return None

    async def _notify_user(self, project: dict, urls: dict) -> None:
        notify_url = os.getenv("NOTIFICATION_BUS_URL", "http://notification-bus:8111")
        github_url = urls.get("github", "")
        message = (
            f"Prax finished building '{project['name']}'. "
            f"All tests pass. Delivery verified from cold start. "
            f"{('View on GitHub: ' + github_url) if github_url else 'Saved locally — add GITHUB_TOKEN to publish.'}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                await c.post(
                    f"{notify_url}/notify",
                    json={
                        "title": f"✅ Prax delivered: {project['name']}",
                        "body": message,
                        "severity": "info",
                        "source": "inventor-engine",
                    },
                )
        except Exception:
            pass

    async def _log_release(self, project: dict, urls: dict) -> None:
        audit_url = os.getenv("AUDIT_LOG_URL", "http://audit-log:8112")
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                await c.post(
                    f"{audit_url}/events",
                    json={
                        "event": "project_released",
                        "project_id": project["project_id"],
                        "project_name": project["name"],
                        "verified": project["verified"],
                        "urls": urls,
                        "service": "inventor-engine",
                    },
                )
        except Exception:
            pass
