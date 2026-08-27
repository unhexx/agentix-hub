# -*- coding: utf-8 -*-
"""Linear GraphQL: создание/обновление задач по INVEST из TODO.md."""
from __future__ import annotations

from typing import Any, Dict, Optional

from memory.integrations.http import HttpError, request_json
from memory.integrations.tracker import RemoteIssue
from memory.integrations.todo import TodoItem
from memory.logutil import get_logger

log = get_logger("memory.integrations")

_TEAM_QUERY = """
query TeamByKey($key: String!) {
  teams(filter: { key: { eq: $key } }) {
    nodes { id key name }
  }
}
""".strip()

_STATES_QUERY = """
query TeamStates($id: String!) {
  team(id: $id) {
    states { nodes { id name type } }
  }
}
""".strip()

_CREATE = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url title }
  }
}
""".strip()

_UPDATE = """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier url title }
  }
}
""".strip()


class LinearTracker:
    provider = "linear"

    def __init__(
        self,
        *,
        api_key: str,
        project_id: str,
        base_url: str,
        team_id: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.api_key = api_key
        self.project_id = project_id
        self.base_url = base_url.rstrip("/")
        self._cached_team_id = team_id
        self._state = state if state is not None else {}

    def _headers(self) -> Dict[str, str]:
        key = self.api_key
        # Linear принимает ключ как есть; Bearer оставляем, если его уже проставили.
        auth = key if key.lower().startswith("bearer ") else key
        return {"Authorization": auth, "Content-Type": "application/json"}

    def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        status, payload = request_json(
            "POST",
            self.base_url,
            headers=self._headers(),
            body={"query": query, "variables": variables},
        )
        if status >= 400 or not isinstance(payload, dict):
            raise HttpError("linear_http", status=status)
        errors = payload.get("errors")
        if errors:
            raise HttpError("linear_graphql", status=status)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise HttpError("linear_empty", status=status)
        return data

    def team_id(self) -> str:
        if self._cached_team_id:
            return self._cached_team_id
        cached = self._state.get("team_id")
        if isinstance(cached, str) and cached:
            self._cached_team_id = cached
            return cached
        data = self._graphql(_TEAM_QUERY, {"key": self.project_id})
        nodes = (((data.get("teams") or {}).get("nodes")) or [])
        if not nodes:
            raise HttpError("linear_team_missing")
        tid = str(nodes[0].get("id") or "")
        if not tid:
            raise HttpError("linear_team_missing")
        self._cached_team_id = tid
        self._state["team_id"] = tid
        return tid

    def _done_state_id(self) -> Optional[str]:
        cached = self._state.get("done_state_id")
        if isinstance(cached, str) and cached:
            return cached
        data = self._graphql(_STATES_QUERY, {"id": self.team_id()})
        nodes = (((data.get("team") or {}).get("states") or {}).get("nodes")) or []
        preferred = None
        for node in nodes:
            if not isinstance(node, dict):
                continue
            ntype = str(node.get("type") or "").lower()
            name = str(node.get("name") or "").lower()
            nid = str(node.get("id") or "")
            if not nid:
                continue
            if ntype == "completed" and name in {"done", "completed", "closed"}:
                preferred = nid
                break
            if ntype == "completed" and preferred is None:
                preferred = nid
        if preferred:
            self._state["done_state_id"] = preferred
        return preferred

    def _issue_from(self, blob: Dict[str, Any], status: str) -> RemoteIssue:
        return RemoteIssue(
            remote_id=str(blob.get("id") or ""),
            key=str(blob.get("identifier") or blob.get("id") or ""),
            url=str(blob.get("url") or ""),
            title=str(blob.get("title") or ""),
            status=status,
        )

    def _description(self, item: TodoItem) -> str:
        return (
            f"Source: `.agent/TODO.md` line {item.source_line} (`{item.item_id}`)\n\n"
            f"{item.raw}"
        )

    def upsert(self, item: TodoItem) -> RemoteIssue:
        mapped = (self._state.get("items") or {}).get(item.item_id)
        if isinstance(mapped, dict) and mapped.get("remote_id"):
            remote_id = str(mapped["remote_id"])
            if mapped.get("title") == item.title and mapped.get("status") == "open":
                return RemoteIssue(
                    remote_id=remote_id,
                    key=str(mapped.get("key") or remote_id),
                    url=str(mapped.get("url") or ""),
                    title=item.title,
                    status="open",
                )
            data = self._graphql(
                _UPDATE,
                {
                    "id": remote_id,
                    "input": {
                        "title": item.title,
                        "description": self._description(item),
                    },
                },
            )
            issue = ((data.get("issueUpdate") or {}).get("issue")) or {}
            return self._issue_from(issue, "open")
        data = self._graphql(
            _CREATE,
            {
                "input": {
                    "teamId": self.team_id(),
                    "title": item.title,
                    "description": self._description(item),
                }
            },
        )
        issue = ((data.get("issueCreate") or {}).get("issue")) or {}
        created = self._issue_from(issue, "open")
        if not created.remote_id:
            raise HttpError("linear_create_empty")
        return created

    def close(self, item: TodoItem, remote: RemoteIssue) -> RemoteIssue:
        state_id = self._done_state_id()
        payload: Dict[str, Any] = {"title": item.title}
        if state_id:
            payload["stateId"] = state_id
        else:
            log.warning("linear completed state not found; updating title only")
        data = self._graphql(
            _UPDATE, {"id": remote.remote_id, "input": payload}
        )
        issue = ((data.get("issueUpdate") or {}).get("issue")) or {}
        out = self._issue_from(issue, "done")
        if not out.remote_id:
            return RemoteIssue(
                remote_id=remote.remote_id,
                key=remote.key,
                url=remote.url,
                title=item.title,
                status="done",
            )
        return out
