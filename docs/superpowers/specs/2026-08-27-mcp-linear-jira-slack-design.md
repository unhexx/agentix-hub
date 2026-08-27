# Full MCP skills for Linear, Jira, Slack — Design (Agentix Hub 3.13.0)

**Title:** Opt-in Linear/Jira issue sync + Slack cycle notifications (MCP skills + stdlib adapters)  
**Author:** Agentix Hub cycle  
**Date:** 2026-08-27  
**Status:** Accepted for implementation (this fire)  
**Repo / home:** `agentix-hub` (product line: MCP skills), import package `memory`  
**Baseline:** VERSION **3.12.0**, seed commit `b686dc8` of `unhexx/agentic_loop_template`.  
**Target version:** **3.13.0** (minor: new opt-in integration surface. Not 4.0.0. Not a 3.12.x patch.)  
**Canonical landing path:** `docs/superpowers/specs/2026-08-27-mcp-linear-jira-slack-design.md`  
**Roadmap item:** Future — “Full MCP skills for Linear/Jira/Slack”

This document specifies the smallest complete F: Linear **and** Jira **and** Slack. It does **not** spawn hosted Hub SaaS (item E), does not rewrite Control Plane / supervisor roles / playbooks embeddings, and does not replace `skills/git-commit-to-jira-tasks`.

---

## Decision (this fire)

| Option | What | Verdict |
|--------|------|---------|
| A. Hosted Hub SaaS first | Item E, billing, catalog | Rejected. This repo is assigned F, not E. Keep the existing static Hub JSON feed. |
| B. Skill Markdown only | SKILL.md with no Python | Rejected. Supervisor cannot create/close issues on cycle start / Reviewer DONE without a callable. |
| C. Required Linear/Jira/Slack SDKs | `linear`, `jira`, `slack-sdk` in `[project] dependencies` | Rejected. Stdlib install must keep working. |
| D. Rewrite `git-commit-to-jira-tasks` | One Jira skill for commits + cycle sync | Rejected. That skill is REST clustering, `disable-model-invocation: true`, never `--intent git`. Different surface. |
| E. Always-on supervisor HTTP | Fire Linear/Jira/Slack every cycle | Rejected. Default `enabled: false`. Opt-in only. |
| **F. Skills + stdlib adapters + config gate, 3.13.0** | MCP skill packages; `memory/integrations/` urllib adapters; Linear vs Jira behind one protocol; Slack webhook/Web API; fail-open supervisor hooks | **Accepted.** |

---

## Overview

`docs/integrations.md` already sketches the contract:

1. Read open INVEST tasks from `.agent/TODO.md`.
2. Create/update issues on cycle start (Orchestrator).
3. Close issues on Reviewer `DONE`.
4. On Reviewer `DONE` or `BLOCKED`: post a compact Slack summary (commit link + ledger metrics).
5. Audit via `python -m memory.audit_log append --action slack_notify ...`.

Today that is documentation only. This fire ships the skills, the Python adapters, the config keys, hermetic tests, and opt-in supervisor hooks. Default remains off. No live Linear/Jira/Slack in pytest.

---

## Background and motivation

### Current state (verified 2026-08-27 on seed `b686dc8`)

| Layer | What exists | Gap vs F |
|-------|-------------|----------|
| Docs | `docs/integrations.md` stub JSON `integrations.issue_tracker` | No runtime. |
| Config | `.agent/project_config.example.json` has no `integrations` / `tier` | Gate keys missing. |
| Jira skill | `skills/git-commit-to-jira-tasks/` — commit clustering, dry-run default, never `--intent git` | Cycle issue sync is a different skill. Do not collide. |
| GitHub MCP | `grok_com_github` per `TOOLS_REGISTRY.md` | Do not reimplement GitHub. |
| Slack | Audit example `--action slack_notify` | No HTTP, no skill. |
| Supervisor | `run_loop` fail-open `maybe_cycle_on_done` on `PR_READY` | No tracker/Slack hook. |
| HTTP | `memory/playbooks_embed.py` stdlib urllib + monkeypatch tests | Pattern to copy. |
| Hub | Static `docs/hub/` JSON feed | Keep; do not build SaaS. |
| ROADMAP Future | “Full MCP skills for Linear/Jira/Slack” | This fire. |

