---
name: mcp-linear
author: agentix / exception.expert
version: 1.0.0
disable-model-invocation: true
description: >
  Opt-in Agentix MCP skill (disabled by default; do not auto-invoke).
  Syncs open INVEST items from .agent/TODO.md to Linear issues on cycle start
  and closes them on Reviewer DONE. Load only when
  integrations.issue_tracker.provider=linear and enabled=true, or when the
  user explicitly follows this skill.
---

# mcp-linear

**Purpose:** Keep Linear issues in lockstep with `.agent/TODO.md` for the Agentix loop. This is **cycle issue sync**, not git-commit clustering.

**Load contract:** Explicit `Follow skills/mcp-linear/SKILL.md` **or** supervisor hook when `project_config.json` has `integrations.issue_tracker.enabled: true` and `provider: "linear"`. Never via `python tools/select.py --intent git`. Hosts that honor YAML must treat `disable-model-invocation: true`.

## Required inputs

- `.agent/TODO.md` with INVEST checkboxes (`- [ ] P1-01 Title`)
- `integrations.issue_tracker.project_id` = Linear team key
- Env `LINEAR_API_KEY` (never paste into chat). Optional `LINEAR_TEAM_ID`
- Default remains **off**. Do not invent a team or enable the flag yourself.

## Workflow

1. Confirm `python -m memory.integrations status --workdir .` shows `tracker_enabled: true` and `provider: linear`.
2. Preview: `python -m memory.integrations sync --workdir . --dry-run`
3. Apply (or let the supervisor hook do it on Orchestrator cycle start): `... sync --apply` or `AUTO_CONFIRM=1`
4. On Reviewer DONE: `python -m memory.integrations close --apply`
5. Mapping lives in `.agent/integrations-issues-state.json` (gitignored)

Helper: `skills/mcp-linear/scripts/sync.sh`

## Anti-patterns

- Enabling the tracker without a key
- Loading this skill from `--intent git`
- Rewriting `skills/git-commit-to-jira-tasks` (different surface)
- Logging `LINEAR_API_KEY`
- Calling live Linear from pytest

## Output

JSON report: created / updated / unchanged / closed keys. No secrets.
