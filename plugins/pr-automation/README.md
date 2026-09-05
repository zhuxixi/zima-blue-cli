# pr-automation

Claude Code plugin for GitHub PR automation. Designed to be driven by the [zima](https://github.com/zhuxixi/zima-blue-cli) daemon scheduler, but works standalone in any Claude Code session that has the `gh` CLI available.

## Skills

| Skill | Purpose | Trigger phrases |
|---|---|---|
| `github-code-review-batch` | One-shot batch / scheduled CR for a single PR. Multi-agent parallel review against `CLAUDE.md` + `AGENTS.md`, blocking/advisory severity policy, `<zima-review>` XML verdict trailer, changed-file-scoped tool layer, issue-validation false-positive filtering, metadata-persisted state for cross-session scheduling. | `batch review pr`, `review pr batch`, `scheduled review pr` |

> The trigger phrases are an external contract with the zima daemon — do not rename without coordinated changes on both sides.

## Requirements

- `gh` CLI authenticated against the target repo
- Python 3.10+ (for the deterministic helper scripts under `skills/*/scripts/`)
- Claude Code with sub-agent support (the skill spawns parallel review agents)

## Install

```
/plugin marketplace add zhuxixi/zima-blue-cli
/plugin install pr-automation@zima-blue
```

## Relationship to zima daemon

The skill is a **one-shot short session** — it executes one CR round, posts a PR comment, and exits. State persists in PR review metadata (`cc-cr-meta`; `pi-cr-meta` and legacy `kimi-cr-meta` comments from other review bots are ignored) so an external scheduler (zima daemon) can alternate between CR and fix agents across rounds.

This is not a watcher process. If you want continuous monitoring, that's a separate concern (and a future skill in this plugin).

## Release notes

- **0.6.0** — Aligned with the pi version of the skill: blocking/advisory severity policy (`blocking_open_count` drives status and fix scheduling; low-severity findings stay advisory), `<zima-review>` XML verdict trailer in the terminal report for zima postExec label transitions, and changed-file-scoped tool layer (#174). **Scheduler-visible boundary change**: advisory-only rounds now report `PASS` and no longer trigger fix-agent scheduling on existing cc fallback PJob configs — previously any open issue forced `NEEDS_FIX`.

## Roadmap

- `github-code-review-batch` ✅
- `pr-monitor` (planned) — watch a PR for CR + CI results, auto-fix and auto-merge

## License

MIT