Pain: consumers who already set `issue_tracker.enabled` in the stub have nothing to call. Reviewer DONE does not close a Linear/Jira issue and does not notify Slack.

---

## Goals and non-goals

### Goals

| ID | Goal |
|----|------|
| G1 | `skills/mcp-linear`, `skills/mcp-jira`, `skills/mcp-slack`: English SKILL.md + thin scripts. YAML `disable-model-invocation: true`. Never attached to `--intent git`. |
| G2 | Shared `IssueTracker` protocol. `integrations.issue_tracker.provider` is `"linear"` or `"jira"`. Factory returns one adapter. |
| G3 | Default `integrations.issue_tracker.enabled: false` and Slack off. Missing section ≡ disabled. Opt-in only. |
| G4 | Cycle start (Orchestrator, including `_should_start_new_cycle`): upsert open TODO items. Reviewer `DONE` (`PR_READY`): close mapped issues that are done in TODO (or the current task id). Fail-open: WARNING, loop continues. |
| G5 | Slack on Reviewer `DONE` / `BLOCKED`: compact text + commit link + last ledger cycle. Gate: `integrations.slack.enabled` **and** (`tier.feature_flags.enterprise_governance` **or** `integrations.slack.force`). Default off. |
| G6 | HTTP via stdlib `urllib`. No required new deps. Optional empty extras `mcp` / `linear` / `jira` / `slack` as era markers (do not import-check them). |
| G7 | CLI `python -m memory.integrations {sync,close,notify,status}`. Audit actions `issue_sync`, `issue_close`, `slack_notify`. |
| G8 | Hermetic tests (`memory/test_integrations.py` and siblings): mock urllib; no live Linear/Jira/Slack. `importorskip` only if a future extra actually imports. VERSION **3.13.0**. |

### Non-goals

| ID | Non-goal | Why |
|----|----------|-----|
| NG1 | Hosted Hub SaaS, billing, live catalog | Item E, not this repo’s assignment. |
| NG2 | Redesign Control Plane, role chain, playbooks embeddings, pxpipe `:8110` / host `:8100` / CP `:8112` | Unrelated. |
| NG3 | Rewrite `git-commit-to-jira-tasks` or attach it to `--intent git` | Keep that contract. |
| NG4 | Reimplement GitHub MCP | Already `grok_com_github`. |
| NG5 | Required `linear` / `jira` / `slack-sdk` packages | Stdlib urllib. |
| NG6 | Auto-load skills on every cycle without config | Gate is `enabled`. |
| NG7 | Live third-party HTTP in pytest | Mock only. |
| NG8 | PyPI publish; rename import package `memory` | Out of scope. |
| NG9 | Bitbucket / git.aservice24.ru remote | Only if `gh`/`git` against that host succeeds without prompting. |

---

## Public names (English, lock these)

### Config (`.agent/project_config.json`)

```json
"integrations": {
  "issue_tracker": {
    "provider": "linear",
    "project_id": "AGX",
    "enabled": false,
    "base_url": null
  },
  "slack": {
    "enabled": false,
    "channel": "#agentix",
    "webhook_url": null,
    "force": false
  }
},
"tier": {
  "level": "free",
  "feature_flags": {
    "hub_premium": false,
    "eval_harness": false,
    "enterprise_governance": false
  }
}
```

- `provider`: `"linear"` | `"jira"`. Unknown provider → disabled + WARNING.
- `project_id`: Linear team key **or** Jira project key.
- `base_url`: Jira site (`https://example.atlassian.net`). Linear ignores (fixed `https://api.linear.app/graphql`) unless tests inject it.
- Secrets are **env only**, never committed in the example file:
  - Linear: `LINEAR_API_KEY` (optional `LINEAR_TEAM_ID` overrides lookup)
  - Jira: `JIRA_BASE_URL`, `JIRA_PROJECT_KEY` (fallback `project_id`), `JIRA_PAT` **or** `JIRA_EMAIL` + `JIRA_API_TOKEN`
  - Slack: `SLACK_WEBHOOK_URL` or `SLACK_BOT_TOKEN` (Web API `chat.postMessage`)
