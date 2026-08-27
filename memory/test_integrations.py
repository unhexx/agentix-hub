# -*- coding: utf-8 -*-
"""Герметичные тесты MCP-интеграций: urllib мокаем, в сеть не ходим."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request

import pytest

from memory.integrations.config import slack_enabled, tracker_enabled
from memory.integrations.service import close_done_issues, sync_open_issues
from memory.integrations.slack import build_message, notify_slack
from memory.integrations.todo import parse_todo_md


TODO_FIXTURE = """# TODO

## Open

- [ ] P1-01 Auth refresh
- [ ] P1-02 Compact Slack summary
- [x] P0-01 Seed repo
- [ ] Wire the gateway fallback

## AGX-9 Heading task
Status: TODO

## Done
- [x] P0-02 Docs
"""


def test_parse_todo_checkboxes_and_headings():
    items = parse_todo_md(TODO_FIXTURE)
    by_id = {i.item_id: i for i in items}
    assert by_id["P1-01"].open and by_id["P1-01"].title == "Auth refresh"
    assert by_id["P1-02"].open
    assert by_id["P0-01"].open is False
    assert by_id["AGX-9"].open and "Heading" in by_id["AGX-9"].title
    slug = [i for i in items if i.item_id.startswith("todo-")]
    assert slug and slug[0].open
    assert "P0-02" in by_id and by_id["P0-02"].open is False


def test_tracker_and_slack_gates_default_off():
    assert tracker_enabled({}) is False
    assert tracker_enabled({"integrations": {}}) is False
    assert (
        tracker_enabled(
            {"integrations": {"issue_tracker": {"provider": "linear", "enabled": False}}}
        )
        is False
    )
    assert (
        tracker_enabled(
            {"integrations": {"issue_tracker": {"provider": "linear", "enabled": True}}}
        )
        is True
    )
    assert (
        tracker_enabled(
            {"integrations": {"issue_tracker": {"provider": "asana", "enabled": True}}}
        )
        is False
    )
    slack_on = {
        "integrations": {"slack": {"enabled": True}},
        "tier": {"feature_flags": {"enterprise_governance": True}},
    }
    assert slack_enabled(slack_on) is True
    slack_no_gov = {
        "integrations": {"slack": {"enabled": True}},
        "tier": {"feature_flags": {"enterprise_governance": False}},
    }
    assert slack_enabled(slack_no_gov) is False
    assert slack_enabled(slack_no_gov, force=True) is True
    slack_force_cfg = {
        "integrations": {"slack": {"enabled": True, "force": True}},
        "tier": {"feature_flags": {"enterprise_governance": False}},
    }
    assert slack_enabled(slack_force_cfg) is True
    assert slack_enabled({"integrations": {"slack": {"enabled": True}}}) is False


class FakeResp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        raw = (
            payload
            if isinstance(payload, (bytes, bytearray))
            else json.dumps(payload).encode("utf-8")
        )
        self._buf = io.BytesIO(raw)
        self.status = status

    def read(self) -> bytes:
        return self._buf.read()

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeResp":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class FakeHttp:
    def __init__(self) -> None:
        self.calls: List[Request] = []
        self.linear_created = 0
        self.jira_created = 0

    def __call__(self, req: Request, timeout: Optional[float] = None) -> FakeResp:
        self.calls.append(req)
        url = req.full_url
        method = (req.get_method() or "GET").upper()
        body: Dict[str, Any] = {}
        if req.data:
            try:
                body = json.loads(req.data.decode("utf-8"))
            except Exception:
                body = {}
        if "graphql" in url or "api.linear.app" in url:
            return FakeResp(self._linear(body))
        if "/rest/api/" in url:
            return FakeResp(self._jira(method, url, body), status=self._jira_status(method, url))
        if "hooks.slack.com" in url or "slack.com/api" in url:
            if "chat.postMessage" in url:
                return FakeResp({"ok": True})
            return FakeResp({"ok": True})
        raise AssertionError(f"unexpected url {url}")

    def _linear(self, body: Dict[str, Any]) -> Dict[str, Any]:
        query = str(body.get("query") or "")
        if "teams(" in query:
            return {"data": {"teams": {"nodes": [{"id": "team-1", "key": "AGX", "name": "Agx"}]}}}
        if "states" in query:
            return {
                "data": {
                    "team": {
                        "states": {
                            "nodes": [
                                {"id": "st-open", "name": "Todo", "type": "unstarted"},
                                {"id": "st-done", "name": "Done", "type": "completed"},
                            ]
                        }
                    }
                }
            }
        if "issueCreate" in query:
            self.linear_created += 1
            ident = f"AGX-{self.linear_created}"
            return {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": f"id-{self.linear_created}",
                            "identifier": ident,
                            "url": f"https://linear.app/agx/issue/{ident}",
                            "title": (body.get("variables") or {})
                            .get("input", {})
                            .get("title", ident),
                        },
                    }
                }
            }
        if "issueUpdate" in query:
            ident = "AGX-1"
            return {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": {
                            "id": (body.get("variables") or {}).get("id") or "id-1",
                            "identifier": ident,
                            "url": f"https://linear.app/agx/issue/{ident}",
                            "title": "updated",
                        },
                    }
                }
            }
        return {"errors": [{"message": "unexpected linear query"}]}

    def _jira_status(self, method: str, url: str) -> int:
        if method == "POST" and url.endswith("/issue"):
            return 201
        if method == "POST" and url.endswith("/transitions"):
            return 204
        return 200

    def _jira(self, method: str, url: str, body: Dict[str, Any]) -> Any:
        if method == "POST" and url.endswith("/issue"):
            self.jira_created += 1
            key = f"AGX-{self.jira_created}"
            return {"id": str(10000 + self.jira_created), "key": key, "self": url + "/" + key}
        if method == "PUT":
            return {}
        if url.endswith("/transitions") and method == "GET":
            return {
                "transitions": [
                    {
                        "id": "31",
                        "name": "Done",
                        "to": {"name": "Done", "statusCategory": {"key": "done"}},
                    }
                ]
            }
        if method == "POST" and url.endswith("/transitions"):
            return {}
        return {}


def _write_cfg(workdir: Path, payload: Dict[str, Any]) -> None:
    agent = workdir / ".agent"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "project_config.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _write_todo(workdir: Path, text: str = TODO_FIXTURE) -> None:
    agent = workdir / ".agent"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "TODO.md").write_text(text, encoding="utf-8")


def test_sync_disabled_does_not_http(tmp_path: Path, monkeypatch):
    _write_cfg(tmp_path, {})
    _write_todo(tmp_path)
    fake = FakeHttp()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    report = sync_open_issues(tmp_path, dry_run=False)
    assert report["skipped"] is True
    assert fake.calls == []


def test_linear_upsert_and_close(tmp_path: Path, monkeypatch):
    _write_cfg(
        tmp_path,
        {
            "integrations": {
                "issue_tracker": {
                    "provider": "linear",
                    "project_id": "AGX",
                    "enabled": True,
                    "base_url": "https://api.linear.app/graphql",
                }
            }
        },
    )
    _write_todo(
        tmp_path,
        "- [ ] P1-01 Auth refresh\n- [ ] P1-02 Slack summary\n",
    )
    fake = FakeHttp()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key_value")
    report = sync_open_issues(tmp_path, dry_run=False)
    assert report["skipped"] is False
    assert report["ok"] is True
    assert len(report["created"]) == 2
    assert fake.linear_created == 2
    state = json.loads(
        (tmp_path / ".agent" / "integrations-issues-state.json").read_text(encoding="utf-8")
    )
    assert "P1-01" in state["items"]
    # второй прогон — без новых create
    report2 = sync_open_issues(tmp_path, dry_run=False)
    assert report2["unchanged"]
    assert fake.linear_created == 2

    (tmp_path / ".agent" / "TODO.md").write_text(
        "- [x] P1-01 Auth refresh\n- [ ] P1-02 Slack summary\n", encoding="utf-8"
    )
    closed = close_done_issues(tmp_path, dry_run=False)
    assert "AGX-1" in closed["closed"] or "P1-01" in str(closed)
    assert closed["ok"] is True
    # ключ не должен утечь в сериализованный отчёт как тело запроса — проверяем логи не здесь
    dumped = json.dumps(report)
    assert "lin_api_test_key_value" not in dumped


def test_jira_upsert_and_close(tmp_path: Path, monkeypatch):
    _write_cfg(
        tmp_path,
        {
            "integrations": {
                "issue_tracker": {
                    "provider": "jira",
                    "project_id": "AGX",
                    "enabled": True,
                    "base_url": "https://example.atlassian.net",
                }
            }
        },
    )
    _write_todo(tmp_path, "- [ ] P1-01 Auth refresh\n")
    fake = FakeHttp()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setenv("JIRA_EMAIL", "dev@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "jira-token-value")
    report = sync_open_issues(tmp_path, dry_run=False)
    assert report["ok"] is True
    assert fake.jira_created == 1
    urls = [c.full_url for c in fake.calls]
    assert any("/rest/api/3/issue" in u for u in urls)
    (tmp_path / ".agent" / "TODO.md").write_text(
        "- [x] P1-01 Auth refresh\n", encoding="utf-8"
    )
    closed = close_done_issues(tmp_path, dry_run=False)
    assert closed["ok"] is True
    assert closed["closed"]
    trans = [
        c
        for c in fake.calls
        if (c.get_method() or "").upper() == "POST" and str(c.full_url).endswith("/transitions")
    ]
    assert trans


def test_slack_webhook_and_governance_gate(tmp_path: Path, monkeypatch):
    fake = FakeHttp()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    _write_cfg(
        tmp_path,
        {
            "integrations": {"slack": {"enabled": True, "channel": "#agentix"}},
            "tier": {"feature_flags": {"enterprise_governance": False}},
        },
    )
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/XXX")
    skipped = notify_slack(
        tmp_path,
        status="DONE",
        dry_run=False,
        sha="abc123deadbeef",
        remote="https://github.com/unhexx/agentix-hub.git",
    )
    assert skipped["skipped"] is True
    assert fake.calls == []

    _write_cfg(
        tmp_path,
        {
            "integrations": {"slack": {"enabled": True, "channel": "#agentix"}},
            "tier": {"feature_flags": {"enterprise_governance": True}},
        },
    )
    from memory.performance_ledger import append_cycle

    append_cycle(
        agent_dir=tmp_path / ".agent",
        cycle=12,
        elapsed_minutes=1.6,
        confidence=0.94,
        tests_failed=0,
        outcome="DONE",
    )
    posted = notify_slack(
        tmp_path,
        status="DONE",
        handoff={"cycle_number": 12, "task_id": "P1-01"},
        dry_run=False,
        sha="abc123deadbeef",
        remote="git@github.com:unhexx/agentix-hub.git",
    )
    assert posted["ok"] is True
    assert posted["skipped"] is False
    assert fake.calls
    body = json.loads(fake.calls[-1].data.decode("utf-8"))
    text = body["text"]
    assert "DONE" in text
    assert "P1-01" in text
    assert "github.com/unhexx/agentix-hub/commit/" in text
    assert "elapsed=1.6m" in text
    assert "confidence=0.94" in text
    audit = json.loads(
        (tmp_path / ".agent" / "AUDIT_LOG.json").read_text(encoding="utf-8")
    )
    details = audit["entries"][-1]["details"]
    assert "hooks.slack.com" not in json.dumps(details)
    assert details.get("channel") == "#agentix"


def test_build_message_compact():
    text = build_message(
        status="BLOCKED",
        cycle=3,
        task_id="P1-02",
        commit="https://github.com/o/r/commit/abcd",
        metrics="elapsed=2m",
    )
    assert text.startswith("Agentix Reviewer BLOCKED")
    assert "P1-02" in text
    assert "commit:" in text


def test_cli_status_disabled(tmp_path: Path):
    from memory.integrations.__main__ import main

    _write_cfg(tmp_path, {})
    rc = main(["--workdir", str(tmp_path), "status"])
    assert rc == 0


def test_select_git_intent_excludes_mcp_skills():
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    out = subprocess.check_output(
        [sys.executable, str(repo / "tools" / "select.py"), "--intent", "git", "--list"],
        cwd=str(repo),
        text=True,
    )
    assert "mcp-linear" not in out
    assert "mcp-jira" not in out
    assert "mcp-slack" not in out
    assert "git-commit-to-jira-tasks" not in out


def test_select_tracker_intent_lists_mcp_skills():
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    out = subprocess.check_output(
        [sys.executable, str(repo / "tools" / "select.py"), "--intent", "tracker", "--list"],
        cwd=str(repo),
        text=True,
    )
    assert "mcp-linear" in out
    assert "mcp-jira" in out
    assert "git-commit-to-jira-tasks" not in out


def test_git_commit_jira_skill_contract_untouched():
    repo = Path(__file__).resolve().parents[1]
    text = (repo / "skills" / "git-commit-to-jira-tasks" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "disable-model-invocation: true" in text
    for name in ("mcp-linear", "mcp-jira", "mcp-slack"):
        yaml = (repo / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "disable-model-invocation: true" in yaml


def test_supervisor_mock_cycle_with_linear_and_slack(tmp_path: Path, monkeypatch):
    from memory.supervisor import Terminal, run_loop

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    for name in ("orchestrator", "coder", "tester", "debugger", "reviewer"):
        (prompts / f"short_{name}_prompt.md").write_text(f"# {name}\n", encoding="utf-8")
    _write_cfg(
        tmp_path,
        {
            "supervisor": {
                "adapter": "mock",
                "max_cycles": 1,
                "max_role_retries": 1,
            },
            "integrations": {
                "issue_tracker": {
                    "provider": "linear",
                    "project_id": "AGX",
                    "enabled": True,
                    "base_url": "https://api.linear.app/graphql",
                },
                "slack": {
                    "enabled": True,
                    "channel": "#agentix",
                    "force": True,
                },
            },
            "tier": {"feature_flags": {"enterprise_governance": False}},
        },
    )
    _write_todo(tmp_path, "- [ ] P1-01 Auth refresh\n")
    fake = FakeHttp()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key_value")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/XXX")
    monkeypatch.chdir(tmp_path)
    result = run_loop(
        workdir=tmp_path, adapter_name="mock", max_cycles=1, create_pr=False
    )
    assert result["terminal"] in (
        Terminal.PR_READY,
        Terminal.PR_READY_LOCAL,
        "PR_READY",
        "PR_READY_LOCAL",
    )
    assert fake.linear_created >= 1
    slack_posts = [
        c
        for c in fake.calls
        if "hooks.slack.com" in c.full_url
    ]
    assert slack_posts
