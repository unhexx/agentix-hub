# -*- coding: utf-8 -*-
"""CLI: python -m memory.integrations {sync,close,notify,status}."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from memory.integrations.config import (
    load_project_cfg,
    slack_enabled,
    tracker_enabled,
    tracker_project_id,
    tracker_provider,
)
from memory.integrations.service import close_done_issues, sync_open_issues
from memory.integrations.slack import notify_slack
from memory.integrations.state import load_state, state_path


def _workdir(raw: Optional[Path]) -> Path:
    return Path(raw or Path.cwd()).resolve()


def _dry(args: argparse.Namespace) -> bool:
    if getattr(args, "dry_run", False):
        return True
    if getattr(args, "apply", False) or os.environ.get("AUTO_CONFIRM") == "1":
        return False
    return True


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="memory.integrations",
        description="Opt-in Linear/Jira sync and Slack notify",
    )
    p.add_argument("--workdir", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sync", help="Upsert open TODO.md items")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--apply", action="store_true")

    cp = sub.add_parser("close", help="Close done TODO items / --task-id")
    cp.add_argument("--dry-run", action="store_true")
    cp.add_argument("--apply", action="store_true")
    cp.add_argument("--task-id", default=None)

    np = sub.add_parser("notify", help="Post Slack summary")
    np.add_argument("--status", required=True, choices=["DONE", "BLOCKED"])
    np.add_argument("--force", action="store_true")
    np.add_argument("--dry-run", action="store_true")
    np.add_argument("--apply", action="store_true")

    sub.add_parser("status", help="Print gates and mapping (no secrets)")

    args = p.parse_args(argv)
    workdir = _workdir(args.workdir)
    if args.cmd == "sync":
        report = sync_open_issues(workdir, dry_run=_dry(args))
    elif args.cmd == "close":
        report = close_done_issues(
            workdir, task_id=args.task_id, dry_run=_dry(args)
        )
    elif args.cmd == "notify":
        report = notify_slack(
            workdir,
            status=args.status,
            force=bool(args.force),
            dry_run=_dry(args),
        )
    else:
        cfg = load_project_cfg(workdir)
        provider = tracker_provider(cfg) or ""
        project_id = tracker_project_id(cfg)
        st = {}
        if provider:
            st = load_state(
                workdir / ".agent", provider=provider, project_id=project_id
            )
        report = {
            "tracker_enabled": tracker_enabled(cfg),
            "slack_enabled": slack_enabled(cfg),
            "provider": provider or None,
            "project_id": project_id or None,
            "state_file": str(state_path(workdir / ".agent")),
            "mapped": len((st.get("items") or {})),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("ok") is False and not report.get("skipped"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
