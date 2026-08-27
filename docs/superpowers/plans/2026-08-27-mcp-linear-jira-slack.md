# Full MCP skills for Linear, Jira, Slack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Subagent prompts in English.

**Goal:** Ship Agentix Hub **3.13.0** — opt-in Linear **and** Jira cycle issue sync plus Slack Reviewer notifications. Skills + stdlib `memory/integrations/` adapters. Default `enabled: false`.

**Architecture:** Shared `IssueTracker` protocol; `provider` selects Linear GraphQL or Jira REST. Slack is a separate notifier gated by `integrations.slack.enabled` AND (`enterprise_governance` OR `force`). Supervisor calls fail-open hooks. `git-commit-to-jira-tasks` stays untouched in contract (`disable-model-invocation: true`, never `--intent git`).

**Tech Stack:** Python 3.10+, stdlib urllib/json/hashlib. Existing `memory.agent_lock`, `memory.audit_log`, `memory.performance_ledger`. No required new deps. Empty extras `mcp`, `linear`, `jira`, `slack`.

**Spec:** [`../specs/2026-08-27-mcp-linear-jira-slack-design.md`](../specs/2026-08-27-mcp-linear-jira-slack-design.md)

**Branch:** `feature/v3.13.0-mcp-linear-jira-slack` from `main` (3.12.0, `b686dc8` seed). Merge to `main` after pytest.

**Out of scope:** Hub SaaS, Control Plane redesign, pxpipe ports, GitHub MCP, PyPI, rewrite of git-commit-to-jira-tasks, live third-party HTTP in tests.

**House rules:** comments and commit messages in natural Russian (`DEVELOPMENT_STANDARDS.md` §1). Public names, skill YAML, README headings English. Do not mention AI/agents in commits. Do not commit live `.agent/` dirt. Interpreter: `/home/unhex/_PROJECT/agentix-hub/.venv/bin/python`.

---

## File map

| Path | Action |
|------|--------|
| `memory/integrations/__init__.py` | Create — public API |
| `memory/integrations/config.py` | Create — gates |
| `memory/integrations/todo.py` | Create — TODO.md parser |
| `memory/integrations/http.py` | Create — urllib JSON |
| `memory/integrations/state.py` | Create — mapping file + lock |
| `memory/integrations/tracker.py` | Create — protocol + factory |
| `memory/integrations/linear.py` | Create — GraphQL |
| `memory/integrations/jira.py` | Create — REST v3/v2 |
| `memory/integrations/slack.py` | Create — webhook / Web API |
| `memory/integrations/hooks.py` | Create — supervisor callbacks |
| `memory/integrations/__main__.py` | Create — CLI |
| `memory/test_integrations.py` | Create — hermetic tests |
| `memory/supervisor.py` | Fail-open hook calls only |
| `skills/mcp-linear/` | Create SKILL.md + scripts |
| `skills/mcp-jira/` | Create SKILL.md + scripts |
| `skills/mcp-slack/` | Create SKILL.md + scripts |
| `skills/README.md` | Three When-to-load rows |
| `tools/select.py` | Optional intents `tracker` / `slack` (not `git`) |
| `.agent/project_config.example.json` | Default-off keys, no secrets |
| `.gitignore` | `integrations-issues-state.json` |
| `pyproject.toml` | Empty extras |
| `docs/integrations.md` | Shipped contract |
| `VERSION` / `CHANGELOG.md` / `ROADMAP.md` / README badges | 3.13.0 |

**Interpreter:** `/home/unhex/_PROJECT/agentix-hub/.venv/bin/python`. Tests: `PYTHONPATH=. pytest memory/test_integrations.py memory/test_supervisor_mock_cycle.py -q` then full `pytest memory/`.

**Topo:** Task 1 parser+config tests → Task 2 HTTP+Linear+Jira → Task 3 Slack+audit → Task 4 hooks+supervisor → Task 5 skills+CLI → Task 6 docs/version.

---

## Task 1: Parser, config gates, tests first

