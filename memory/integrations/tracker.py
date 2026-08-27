# -*- coding: utf-8 -*-
"""Протокол трекера и фабрика Linear/Jira."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol

from memory.integrations.config import (
    issue_tracker_section,
    tracker_base_url,
    tracker_enabled,
    tracker_project_id,
    tracker_provider,
)
from memory.integrations.todo import TodoItem
from memory.logutil import get_logger

log = get_logger("memory.integrations")


@dataclass(frozen=True)
class RemoteIssue:
    remote_id: str
    key: str
    url: str
    title: str
    status: str


class IssueTracker(Protocol):
    provider: str

    def upsert(self, item: TodoItem) -> RemoteIssue: ...

    def close(self, item: TodoItem, remote: RemoteIssue) -> RemoteIssue: ...


def _env(environ: Optional[Mapping[str, str]], *names: str) -> Optional[str]:
    src = os.environ if environ is None else environ
    for name in names:
        raw = src.get(name)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def get_tracker(
    cfg: Dict[str, Any],
    *,
    environ: Optional[Mapping[str, str]] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Optional[IssueTracker]:
    """None, если выключено или нет секретов — вызывающий не ходит в сеть."""
    if not tracker_enabled(cfg):
        return None
    provider = tracker_provider(cfg)
    project_id = tracker_project_id(cfg)
    if not provider:
        return None
    if provider == "linear":
        from memory.integrations.linear import LinearTracker

        api_key = _env(environ, "LINEAR_API_KEY")
        if not api_key:
            log.warning("linear enabled but LINEAR_API_KEY is empty")
            return None
        team_override = _env(environ, "LINEAR_TEAM_ID")
        base = tracker_base_url(cfg) or "https://api.linear.app/graphql"
        return LinearTracker(
            api_key=api_key,
            project_id=project_id,
            base_url=base,
            team_id=team_override,
            state=state,
        )
    if provider == "jira":
        from memory.integrations.jira import JiraTracker

        section = issue_tracker_section(cfg)
        base = tracker_base_url(cfg) or _env(environ, "JIRA_BASE_URL")
        key = project_id or (_env(environ, "JIRA_PROJECT_KEY") or "")
        if not base or not key:
            log.warning("jira enabled but JIRA_BASE_URL/project_id missing")
            return None
        pat = _env(environ, "JIRA_PAT")
        email = _env(environ, "JIRA_EMAIL")
        token = _env(environ, "JIRA_API_TOKEN")
        if not pat and not (email and token):
            log.warning("jira enabled but no JIRA_PAT / JIRA_EMAIL+TOKEN")
            return None
        api_ver = section.get("api_version")
        return JiraTracker(
            base_url=base,
            project_key=key,
            pat=pat,
            email=email,
            api_token=token,
            api_version=str(api_ver) if api_ver else None,
            state=state,
        )
    return None
