# -*- coding: utf-8 -*-
"""Оркестрация upsert/close по TODO.md. Супервизор зовёт с dry_run=False."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from memory.audit_log import append_entry
from memory.integrations.config import (
    load_project_cfg,
    tracker_enabled,
    tracker_project_id,
    tracker_provider,
)
from memory.integrations.state import get_item, load_state, put_item, save_state
from memory.integrations.todo import TodoItem, load_todo_items
from memory.integrations.tracker import RemoteIssue, get_tracker
from memory.logutil import get_logger

log = get_logger("memory.integrations")


def _agent_dir(workdir: Path) -> Path:
    return Path(workdir) / ".agent"


def _cli_dry_run(explicit: Optional[bool]) -> bool:
    if explicit is not None:
        return explicit
    if os.environ.get("AUTO_CONFIRM") == "1":
        return False
    return True


def _record(item: TodoItem, remote: RemoteIssue, status: str) -> Dict[str, Any]:
    return {
        "remote_id": remote.remote_id,
        "key": remote.key,
        "url": remote.url,
        "title": item.title,
        "status": status,
    }


def sync_open_issues(
    workdir: Path,
    *,
    dry_run: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Создать/обновить открытые пункты TODO в трекере."""
    workdir = Path(workdir)
    cfg = load_project_cfg(workdir)
    report: Dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "created": [],
        "updated": [],
        "unchanged": [],
        "errors": [],
    }
    if not tracker_enabled(cfg):
        report["skipped"] = True
        report["reason"] = "disabled"
        return report
    provider = tracker_provider(cfg) or ""
    project_id = tracker_project_id(cfg)
    agent = _agent_dir(workdir)
    state = load_state(agent, provider=provider, project_id=project_id)
    tracker = get_tracker(cfg, environ=environ, state=state)
    if tracker is None:
        report["ok"] = False
        report["skipped"] = True
        report["reason"] = "no_tracker"
        return report
    dry = _cli_dry_run(dry_run)
    report["dry_run"] = dry
    report["provider"] = provider
    items = [it for it in load_todo_items(workdir) if it.open]
    for item in items:
        mapped = get_item(state, item.item_id)
        action = "created" if not mapped else "updated"
        if (
            mapped
            and mapped.get("title") == item.title
            and mapped.get("status") == "open"
        ):
            report["unchanged"].append(item.item_id)
            continue
        if dry:
            report[action].append(item.item_id)
            continue
        try:
            remote = tracker.upsert(item)
        except Exception as exc:
            log.warning("tracker upsert failed %s: %s", item.item_id, exc)
            report["errors"].append(item.item_id)
            report["ok"] = False
            continue
        put_item(state, item.item_id, _record(item, remote, "open"))
        report[action].append(remote.key or item.item_id)
    if not dry:
        save_state(agent, state)
        try:
            append_entry(
                "issue_sync",
                "orchestrator",
                0,
                details={
                    "provider": provider,
                    "created": len(report["created"]),
                    "updated": len(report["updated"]),
                },
                agent_dir=agent,
            )
        except Exception as exc:
            log.warning("issue_sync audit failed: %s", exc)
    return report


def close_done_issues(
    workdir: Path,
    *,
    task_id: Optional[str] = None,
    dry_run: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
    handoff: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Закрыть задачи, отмеченные DONE в TODO, либо task_id из handoff."""
    workdir = Path(workdir)
    cfg = load_project_cfg(workdir)
    report: Dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "closed": [],
        "errors": [],
    }
    if not tracker_enabled(cfg):
        report["skipped"] = True
        report["reason"] = "disabled"
        return report
    provider = tracker_provider(cfg) or ""
    project_id = tracker_project_id(cfg)
    agent = _agent_dir(workdir)
    state = load_state(agent, provider=provider, project_id=project_id)
    tracker = get_tracker(cfg, environ=environ, state=state)
    if tracker is None:
        report["ok"] = False
        report["skipped"] = True
        report["reason"] = "no_tracker"
        return report
    dry = _cli_dry_run(dry_run)
    report["dry_run"] = dry
    todos = load_todo_items(workdir)
    by_id = {t.item_id: t for t in todos}
    targets: List[str] = []
    if task_id:
        targets.append(task_id)
    else:
        if isinstance(handoff, dict):
            hid = handoff.get("task_id") or handoff.get("current_task")
            if isinstance(hid, str) and hid.strip():
                targets.append(hid.strip())
        for item in todos:
            if not item.open:
                mapped = get_item(state, item.item_id)
                if mapped and mapped.get("status") != "done":
                    targets.append(item.item_id)
        # если TODO не обновлён, закрываем все ещё open маппинги текущего прогона —
        # только когда явный task_id не задан и нет checked пунктов: не трогаем.
    # уникальные, только те, что есть в state
    seen = set()
    ordered: List[str] = []
    for tid in targets:
        if tid in seen:
            continue
        seen.add(tid)
        if get_item(state, tid):
            ordered.append(tid)
    for tid in ordered:
        mapped = get_item(state, tid) or {}
        item = by_id.get(tid) or TodoItem(
            item_id=tid,
            title=str(mapped.get("title") or tid),
            open=False,
            raw=tid,
            source_line=0,
        )
        remote = RemoteIssue(
            remote_id=str(mapped.get("remote_id") or mapped.get("key") or ""),
            key=str(mapped.get("key") or mapped.get("remote_id") or ""),
            url=str(mapped.get("url") or ""),
            title=item.title,
            status=str(mapped.get("status") or "open"),
        )
        if dry:
            report["closed"].append(remote.key or tid)
            continue
        try:
            closed = tracker.close(item, remote)
        except Exception as exc:
            log.warning("tracker close failed %s: %s", tid, exc)
            report["errors"].append(tid)
            report["ok"] = False
            continue
        put_item(state, tid, _record(item, closed, "done"))
        report["closed"].append(closed.key or tid)
    if not dry:
        save_state(agent, state)
        try:
            append_entry(
                "issue_close",
                "reviewer",
                0,
                details={"provider": provider, "closed": len(report["closed"])},
                agent_dir=agent,
            )
        except Exception as exc:
            log.warning("issue_close audit failed: %s", exc)
    return report
