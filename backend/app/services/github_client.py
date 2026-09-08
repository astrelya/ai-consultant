"""Minimal GitHub REST client using httpx (PAT auth)."""
from typing import Any
import httpx


class GitHubClient:
    def __init__(self, pat: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"https://api.github.com/repos/{owner}/{repo}", headers=self._headers)
            r.raise_for_status()
            return r.json()

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                headers=self._headers,
                json={"title": title, "head": head, "base": base, "body": body},
            )
            if r.status_code >= 400:
                raise RuntimeError(f"GitHub create_pull_request failed [{r.status_code}]: {r.text}")
            return r.json()
