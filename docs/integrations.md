# Integrations

MCP-ready integration patterns for enterprise workflows. Linear, Jira, and Slack **ship in this repo** (Agentix Hub 3.13.0). Default **off**. Opt-in via `.agent/project_config.json`.

Design: [superpowers/specs/2026-08-27-mcp-linear-jira-slack-design.md](superpowers/specs/2026-08-27-mcp-linear-jira-slack-design.md).

## GitHub Actions — Loop Trigger

Workflow: [.github/workflows/agentix-loop.yml](../.github/workflows/agentix-loop.yml)

Triggers:

- **pull_request** and **push** to `main`
- **Manual** (`workflow_dispatch`) with `cycle_goal` input
- **Weekly** schedule (Monday 08:00 UTC)

The `harness` job does an editable install (`pip install -e ".[dev,dashboard]"`), proves G1 (`import memory` from `/tmp` with PYTHONPATH unset), runs `pytest memory/` including the full mock O→C→T→R cycle, then Agent-Init + Hub export + audit. `stdlib-collect` installs `.[dev]` only and collect-only supervisor tests. Mock/CI skip live pxpipe. Tests **never** call live Linear/Jira/Slack.

```bash
gh workflow run agentix-loop.yml -f cycle_goal="P5-governance"
```

## Linear / Jira (cycle issue sync)

Skills: [mcp-linear](../skills/mcp-linear/SKILL.md), [mcp-jira](../skills/mcp-jira/SKILL.md). Runtime: `python -m memory.integrations`.

1. Read open INVEST tasks from `.agent/TODO.md`
2. Create/update issues on cycle start (Orchestrator hook, fail-open)
3. Close issues on Reviewer `DONE`

```json
"integrations": {
  "issue_tracker": {
    "provider": "linear",
    "project_id": "AGX",
    "enabled": false,
    "base_url": null
  }
}
```

Set `"enabled": true` and `provider` to `"linear"` or `"jira"`. Secrets stay in the environment:

| Provider | Env |
|----------|-----|
| Linear | `LINEAR_API_KEY`, optional `LINEAR_TEAM_ID` |
| Jira Cloud | `JIRA_BASE_URL`, `JIRA_EMAIL` + `JIRA_API_TOKEN` **or** `JIRA_PAT` |
| Jira DC | `JIRA_BASE_URL`, `JIRA_PAT` (`base_url` not `*.atlassian.net` → REST v2) |

```bash
python -m memory.integrations status --workdir .
python -m memory.integrations sync --dry-run
python -m memory.integrations sync --apply
python -m memory.integrations close --apply
```

CLI default is dry-run unless `--apply` or `AUTO_CONFIRM=1`. Supervisor writes only when `enabled: true`. Mapping: `.agent/integrations-issues-state.json` (gitignored).

This is **not** [git-commit-to-jira-tasks](../skills/git-commit-to-jira-tasks/SKILL.md) (commit clustering, Story Points, never `--intent git`). Do not attach cycle-sync skills to `--intent git`. Optional: `python tools/select.py --intent tracker`.

## Slack Notifications

Skill: [mcp-slack](../skills/mcp-slack/SKILL.md).

On Reviewer `DONE` or `BLOCKED`:

- Post compact summary + commit link
- Include performance metrics from the ledger when present

```json
"integrations": {
  "slack": { "enabled": false, "channel": "#agentix", "webhook_url": null, "force": false }
},
"tier": {
  "feature_flags": { "enterprise_governance": false }
}
```

Posts iff `integrations.slack.enabled` **and** (`tier.feature_flags.enterprise_governance` **or** `integrations.slack.force`). Env: `SLACK_WEBHOOK_URL` or `SLACK_BOT_TOKEN`. Example config keeps `webhook_url` null.

```bash
python -m memory.integrations notify --status DONE --dry-run --force
python -m memory.integrations notify --status DONE --apply
python tools/select.py --intent slack
```

## GitHub MCP (Built-in)

Use `grok_com_github` MCP tools for PR creation, status checks, and branch management per `TOOLS_REGISTRY.md`. Not reimplemented here.

## Audit on Integration Events

```bash
python -m memory.audit_log append \
  --action "slack_notify" \
  --role "reviewer" \
  --cycle 60 \
  --details '{"channel":"#agentix","status":"DONE"}'
```

Runtime also appends `issue_sync`, `issue_close`, and `slack_notify`. Details never include tokens or webhook URLs.

## Optional extras

Empty era markers (stdlib urllib is enough):

```bash
pip install -e ".[mcp]"
# or .[linear] / .[jira] / .[slack]
```
