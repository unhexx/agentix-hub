# -*- coding: utf-8 -*-
"""Точки входа супервизора. Любая ошибка — warning, цикл не валим."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from memory.logutil import get_logger

log = get_logger("memory.integrations")


def on_cycle_start(workdir: Path) -> None:
    """Оркестратор: upsert открытых INVEST, если трекер включён."""
    from memory.integrations.service import sync_open_issues

    try:
        sync_open_issues(Path(workdir), dry_run=False)
    except Exception as exc:
        log.warning("on_cycle_start failed: %s", exc)


def on_reviewer_done(workdir: Path, handoff: Optional[Dict[str, Any]] = None) -> None:
    """Reviewer DONE: закрыть задачи и пнуть Slack."""
    from memory.integrations.service import close_done_issues
    from memory.integrations.slack import notify_slack

    try:
        close_done_issues(Path(workdir), dry_run=False, handoff=handoff)
    except Exception as exc:
        log.warning("on_reviewer_done close failed: %s", exc)
    try:
        notify_slack(Path(workdir), status="DONE", handoff=handoff, dry_run=False)
    except Exception as exc:
        log.warning("on_reviewer_done slack failed: %s", exc)


def on_reviewer_blocked(
    workdir: Path, handoff: Optional[Dict[str, Any]] = None
) -> None:
    """BLOCKED: только Slack, трекер не трогаем."""
    from memory.integrations.slack import notify_slack

    try:
        notify_slack(Path(workdir), status="BLOCKED", handoff=handoff, dry_run=False)
    except Exception as exc:
        log.warning("on_reviewer_blocked slack failed: %s", exc)