- Slack posts iff `integrations.slack.enabled` is true **and** (`enterprise_governance` is true **or** `integrations.slack.force` is true). Missing `tier` + `slack.enabled` is still off unless `force` (fail-closed on the governance flag when a consumer copied Pro-tier JSON with `enterprise_governance: false`). Exception: tests and CLI `--force`.

Clarification of the “and/or” in the stub: **runtime AND**. Both knobs default false. Operators who want Slack on Free tier set `"force": true` together with `"enabled": true`.

### Python API (`memory.integrations`)

```python
class IssueTracker(Protocol):
    def upsert(self, item: TodoItem) -> RemoteIssue: ...
    def close(self, item: TodoItem, remote: RemoteIssue) -> RemoteIssue: ...

def sync_open_issues(workdir: Path, *, dry_run: bool = False) -> SyncReport: ...
def close_done_issues(workdir: Path, *, task_id: str | None = None, dry_run: bool = False) -> SyncReport: ...
def notify_slack(workdir: Path, *, status: str, handoff: dict | None = None, force: bool = False) -> NotifyReport: ...
def on_cycle_start(workdir: Path) -> None: ...          # fail-open
def on_reviewer_done(workdir: Path, handoff: dict | None = None) -> None: ...
def on_reviewer_blocked(workdir: Path, handoff: dict | None = None) -> None: ...
```

CLI:

```bash
python -m memory.integrations sync [--workdir DIR] [--dry-run]
python -m memory.integrations close [--workdir DIR] [--task-id ID] [--dry-run]
python -m memory.integrations notify [--workdir DIR] --status DONE|BLOCKED [--force]
python -m memory.integrations status [--workdir DIR]
```

Dry-run is the CLI default for `sync` / `close` when stdin is a TTY and `AUTO_CONFIRM` is unset — **except** supervisor hooks, which write when `enabled: true` (the config **is** the confirm). CLI `--apply` or `AUTO_CONFIRM=1` also writes.

### Skill YAML

```yaml
name: mcp-linear   # also mcp-jira, mcp-slack
disable-model-invocation: true
```

Load: explicit `Follow skills/mcp-linear/SKILL.md` **or** supervisor hook when config enabled. Not `tools/select.py --intent git`. Optional new intents `tracker` / `slack` may list the skills; they must not be implied by `git`.

---

## Architecture

```
.agent/TODO.md  ──parse──► TodoItem[] ──upsert/close──► IssueTracker
                                   │                      ├─ LinearGraphQL
                                   │                      └─ JiraRest
supervisor run_loop ──hooks──► memory.integrations.hooks (fail-open)
                                   │
                                   └─ SlackNotifier (webhook or Web API)
                                          │
                                          └─ audit_log.append_entry
```

Prefer skills + stdlib urllib. Helpers live under `memory/integrations/` so the supervisor can call them without a model turn.

### File map

| Path | Responsibility |
|------|----------------|
| `memory/integrations/__init__.py` | Public re-exports |
| `memory/integrations/config.py` | Read gates; never log secrets |
| `memory/integrations/todo.py` | Parse `.agent/TODO.md` |
| `memory/integrations/http.py` | `request_json` via urllib |
| `memory/integrations/state.py` | `.agent/integrations-issues-state.json` under `agent_lock(name="integrations")` |
| `memory/integrations/tracker.py` | Protocol + factory |
| `memory/integrations/linear.py` | GraphQL IssueCreate / IssueUpdate |
| `memory/integrations/jira.py` | REST v3 (DC v2 when host is not `atlassian.net`) |
| `memory/integrations/slack.py` | Incoming webhook or `chat.postMessage` |
| `memory/integrations/hooks.py` | Supervisor callbacks |
| `memory/integrations/__main__.py` | CLI |
| `memory/test_integrations.py` | Hermetic tests |
| `skills/mcp-linear/**` | Skill + `scripts/sync.sh` |
| `skills/mcp-jira/**` | Skill + `scripts/sync.sh` |
| `skills/mcp-slack/**` | Skill + `scripts/notify.sh` |
| `.agent/project_config.example.json` | Default-off keys, no secrets |
| `docs/integrations.md` | Stub → shipped contract |

