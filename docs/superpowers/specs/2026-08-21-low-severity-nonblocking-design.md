# Issue #183 Design Spec: Low-Severity Findings Are Non-Blocking by Default

- **Issue:** https://github.com/zhuxixi/zima-blue-cli/issues/183
- **Status:** Approved and implemented
- **Scope:** `github-code-review-batch` skill and `zima-pr-monitor` convergence contract

## 1. Problem and goal

PR #7 in `zhuxixi/pi-agent-board` exposed a semantic split:

- The human-readable review body said `No issues above low severity` and called three low findings “suppressed”.
- The `pi-cr-meta` metadata retained those findings as `status: open` and counted them in `new_count`.
- The convergence and fix flow consequently treated advisory documentation findings as mandatory work.

The goal is to make the workflow policy explicit and consistent for every repository:

1. `severity=low` defaults to `blocking=false`.
2. `status` remains a lifecycle field (`open` / `resolved`), not a suppression state.
3. Metadata retains all findings as the factual record and adds a normalized per-finding `blocking` boolean.
4. Convergence, fix scheduling, status, and the `<zima-review>` verdict consider only open blocking findings.
5. Advisory findings remain human-readable in the PR comment, in a collapsed section, and are clearly labeled non-blocking.
6. An explicit boolean `blocking` value can override the severity default.

## 2. Decisions and non-goals

### Decisions

| Decision | Rule |
| --- | --- |
| Default policy | `low` → `blocking=false`; `medium`, `high`, `critical` → `blocking=true` |
| Explicit override | If an issue supplies a boolean `blocking`, preserve it; a low issue can therefore be explicitly upgraded with `blocking=true` |
| Invalid override | Non-boolean values are ignored and fall back to the severity policy |
| Lifecycle | `status` remains `open` / `resolved`; do not add `suppressed` as a lifecycle status |
| Facts vs workflow | Existing all-finding counts remain factual; new blocking/advisory counts drive workflow decisions |
| Legacy metadata | Missing `blocking` is derived from `severity`; missing/invalid severity follows the existing `medium` fallback and is therefore blocking |
| Repository scope | The low default is global for all repositories; no per-repository configuration is introduced |

### Non-goals

- Do not change the default blocking behavior of medium/high/critical findings.
- Do not automatically mark low findings as `acknowledged` or `wontfix`.
- Do not change the matching semantics of the cross-PR suppression mechanism from #126.
- Do not replace the three-state `Status:` contract.
- Do not make the LLM choose severity policy dynamically; blocking normalization is deterministic downstream.

## 3. Data contract

### 3.1 Per-issue schema

Every issue emitted into `pi-cr-meta.issues[]` is copied and normalized without changing its existing fields or input order:

```json
{
  "id": "issue-1",
  "description": "...",
  "reason": "logic",
  "file": "src/example.py",
  "lines": "10-12",
  "status": "open",
  "first_round": 1,
  "severity": "low",
  "blocking": false,
  "resolution": null,
  "committer_note": null
}
```

`blocking` is always present in newly generated metadata. The normalizer uses this rule:

```text
if issue.blocking is a JSON boolean:
    use issue.blocking
else:
    use (normalized_severity(issue) != "low")
```

The existing `_severity()` behavior remains the compatibility source of truth: missing or unknown severity is treated as `medium`.

### 3.2 Top-level metadata counts

Existing fields retain their factual meanings and remain present:

- `total_issues`: all current open findings that are not acknowledged/wontfix, including advisory findings.
- `new_count`: all findings newly introduced in the current round, including advisory findings.
- `resolved_count` and `acknowledged_count`: unchanged.

Add these fields:

- `blocking_open_count`: current open findings with `blocking=true`.
- `blocking_new_count`: current-round new findings with `blocking=true`.
- `advisory_open_count`: current open findings with `blocking=false`.
- `advisory_new_count`: current-round new findings with `blocking=false`.

