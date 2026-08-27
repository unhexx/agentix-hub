# -*- coding: utf-8 -*-
"""Разбор открытых INVEST-пунктов из .agent/TODO.md."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_CHECKBOX_RE = re.compile(
    r"""^(\s*[-*]\s+)\[([ xX])\]\s+
        (?:((?:[A-Za-z][A-Za-z0-9]*)-\d+)\s*[:.\-–]?\s*)?
        (.+?)\s*$""",
    re.VERBOSE,
)
# VERBOSE нельзя: «#» в шаблоне стал бы комментарием.
_HEADING_RE = re.compile(
    r"^(#{1,4})\s+((?:[A-Za-z][A-Za-z0-9]*)-\d+)\s*[:.\-–]?\s*(.+?)\s*$"
)
_STATUS_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:\*\*)?Status(?:\*\*)?\s*:\s*([A-Za-z_]+)",
    re.IGNORECASE,
)
_SKIP_TITLES = frozenset(
    {
        "todo",
        "open",
        "done",
        "closed",
        "backlog",
        "in progress",
        "in_progress",
        "blocked",
        "tasks",
        "invest",
    }
)
_OPEN_STATUS = frozenset({"todo", "open", "in_progress", "in-progress", "blocked", "wip"})
_DONE_STATUS = frozenset({"done", "closed", "complete", "completed", "resolved"})


@dataclass(frozen=True)
class TodoItem:
    item_id: str
    title: str
    open: bool
    raw: str
    source_line: int


def _slug(title: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not cleaned:
        cleaned = "item"
    return "todo-" + cleaned[:40]


def parse_todo_md(text: str) -> List[TodoItem]:
    """Чекбоксы и заголовки с идентификатором P1-01 / AGX-12."""
    lines = text.splitlines()
    items: List[TodoItem] = []
    seen: set[str] = set()
    pending_heading: Optional[tuple[str, str, int, str]] = None

    def _push(item_id: str, title: str, is_open: bool, raw: str, line_no: int) -> None:
        item_id = item_id.strip()
        title = title.strip()
        if not item_id or not title:
            return
        if title.lower() in _SKIP_TITLES:
            return
        if item_id in seen:
            return
        seen.add(item_id)
        items.append(
            TodoItem(
                item_id=item_id,
                title=title,
                open=is_open,
                raw=raw.strip(),
                source_line=line_no,
            )
        )

    def _flush_heading(status: Optional[str]) -> None:
        nonlocal pending_heading
        if pending_heading is None:
            return
        item_id, title, line_no, raw = pending_heading
        pending_heading = None
        st = (status or "todo").strip().lower().replace(" ", "_")
        if st in _DONE_STATUS:
            is_open = False
        else:
            is_open = st in _OPEN_STATUS or status is None
        _push(item_id, title, is_open, raw, line_no)

    for idx, line in enumerate(lines, start=1):
        status_m = _STATUS_RE.match(line)
        if status_m and pending_heading is not None:
            _flush_heading(status_m.group(1))
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            _flush_heading(None)
            title = heading.group(3).strip()
            if title.lower() in _SKIP_TITLES:
                pending_heading = None
                continue
            pending_heading = (heading.group(2), title, idx, line)
            continue
        box = _CHECKBOX_RE.match(line)
        if box:
            _flush_heading(None)
            checked = box.group(2).lower() == "x"
            item_id = (box.group(3) or "").strip() or _slug(box.group(4))
            _push(item_id, box.group(4), not checked, line, idx)
            continue
        if pending_heading is not None and line.strip() == "":
            continue
        if pending_heading is not None and line.startswith("#"):
            _flush_heading(None)

    _flush_heading(None)
    return items


def load_todo_items(workdir: Path) -> List[TodoItem]:
    path = Path(workdir) / ".agent" / "TODO.md"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    return parse_todo_md(text)