**Files:**
- Create: `memory/integrations/config.py`, `memory/integrations/todo.py`, `memory/integrations/__init__.py`
- Create: `memory/test_integrations.py` (parser + gate cases)

- [ ] **Step 1: Write failing tests for TODO parser and gates**

- [ ] **Step 2: Implement parser + `tracker_enabled` / `slack_enabled`**

- [ ] **Step 3: Run** `.venv/bin/python -m pytest memory/test_integrations.py -q` until parser/gate tests pass.

Commit: parser and config gates.

---

## Task 2: HTTP helper, state, Linear, Jira

- [ ] **Step 1: Tests** for mocked Linear GraphQL create/update/close and Jira REST create/close. Disabled config must not call `urlopen`.

- [ ] **Step 2: Implement** `http.py`, `state.py`, `tracker.py`, `linear.py`, `jira.py`, `sync_open_issues`, `close_done_issues`.

- [ ] **Step 3: Pytest** those cases.

Commit: трекер Linear/Jira за stdlib urllib.

---

## Task 3: Slack + audit

- [ ] **Step 1: Tests** webhook POST body, governance gate, `--force`, no secrets in audit details.

- [ ] **Step 2: Implement** `slack.py` + ledger/commit helpers.

- [ ] **Step 3: Pytest**.

Commit: Slack webhook и аудит без секретов.

---

## Task 4: Supervisor hooks

- [ ] **Step 1: Test** mock cycle still PR_READY with integrations omitted; enabled Linear+Slack with mocked urlopen records sync + notify.

- [ ] **Step 2: `hooks.py` + three call sites in `run_loop`** (cycle start, PR_READY, BLOCKED). Fail-open WARNING.

- [ ] **Step 3: Pytest** `test_supervisor_mock_cycle.py` + new hook tests.

Commit: хуки супервизора, по умолчанию молчат.

---

## Task 5: CLI + skills + select.py

- [ ] **Step 1:** `python -m memory.integrations` CLI (`sync`/`close`/`notify`/`status`). CLI default dry-run; `--apply` writes.

- [ ] **Step 2:** Three skill trees. Scripts invoke the CLI. README rows. Optional `--intent tracker|slack`. Confirm `--intent git` does not list them. `git-commit-to-jira-tasks` YAML unchanged.

- [ ] **Step 3:** Smoke CLI `--help` and `select.py --intent git --list`.

Commit: навыки MCP и CLI.

---

## Task 6: Config example, docs, 3.13.0

- [ ] Example JSON default-off + gitignore state file + empty extras.
- [ ] `docs/integrations.md` shipped contract.
- [ ] VERSION 3.13.0, CHANGELOG, ROADMAP Future bullet removed, badges README / README.ru / docs.
- [ ] Full `pytest memory/`. Fix failures caused here. Unrelated flakes: retry once.
- [ ] Merge to `main`, `git push origin main`.

Commit: версия 3.13.0 и документация интеграций.

---

## Public helpers (lock these names)

```python
def parse_todo_md(text: str) -> list[TodoItem]: ...
def tracker_enabled(cfg: dict) -> bool: ...
def slack_enabled(cfg: dict, *, force: bool = False) -> bool: ...
def get_tracker(cfg: dict, *, environ=None, http=None) -> IssueTracker | None: ...
def sync_open_issues(workdir: Path, *, dry_run: bool = False) -> dict: ...
def close_done_issues(workdir: Path, *, task_id: str | None = None, dry_run: bool = False) -> dict: ...
def notify_slack(workdir: Path, *, status: str, handoff: dict | None = None, force: bool = False) -> dict: ...
```

---

## Verification

```bash
/home/unhex/_PROJECT/agentix-hub/.venv/bin/python -m pytest memory/ -q
python tools/select.py --intent git --list   # must not mention mcp-linear/jira/slack
grep -n 'disable-model-invocation' skills/git-commit-to-jira-tasks/SKILL.md skills/mcp-*/SKILL.md
```

Default `project_config.example.json`: `enabled: false` for tracker and slack.
