"""Minimal Jira REST v3 client using httpx (Basic Auth: email + API token)."""
import base64
from typing import Any

import httpx


class JiraClient:
    def __init__(self, site_url: str, email: str, api_token: str) -> None:
        self.site_url = site_url.rstrip("/")
        auth = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.site_url}{path}"

    async def myself(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(self._url("/rest/api/3/myself"), headers=self._headers)
            r.raise_for_status()
            return r.json()

    async def project(self, project_key: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(self._url(f"/rest/api/3/project/{project_key}"), headers=self._headers)
            r.raise_for_status()
            return r.json()

    async def get_issue(self, key: str, fields: str = "summary,description,status,issuetype,priority") -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                self._url(f"/rest/api/3/issue/{key}"),
                headers=self._headers,
                params={"fields": fields},
            )
            r.raise_for_status()
            return r.json()

    async def search(self, jql: str, fields: str = "summary,status", max_results: int = 50) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                self._url("/rest/api/3/search"),
                headers=self._headers,
                params={"jql": jql, "fields": fields, "maxResults": max_results},
            )
            r.raise_for_status()
            return r.json()

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Story",
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        # Convert plain description to Atlassian Document Format (v3 API requires ADF).
        adf_description = {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": description}]}
            ],
        }
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "description": adf_description,
            "issuetype": {"name": issue_type},
        }
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = labels

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(self._url("/rest/api/3/issue"), headers=self._headers, json={"fields": fields})
            if r.status_code >= 400:
                raise RuntimeError(f"Jira create_issue failed [{r.status_code}]: {r.text}")
            return r.json()
