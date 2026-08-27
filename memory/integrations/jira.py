# -*- coding: utf-8 -*-
"""Jira REST: синхронизация INVEST-задач цикла (не git-commit-to-jira-tasks)."""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from memory.integrations.http import HttpError, request_json
from memory.integrations.tracker import RemoteIssue
from memory.integrations.todo import TodoItem
from memory.logutil import get_logger

log = get_logger("memory.integrations")

_DONE_NAMES = frozenset(
    {"done", "closed", "resolved", "complete", "completed", "finish", "finished"}
)


def _adf(text: str) -> Dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text or " "}],
            }
        ],
    }


class JiraTracker:
    provider = "jira"

    def __init__(
        self,
        *,
        base_url: str,
        project_key: str,
        pat: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        api_version: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.pat = pat
        self.email = email
        self.api_token = api_token
        self._state = state if state is not None else {}
        host = (urlparse(self.base_url).hostname or "").lower()
        if api_version in {"2", "3"}:
            self.api = api_version
        else:
            self.api = "3" if host.endswith("atlassian.net") else "2"

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.pat:
            headers["Authorization"] = f"Bearer {self.pat}"
        elif self.email and self.api_token:
            blob = base64.b64encode(f"{self.email}:{self.api_token}".encode("utf-8"))
            headers["Authorization"] = "Basic " + blob.decode("ascii")
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/rest/api/{self.api}{path}"

    def _request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        return request_json(
            method, self._url(path), headers=self._headers(), body=body
        )

    def _description(self, item: TodoItem) -> Any:
        text = (
            f"Source: .agent/TODO.md line {item.source_line} ({item.item_id})\n"
            f"{item.raw}"
        )
        if self.api == "3":
            return _adf(text)
        return text

    def _issue_from(self, blob: Dict[str, Any], status: str, title: str) -> RemoteIssue:
        key = str(blob.get("key") or "")
        remote_id = str(blob.get("id") or key)
        self_url = str(blob.get("self") or "")
        browse = ""
        if key:
            browse = self.base_url.rstrip("/") + "/browse/" + key
        return RemoteIssue(
            remote_id=remote_id or key,
            key=key or remote_id,
            url=browse or self_url,
            title=title,
            status=status,
        )

    def upsert(self, item: TodoItem) -> RemoteIssue:
        mapped = (self._state.get("items") or {}).get(item.item_id)
        if isinstance(mapped, dict) and mapped.get("key"):
            key = str(mapped["key"])
            if mapped.get("title") == item.title and mapped.get("status") == "open":
                return RemoteIssue(
                    remote_id=str(mapped.get("remote_id") or key),
                    key=key,
                    url=str(mapped.get("url") or ""),
                    title=item.title,
                    status="open",
                )
            fields: Dict[str, Any] = {
                "summary": item.title[:255],
                "description": self._description(item),
            }
            status, payload = self._request("PUT", f"/issue/{key}", {"fields": fields})
            if status >= 400:
                raise HttpError("jira_update", status=status)
            return RemoteIssue(
                remote_id=str(mapped.get("remote_id") or key),
                key=key,
                url=str(mapped.get("url") or ""),
                title=item.title,
                status="open",
            )
        body = {
            "fields": {
                "project": {"key": self.project_key},
                "issuetype": {"name": "Task"},
                "summary": item.title[:255],
                "description": self._description(item),
            }
        }
        status, payload = self._request("POST", "/issue", body)
        if status == 400:
            body["fields"]["issuetype"] = {"name": "Story"}
            status, payload = self._request("POST", "/issue", body)
        if status >= 400 or not isinstance(payload, dict):
            raise HttpError("jira_create", status=status)
        created = self._issue_from(payload, "open", item.title)
        if not created.key:
            raise HttpError("jira_create_empty", status=status)
        return created

    def _pick_transition(self, transitions: List[Any]) -> Optional[str]:
        fallback = None
        for tr in transitions:
            if not isinstance(tr, dict):
                continue
            tid = str(tr.get("id") or "")
            name = str(tr.get("name") or "").lower()
            to = tr.get("to") if isinstance(tr.get("to"), dict) else {}
            cat = to.get("statusCategory") if isinstance(to, dict) else {}
            cat_key = ""
            if isinstance(cat, dict):
                cat_key = str(cat.get("key") or "").lower()
            if not tid:
                continue
            if name in _DONE_NAMES:
                return tid
            if cat_key == "done" and fallback is None:
                fallback = tid
        return fallback

    def close(self, item: TodoItem, remote: RemoteIssue) -> RemoteIssue:
        key = remote.key
        status, payload = self._request("GET", f"/issue/{key}/transitions")
        if status >= 400 or not isinstance(payload, dict):
            raise HttpError("jira_transitions", status=status)
        trans = payload.get("transitions") or []
        if not isinstance(trans, list):
            trans = []
        tid = self._pick_transition(trans)
        if not tid:
            log.warning("jira has no Done transition for %s", key)
            return RemoteIssue(
                remote_id=remote.remote_id,
                key=key,
                url=remote.url,
                title=item.title,
                status="open",
            )
        st, _ = self._request("POST", f"/issue/{key}/transitions", {"transition": {"id": tid}})
        if st >= 400:
            raise HttpError("jira_transition", status=st)
        return RemoteIssue(
            remote_id=remote.remote_id,
            key=key,
            url=remote.url,
            title=item.title,
            status="done",
        )