Do not grow `memory/supervisor.py` beyond a few fail-open calls (same shape as `maybe_cycle_on_done`).

---

## Detailed design

### 1. TODO parser

Read `workdir/.agent/TODO.md` (UTF-8). Supported shapes (first match wins per line):

1. Checkbox: `- [ ] P1-01 Title` / `- [x] P1-01 Title` / `- [X]`.
2. Checkbox without id: `- [ ] Title` → `item_id` = slug of title (`auth-refresh`, truncated 40 chars) prefixed `todo-`.
3. Heading + status: `## P1-01 Title` then a following `Status: TODO|OPEN|IN_PROGRESS|DONE|BLOCKED` line.

Open = checkbox unchecked **or** status in `{TODO, OPEN, IN_PROGRESS, BLOCKED}`. Done = checked **or** `DONE`. Skip empty headings (`# TODO`, `# Open`). IDs match `[A-Za-z][A-Za-z0-9]*-\d+` (P1-01, AGX-12, F-03).

### 2. Linear provider

- POST `{base_url or https://api.linear.app/graphql}` with `Authorization: <LINEAR_API_KEY>` (also accept `Bearer ` prefix if the key already has it).
- Resolve team: `LINEAR_TEAM_ID` or GraphQL `teams(filter: { key: { eq: project_id } })`.
- Cache team id + completed workflow state id in the state file (not secrets).
- `issueCreate` / `issueUpdate` with `title`, `description` (Markdown: source line + raw), `teamId`, `stateId` on close (`type: completed`, prefer name Done/Completed/Closed).
- Map `TodoItem.item_id` → `{ remote_id, key=identifier, url }`.
- Idempotent: existing mapping with same title → skip create; title/desc change → update.

### 3. Jira provider (cycle sync, **not** git-commit clustering)

- Cloud: REST v3, Basic `JIRA_EMAIL:JIRA_API_TOKEN` or Bearer `JIRA_PAT`.
- DC/Server (`base_url` not `*.atlassian.net`): REST v2, Bearer `JIRA_PAT`.
- Create: `POST /rest/api/{2|3}/issue` with `project.key`, `issuetype.name=Task` (fallback `Story` if Task 400), `summary`, `description` (ADF doc for v3 plain text fallback: `description` string for v2).
- Do **not** call unscoped `/issue/createmeta`. Optional: `GET /rest/api/{2|3}/issue/createmeta/{project}/issuetypes` when Task fails; tests mock 201 on Task.
- Close: `GET .../issue/{key}/transitions` then `POST .../transitions` picking Done/Closed/Resolved (case-insensitive). If none, WARNING and leave open.
- Labels: set `from-agentix-todo` only when the create response/echo includes labels; if 400 on labels, retry without (fail-open field).
- Do not invent Story Points. Do not POST issue links. That remains `git-commit-to-jira-tasks`.

### 4. Slack

- Prefer `SLACK_WEBHOOK_URL` or `integrations.slack.webhook_url` (config webhook is allowed but example file must stay `null`).
- Else `SLACK_BOT_TOKEN` → `POST https://slack.com/api/chat.postMessage` JSON `{channel, text}`.
- Text (single message, no Block Kit required):

  ```
  Agentix Reviewer DONE · cycle 12 · task P1-01
  commit: https://github.com/org/repo/commit/abc1234
  elapsed=1.6m confidence=0.94 tests_failed=0
  ```

- Commit link: `last_commit` SHA from `git rev-parse HEAD` in workdir + `origin` GitHub HTTPS URL when parseable; else plain SHA. Tests inject sha/url.
- Metrics: last cycle in `PERFORMANCE_LEDGER.json` via existing ledger loader (`agent_dir=`). Missing ledger → omit metrics line, still post summary.
- Audit: `append_entry(action="slack_notify", role="reviewer", cycle=N, details={channel, status})`. Never put webhook/token in details.

