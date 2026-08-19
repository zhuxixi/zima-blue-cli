# Spec: issue #158 — trust pinned PR in preExec scan_pr

## Decision Table

| Caller context | env has pr_number/pr? | Behavior |
|---|---|---|
| Webhook trigger (server.py spawn) | yes (`pr_number` after fix; `pr` accepted for back-compat) | Trust pinned PR: discovered = {repo, pr_number, pr_url}, skip scan_prs + recency filter + diff fetch |
| Daemon polling (45-min schedule) | no | Current path unchanged: scan_prs label rescan + skip-set filter + fetch_diff |
| Manual `zima pjob run <code>` with --set-var=pr_number=N | yes | Same as webhook (pinned wins) |
| Manual without pinned vars | no | Current path |

## Data Flow (pinned branch)

```
webhook labeled event (repo=zhuxixi/X, pr=11, head_sha=abc)
  → server spawn: zima pjob run <code> --set-var=repo=... --set-var=pr_number=11 --set-var=head_sha=...
  → overrides.variable_values = {repo, pr_number, head_sha}
  → pre_env (env_vars + variable config values, setdefault semantics)
  → run_pre scan_pr branch: pinned = env.pr_number → discovered{repo, pr_number, pr_url=https://github.com/<repo>/pull/<n>}
  → inject_dynamic_vars (overrides win — same value anyway)
  → Jinja2: batch review pr {{ pr_url }} renders correctly
  → postExec add_label uses {{repo}}/{{pr_number}} — both present
```

## Component Contract (actions_runner.py, scan_pr branch)

Insert after repo/label empty-guards, before `provider.scan_prs`:

```python
pinned = (env.get("pr_number") or env.get("pr") or "").strip()
if pinned:
    discovered["repo"] = repo
    discovered["pr_number"] = pinned
    discovered["pr_title"] = ""
    discovered["pr_url"] = f"https://github.com/{repo}/pull/{pinned}"
    continue
```

- `pr_url` constructed from repo+pinned (GitHub canonical URL format; identical to what scan_prs returns via gh).
- `pr_diff` NOT set: zero template consumers today (verified across all 7 CR workflows).
- Failure semantics: pinned branch cannot raise SkipAction-by-empty-scan; a bad PR number surfaces later via agent/postExec gh failure, same as today's path for stale PRs.

## Secondary alignment (webhook/server.py)

`--set-var=pr=` → `--set-var=pr_number=` (name nothing consumes today; runner accepts both names). One-line change.

## Non-Goals

- No retry/backoff on scan_prs (pinned path removes the race; polling path doesn't race).
- No pr_diff/pr_title population for pinned runs.
- No change to skip-set recency filter (polling-path only, untouched).

## Degradation

- If pinned value is wrong (misconfigured manual run), agent gets a bad pr_url → review fails → postExec failure path labels zima:needs-fix. Same observable behavior as a stale PR today; no new failure mode.

---

## Revision (post CR rounds 1-3, 2026-08-17)

The shipped behavior evolved through CR review; this section supersedes the
original Component Contract where they differ:

- **pr_diff IS populated** on the pinned path (direct `gh pr view`, no
  search-index race). An empty diff or a raised exception (after 3 bounded
  retries) is a SkipAction — never review an empty diff.
- **Malformed pinned values** (non-numeric after `#` normalization) raise
  SkipAction immediately; the message reports length only, never the raw value.
- **Pin source is the runtime `execute()` overrides argument only** — static
  Variable config values and PJob YAML `spec.overrides` never pin.
- **postExec action_env** merges `overrides.variable_values` so `{{pr_number}}`
  substitution works even when the PJob references no Variable config.
- webhook server injects both `pr_number` and legacy `pr` during the
  compatibility window.
- **`spec.overrides` `pr`/`pr_number` keys are deprecated**: a stale static
  value that disagrees with the scanned PR is popped (with a warning) before
  merge-back, and a finally-block safety net forces the scanned value into
  postExec substitution under both alias keys.
