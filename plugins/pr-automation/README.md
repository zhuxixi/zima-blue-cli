# pr-automation

Claude Code plugin for GitHub PR automation. Designed to be driven by the [zima](https://github.com/zhuxixi/zima-blue-cli) daemon scheduler, but works standalone in any Claude Code session that has the `gh` CLI available.

## Skills

| Skill | Purpose | Trigger phrases |
|---|---|---|
| `github-code-review-batch` | One-shot batch / scheduled CR for a single PR. Multi-agent parallel review against `CLAUDE.md` + `AGENTS.md`, issue-validation false-positive filtering, metadata-persisted state for cross-session scheduling. | `batch review pr`, `review pr batch`, `scheduled review pr` |

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

The skill is a **one-shot short session** — it executes one CR round, posts a PR comment, and exits. State persists in PR review metadata (`cc-cr-meta` / `kimi-cr-meta`) so an external scheduler (zima daemon) can alternate between CR and fix agents across rounds.

This is not a watcher process. If you want continuous monitoring, that's a separate concern (and a future skill in this plugin).

## Roadmap

- `github-code-review-batch` ✅
- `pr-monitor` (planned) — watch a PR for CR + CI results, auto-fix and auto-merge

## License

MIT