For Round 1, the current/new source is `issues[]`. For later rounds, current open findings are assembled from the current `issues[]` when present, with `unresolved_issues + new_issues` as the derivation fallback; current-round new findings come from `new_issues`.

Explicit count values supplied by an existing caller continue to win, as with the current `new_count`/`total_issues` behavior. When omitted, the script derives the new fields deterministically from the issue lists.

### 3.3 Status report contract

Keep the existing `open_count` and `new_count` input fields as total/factual counts. Add optional inputs:

```json
{
  "open_count": 3,
  "new_count": 3,
  "blocking_open_count": 0,
  "blocking_new_count": 0,
  "advisory_open_count": 3,
  "advisory_new_count": 3
}
```

When the new blocking fields are present, they are authoritative for workflow status and verdict. When absent, the renderer falls back to legacy behavior (`open_count` and `new_count` are treated as blocking counts), preserving old callers.

The human-readable status report keeps the existing `Status:` line and adds explicit blocking/advisory lines. `Status` remains:

- `NEEDS_FIX` when blocking open findings exist;
- `PASS` when no blocking open findings exist;
- `NO_NEW_COMMITS` for the existing no-new-commit path.

For a new-policy payload, the renderer defensively derives `NEEDS_FIX`/`PASS` from `blocking_open_count` (while preserving `NO_NEW_COMMITS`) so a contradictory caller-supplied status cannot reintroduce the original bug. Legacy payloads without blocking fields retain their supplied status for compatibility.

`Verdict` and `<zima-review>` use the blocking open count:

- blocking critical findings → `BLOCK_MERGE`;
- zero blocking open findings → `READY_TO_MERGE` / `approved`, even when advisory findings remain;
- other blocking findings → `MERGE_WITH_CAUTION` / `needs_fix`;
- `NO_NEW_COMMITS` retains its existing skip behavior, except that zero blocking findings remain approved as today.

The XML summary must say “no blocking issues” when advisory findings remain; it must not claim that all findings are resolved.

## 4. Data flow

1. Review agents continue to emit structured `severity`; `blocking` is optional and is not required for ordinary agent output.
2. Step 6 normalizes each accepted/deduplicated issue with `blocking` using the deterministic policy above.
3. The round assembler computes total, blocking, and advisory counts from the normalized issue collections.
4. `build_review_body.py` writes normalized issue metadata and renders blocking findings normally plus advisory findings in a collapsed section.
5. `render_status_report.py` receives both total and blocking counts. Its status/verdict/XML decisions use blocking counts.
6. The external scheduler and fix agent consume blocking counts/status and act only on `blocking=true` open findings.
7. `zima-pr-monitor` convergence checks `blocking_new_count == 0` and no carried actionable finding with `status=open` and effective `blocking=true`. Acknowledged/wontfix findings are not actionable. For old metadata, missing or invalid `blocking` is derived from normalized severity; missing top-level blocking counts are derived from `issues[]`, with current-round findings identified by `first_round == round`. Open low findings may remain as advisory history without preventing convergence.

The existing #126 cross-PR suppression path remains a separate, opt-in mechanism. A finding may be both advisory by severity policy and matched by that suppression list; neither mechanism changes the lifecycle `status` field.

## 5. Human-readable review rendering

The current word “suppressed” is removed from the ordinary low-severity display because it implies that the finding is exempt from all tracking. Use “advisory” or “non-blocking” instead.

### Round 1

- Render blocking findings in the existing severity-sorted list.
- If advisory findings exist, append a collapsed HTML `<details>` section with their descriptions, severity, file/line links, and an explicit `non-blocking` label.
- If only advisory findings exist, show `No blocking issues found. N advisory findings remain.` rather than `No issues found` or `All issues resolved`.

### Round N

