---
name: mcp-slack
author: agentix / exception.expert
version: 1.0.0
disable-model-invocation: true
description: >
  Opt-in Agentix MCP skill (disabled by default; do not auto-invoke).
  Posts a compact Slack summary on Reviewer DONE or BLOCKED (commit link +
  ledger metrics). Gate: integrations.slack.enabled AND
  (tier.feature_flags.enterprise_governance OR integrations.slack.force).
---

# mcp-slack

**Purpose:** One compact Slack message when the Reviewer finishes a cycle (`DONE` or `BLOCKED`).

**Load contract:** Explicit `Follow skills/mcp-slack/SKILL.md` **or** supervisor hook when Slack is gated on. Never `--intent git`. YAML hosts: `disable-model-invocation: true`.

## Gates (all default off)

```json
"integrations": { "slack": { "enabled": false, "channel": "#agentix", "force": false } },
"tier": { "feature_flags": { "enterprise_governance": false } }
```

Posts only when `enabled` is true **and** (`enterprise_governance` **or** `force`). CLI `--force` bypasses the gate for a single run.

## Required inputs

- Env `SLACK_WEBHOOK_URL` **or** `SLACK_BOT_TOKEN` (Web API `chat.postMessage`)
- Optional `SLACK_CHANNEL` / `integrations.slack.channel` (default `#agentix`)
- Ledger `.agent/PERFORMANCE_LEDGER.json` if metrics should appear

## Workflow

1. `python -m memory.integrations status`
2. Preview: `python -m memory.integrations notify --status DONE --dry-run --force`
3. Apply: add `--apply` (or let the supervisor hook fire)
4. Audit: `python -m memory.audit_log list` — action `slack_notify` (channel + status, **no** webhook)

Helper: `skills/mcp-slack/scripts/notify.sh`

Message shape:

```
Agentix Reviewer DONE · cycle 12 · task P1-01
commit: https://github.com/org/repo/commit/abc123
elapsed=1.6m confidence=0.94 tests_failed=0
```

## Anti-patterns

- Enabling Slack in the example config
- Putting webhook URLs in git or audit details
- Loading from `--intent git`
- Live Slack calls in pytest

## Output

JSON `{ok, skipped, channel, reason}`. Secrets omitted.
