---
name: mcp-jira
author: agentix / exception.expert
version: 1.0.0
disable-model-invocation: true
description: >
  Opt-in Agentix MCP skill (disabled by default; do not auto-invoke).
  Syncs open INVEST items from .agent/TODO.md to Jira issues on cycle start
  and closes them on Reviewer DONE. This is NOT git-commit-to-jira-tasks.
  Load only when integrations.issue_tracker.provider=jira and enabled=true,
  or when the user explicitly follows this skill.
---

# mcp-jira

**Purpose:** Cycle-level Jira Task upsert/close from `.agent/TODO.md`. **Not** a rewrite of `skills/git-commit-to-jira-tasks` (commit clustering, Story Points, dry-run clustering).

**Load contract:** Explicit `Follow skills/mcp-jira/SKILL.md` **or** supervisor hook when `provider: "jira"` and `enabled: true`. Never `--intent git`. YAML hosts: `disable-model-invocation: true`.

## Required inputs

- `.agent/TODO.md`
- `integrations.issue_tracker.project_id` (Jira project key) and `base_url`
- Env: `JIRA_BASE_URL`; Cloud `JIRA_EMAIL` + `JIRA_API_TOKEN` **or** `JIRA_PAT`; DC `JIRA_PAT`
- Do not call unscoped `/issue/createmeta`

## Workflow

1. `python -m memory.integrations status`
2. `python -m memory.integrations sync --dry-run` then `--apply`
3. Reviewer DONE: `python -m memory.integrations close --apply`
4. Close uses discovered Done/Closed transitions only

Helper: `skills/mcp-jira/scripts/sync.sh`

Keep `git-commit-to-jira-tasks` for commit→Story clustering. This skill only mirrors INVEST TODO rows.

## Anti-patterns

- One Jira issue per git commit (wrong skill)
- Attaching this skill to `--intent git`
- Hard-coding Story Points field ids
- Logging PAT / API token

## Output

JSON report of keys. No secrets.