- Keep resolved and acknowledged sections and their counts.
- Render blocking carried/new findings in the existing open sections.
- Render advisory carried/new findings in a collapsed `Advisory / non-blocking findings` section with links.
- `Still open` and `New issues found` must distinguish blocking counts from advisory counts.
- When no blocking findings remain but advisory findings do, state `No blocking issues remain` rather than `All issues resolved`.

This makes the PR comment self-contained; “see terminal report” is no longer the only route to the low-finding details, which is important for webhook-triggered reviews.

## 6. Files and responsibilities

Expected implementation scope:

- `pi/github-code-review-batch/scripts/issue_policy.py` (new): shared severity/blocking normalization and count helpers used by the two render scripts.
- `pi/github-code-review-batch/scripts/build_review_body.py`: normalize metadata, add count fields, and render advisory details.
- `pi/github-code-review-batch/scripts/render_status_report.py`: accept blocking/advisory counts, preserve legacy fallback, and drive status/verdict/XML from blocking counts.
- `pi/github-code-review-batch/references/flow.md`: define Step 6 normalization, count semantics, Step 8/9 rendering, Step 10 status, and convergence inputs.
- `pi/github-code-review-batch/references/delta-review.md`: carry/derive `blocking` for unresolved and new issues; update pass condition.
- `pi/github-code-review-batch/references/subagent-prompts.md`: document optional `blocking` override and clarify that default normalization is downstream.
- `pi/github-code-review-batch/references/output-examples.md`: add low-only and mixed blocking/advisory examples.
- `pi/github-code-review-batch/SKILL.md`: update machine-readable output and `NEEDS_FIX`/`PASS` meanings.
- `pi/zima-pr-monitor/SKILL.md`: use blocking-aware convergence and fix selection while retaining multi-flow and in-flight checks.
- `tests/unit/test_cr_batch_contracts.py`: black-box contract coverage for all new behavior, legacy fallback, and authoritative documentation terms.

No changes are expected in `zima/review/parser.py`: it already consumes the verdict XML and does not need to understand per-issue metadata.

## 7. Verification plan

Tests must be written first and observed failing before implementation:

1. **Policy normalization**
   - low without `blocking` becomes `blocking=false`;
   - medium/high/critical without `blocking` become `true`;
   - explicit low `blocking=true` remains blocking;
   - explicit boolean override is preserved;
   - invalid blocking values use severity fallback.
2. **Round-1 metadata/rendering**
   - low-only metadata keeps all findings and `status=open`, adds `blocking=false`, and reports blocking counts as zero;
   - mixed findings separate blocking/advisory counts;
   - advisory details and links are present in the collapsed PR section.
3. **Round-N/delta behavior**
   - carried low findings do not contribute to blocking open/new counts;
   - carried medium/high findings still do;
   - low-only remainder says no blocking issues, not all findings resolved;
   - explicit low override blocks.
4. **Status report/XML**
   - low-only new-policy payload emits `PASS`, `READY_TO_MERGE`, and `approved`;
   - mixed payload emits `NEEDS_FIX`/`needs_fix` when a blocking finding exists;
   - advisory counts appear in output;
   - legacy payload without blocking fields preserves old behavior;
   - `NO_NEW_COMMITS` behavior remains compatible.
5. **Round-trip/parser**
   - metadata generated by the body builder parses through `parse_metadata.py` with blocking fields intact.
6. **Regression**
   - existing trigger phrase, marker, Status-line, stdlib-only, and malformed/minimal input contracts remain green.

## 8. Acceptance criteria

- All repositories using the updated skill treat low findings as non-blocking by default.
- No low finding is silently discarded: it remains in metadata and a human-readable advisory section.
- A low finding can be explicitly made blocking.
- A PR with only low findings no longer dispatches a fix agent or fails convergence.
- A PR with any blocking open finding still follows the existing fix/re-review loop.
- Old metadata remains parseable and follows the documented severity fallback.
- Existing `Status:` three-state and trigger phrase contracts remain intact.
- Tests and documentation agree on the same count and convergence semantics.