### 5. Supervisor hooks

In `run_loop`:

- After `_should_start_new_cycle` persists Orchestrator / IN_PROGRESS: `on_cycle_start(workdir)`.
- On `term == PR_READY` (before `maybe_cycle_on_done`): `on_reviewer_done(workdir, handoff)` — close + Slack DONE.
- On `term == BLOCKED` (both policy-tag return and generic terminal BLOCKED): `on_reviewer_blocked(workdir, handoff)` — Slack only.

Each hook `except Exception: log.warning(...)`. Disabled config returns immediately without HTTP. Mock adapter tests stay green with default example config.

### 6. State and gitignore

Path: `.agent/integrations-issues-state.json` (gitignored). Shape:

```json
{
  "version": 1,
  "provider": "linear",
  "project_id": "AGX",
  "team_id": null,
  "done_state_id": null,
  "items": {
    "P1-01": {
      "remote_id": "uuid-or-key",
      "key": "AGX-12",
      "url": "https://...",
      "title": "Auth refresh",
      "status": "open"
    }
  }
}
```

Writes: tmp+replace under `agent_lock` on the state parent, `name="integrations"`.

### 7. Skills

Each SKILL.md is imperative, short, English public names, opt-in contract. Scripts call `.venv/bin/python -m memory.integrations ...` with `disable-model-invocation` honored by hosts that read YAML.

`skills/README.md` gets three When-to-load rows. Do not add these skills to `SKILL_INTENTS['git']`. Optional `INTENTS['tracker']` / `INTENTS['slack']` empty-block + SKILL_INTENTS is allowed so `python tools/select.py --intent tracker` prints the two tracker skills.

### 8. Tests (hermetic)

| Case | Expectation |
|------|-------------|
| Missing `integrations` / `enabled: false` | `sync_open_issues` / `notify_slack` no urllib |
| Linear upsert | mocked GraphQL team + issueCreate; state maps P1-01 |
| Linear close | mocked issueUpdate with completed state |
| Jira upsert | mocked POST `/issue` 201; mapping by key |
| Jira close | mocked transitions GET + POST |
| Slack webhook | mocked POST body contains DONE + commit + metrics |
| Slack gated | `enabled` true but `enterprise_governance` false and `force` false → no HTTP |
| Supervisor mock cycle | still PR_READY; no urllib if integrations omitted |
| Parser | checkbox + heading fixtures |
| Secrets | responses/logs must not contain `lin_api_` / webhook URL |

Monkeypatch `urllib.request.urlopen` (same style as `memory/test_playbooks_embed.py`). No pytest network plugin required.

### 9. Version / docs

- `VERSION` → `3.13.0`
- CHANGELOG `[3.13.0]` Added/Changed
- ROADMAP: remove Future bullet “Full MCP skills for Linear/Jira/Slack”; add milestone; keep “Hosted Agentix Hub SaaS”
- `docs/integrations.md` becomes the shipped contract (this spec in short)
- README / README.ru / docs badges
- Do not publish to PyPI

---

## Safety

- Default off.
- CLI write path requires `--apply` or `AUTO_CONFIRM=1`; supervisor writes only when `enabled: true`.
- Never log API keys, PATs, webhook URLs.
- Fail-open: tracker/Slack errors do not BLOCK the loop.
- pxpipe remains default request proxy; integration HTTP is **outbound to Linear/Jira/Slack**, not via `:8110`.
- Do not commit live `.agent/` runtime dirt (HUB_INDEX, PLAYBOOKS, PERFORMANCE_LEDGER, stream_leases, integrations-issues-state).

---

## Acceptance

1. New public repo `https://github.com/unhexx/agentix-hub` seeded from template 3.12.0.
2. Design spec + implementation plan committed.
3. Linear, Jira, **and** Slack implemented (not “first skill only”).
4. `pytest memory/` green; no live third-party HTTP.
5. `git-commit-to-jira-tasks` YAML still `disable-model-invocation: true`; `select.py --intent git` does not list MCP tracker skills.
6. Default example config does not enable integrations.
7. HEAD on `origin/main`, VERSION 3.13.0.
