# CC CR Skill Sync Implementation Plan (Issue #221)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync the stale Claude Code plugin skill `plugins/pr-automation/skills/github-code-review-batch/` to the current pi version (blocking/advisory semantics, `<zima-review>` XML trailer, #174 changed-file filtering), bump plugin + marketplace versions 0.5.1 → 0.6.0, and add a minimal cc-side contract test.

**Architecture:** `cc scripts ← pi scripts` byte copy for 4 harness-neutral files + sed-semantic literal substitution for `build_review_body.py` / `parse_metadata.py`; prose (SKILL.md + 4 references) is manually adapted per the spec's delete/flip/replace/keep four-class inventory. One new test file `tests/unit/test_cr_batch_plugin_contracts.py` black-boxes the cc scripts (subprocess, same style as existing contract tests) and statically asserts cc SKILL.md external contracts. pi tree is read-only throughout.

**Tech Stack:** Python stdlib scripts (portability contract: no third-party deps), Markdown skill docs (Chinese), pytest (English code/docstrings), `rg` static checks.

**Spec:** `docs/superpowers/specs/2026-09-04-cc-cr-skill-sync-design.md`

## Global Constraints

- **pi tree is read-only**: nothing under `pi/` may be modified (A2).
- Trigger phrases (`batch review pr`, `review pr batch`, `scheduled review pr`), `Status:` three-state (`NEEDS_FIX|PASS|NO_NEW_COMMITS`), `<zima-review>` XML trailer are external contracts — must survive cc SKILL.md adaptation verbatim.
- The cc metadata contract is `cc-cr-meta` + `Generated with Claude Code`; substitution must be exhaustive across every literal occurrence (sed semantics), including docstrings and regexes.
- cc prose direction-flip points (flow.md Step 0 detection criteria L19–26, suppress-path L308, identity paragraph) must not be missed — the existing cc `flow.md` L18–24 wording is the canonical sample for Step 0.
- Legal exemptions from static greps: cross-bot triple listings ("pi 版包含… cc 版包含…") and the identity paragraph's ignore-list mention of `pi-cr-meta` are legitimate content (spec §2).
- Skill scripts: Python stdlib only; skill docs in Chinese; test code/docstrings in English.
- `black --line-length 100` + `ruff check` must pass on touched Python files; commit format conventional commits.
- Do not `git add -A`; stage files explicitly. No `__pycache__` in commits.
- All paths below are relative to worktree root; session operates via absolute path `WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync`.

---

### Task 1: scripts sync (cc ← pi) — 7 files

**Spec acceptance IDs:** A4, feeds A1

**Files:**
- Copy: `pi/github-code-review-batch/scripts/{issue_policy,render_status_report,compress_diff,run_tool_layer}.py` → `plugins/pr-automation/skills/github-code-review-batch/scripts/` (byte copy, zero pi literals — verified in spec §1)
- Copy + substitute: `build_review_body.py`, `parse_metadata.py` (rules: `pi-cr-meta`→`cc-cr-meta`, `Generated with pi-coding-agent`→`Generated with Claude Code`, `PI_MARKER`→`CC_MARKER`; file-wide sed semantics)
- Untouched: `apply_suppressions.py`, `match_committer_response.py` (already identical)

- [ ] **Step 1: Copy the 4 harness-neutral scripts byte-for-byte**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
for f in issue_policy.py render_status_report.py compress_diff.py run_tool_layer.py; do
  cp $WT/pi/github-code-review-batch/scripts/$f $WT/plugins/pr-automation/skills/github-code-review-batch/scripts/$f
done
```

- [ ] **Step 2: Copy + substitute the 2 meta-carrying scripts**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
cd $WT
cp pi/github-code-review-batch/scripts/build_review_body.py plugins/pr-automation/skills/github-code-review-batch/scripts/build_review_body.py
cp pi/github-code-review-batch/scripts/parse_metadata.py plugins/pr-automation/skills/github-code-review-batch/scripts/parse_metadata.py
cd plugins/pr-automation/skills/github-code-review-batch/scripts
sed -i 's/pi-cr-meta/cc-cr-meta/g; s/Generated with pi-coding-agent/Generated with Claude Code/g; s/PI_MARKER/CC_MARKER/g' build_review_body.py parse_metadata.py
```

- [ ] **Step 3: Verify substitution exhaustiveness (A4)**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
rg -n "pi-cr-meta|pi-coding-agent|PI_MARKER" $WT/plugins/pr-automation/skills/*/scripts/*.py
# Expected: zero hits
```

- [ ] **Step 4: Sanity — every substituted file still parses and `build_review_body.py` finds its `issue_policy` import**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
cd $WT/plugins/pr-automation/skills/github-code-review-batch/scripts
for f in *.py; do python3 -m py_compile "$f" && echo "$f OK"; done
python3 -c "
import importlib.util, sys
sys.path.insert(0, '.')
spec = importlib.util.spec_from_file_location('brb', 'build_review_body.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('build_review_body imports OK')
"
```

- [ ] **Step 5: Verify byte-identity of the 4 neutral copies against pi source**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
for f in issue_policy.py render_status_report.py compress_diff.py run_tool_layer.py; do
  cmp $WT/pi/github-code-review-batch/scripts/$f $WT/plugins/pr-automation/skills/github-code-review-batch/scripts/$f && echo "$f identical"
done
```

- [ ] **Step 6: Commit**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
git -C $WT add plugins/pr-automation/skills/github-code-review-batch/scripts/
git -C $WT commit -m "feat(pr-automation): sync cr-batch scripts from pi version (#174 #119 #176 #183)"
```

---

### Task 2: SKILL.md adaptation (identity flip + dispatch mechanism + literal substitution)

**Spec acceptance IDs:** A5, feeds A1 (static contract assertions)

**Files:**
- Modify: `plugins/pr-automation/skills/github-code-review-batch/SKILL.md`

Use pi `pi/github-code-review-batch/SKILL.md` as base, then adapt per spec §2 four-class inventory:

- **Delete**: `subagent` tool / `workflowScript` / `runs.all` dispatch prose → rewrite as Claude Code `Agent`/Task parallel dispatch (current cc SKILL.md L81-82 wording is the canonical style for this: "**`Agent` 启动所有审查/验证 sub-agent**"); remove any pi-subagents resolution chain content if carried over.
- **Flip**: identity paragraph — pi's "历史 cc 版评论严格忽略" becomes cc's "历史 `pi-cr-meta` 与 `kimi-cr-meta` 评论严格忽略".
- **Replace**: `pi-cr-meta`→`cc-cr-meta`, `pi-coding-agent`→`Claude Code` throughout (INCLUDING the round-count/status prose that references the marker), keeping exemptions.
- **Keep verbatim**: three trigger phrases + their external-contract warning block; `Status:` three-state + `Verdict:` semantics; `<zima-review>` XML trailer section; blocking/advisory normalization rules; 20K/12K diff budget numbers; webhook-server scheduler wording (pi version mentions "zima daemon 或 webhook-server" — cc version may keep this; both schedulers exist).

- [ ] **Step 1: Draft the adapted cc SKILL.md** (base = pi SKILL.md, apply the four-class rules above)
- [ ] **Step 2: Static check (A5, SKILL.md part)**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
rg -n "\.pi/|pi-subagents|modelScope|pi-coding-agent|workflowScript|runs\.all|pi-cr-meta" \
  $WT/plugins/pr-automation/skills/github-code-review-batch/SKILL.md
# Expected: zero hits (the identity paragraph must phrase the ignore rule as
# "pi-cr-meta 与 kimi-cr-meta 评论严格忽略" — wait: this phrase CONTAINS pi-cr-meta.
# Exemption: if the identity/ignore-list line is the ONLY hit, it is legal content
# (spec §2 豁免); reword to 「历史 pi 版（pi-cr-meta）与 kimi 版（kimi-cr-meta）评论严格忽略」
# so the exemption is a single explicit line, or drop the literal and keep it legal.
```

- [ ] **Step 3: Contract preservation check** — the three trigger phrases, three-state enum, `<zima-review>` block, and `gh`-CLI instructions all present verbatim:

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
for p in "batch review pr" "review pr batch" "scheduled review pr" "NEEDS_FIX" "NO_NEW_COMMITS" "zima-review" "gh pr"; do
  rg -q "$p" $WT/plugins/pr-automation/skills/github-code-review-batch/SKILL.md && echo "OK: $p" || echo "MISSING: $p"
done
```

- [ ] **Step 4: Commit**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
git -C $WT add plugins/pr-automation/skills/github-code-review-batch/SKILL.md
git -C $WT commit -m "docs(pr-automation): adapt cr-batch SKILL.md to current contract (blocking/advisory + XML trailer)"
```

---

### Task 3: references adaptation (4 files; edge-cases.md untouched)

**Spec acceptance IDs:** A5

**Files:**
- Modify: `plugins/pr-automation/skills/github-code-review-batch/references/{flow,delta-review,output-examples,subagent-prompts}.md`
- Untouched: `references/edge-cases.md` (both versions identical, zero pi residue — spec §2)

- [ ] **Step 1: flow.md** — base = pi flow.md, apply:
  - Flip Step 0 detection criteria (pi L19–26) to cc semantics; canonical sample = current cc flow.md L18–24 wording
  - Delete `workflowScript`/`runs.all` dispatch block (pi L202–214) → rewrite with `Agent`/Task parallel dispatch prose
  - Delete modelScope / `subagent({action:"models"})` / `.pi/settings.json` segment (pi L216–223)
  - Flip suppress-path sentence (pi L308): cc primary `.claude/cr-suppressions.json`, `.pi/` legacy-compatible
  - Replace `pi-cr-meta`→`cc-cr-meta` / `pi-coding-agent`→`Claude Code` at example sites (L412 metadata block, L454 signature line), preserving the cross-bot triple listing at L42 (legal exemption)
- [ ] **Step 2: delta-review.md** — base = pi version; replace marker literals; keep #187 resolution-verification logic (pi-only improvement to carry over); adapt `bash`→`Bash` tool naming
- [ ] **Step 3: output-examples.md** — base = pi version; replace example metadata headers `<!-- pi-cr-meta` (6 sites) and `🤖 Generated with pi-coding-agent` lines (6 sites); keep the blocking/advisory Round-1 example structure
- [ ] **Step 4: subagent-prompts.md** — base = pi version; DELETE the pi dispatch preamble (pi L1–3: `pi 派发方式` block + `workflowScript` mention); replace severity/blocking section keeping #119/#183 semantics but dropping pi-specific resolution-chain prose; keep #187 delta-reviewer resolution-verification bullet; keep all prompt template bodies (harness-neutral), only adapting tool names inside templates if any (`bash`→`Bash`)
- [ ] **Step 5: Static check (A5, references part)**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
rg -n "\.pi/|pi-subagents|modelScope|pi-coding-agent|workflowScript|runs\.all|pi-cr-meta" \
  $WT/plugins/pr-automation/skills/github-code-review-batch/references/
# Expected: hits ONLY on the legal cross-bot listing line (flow.md L42-style) — review each hit
```

- [ ] **Step 6: Commit**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
git -C $WT add plugins/pr-automation/skills/github-code-review-batch/references/
git -C $WT commit -m "docs(pr-automation): adapt cr-batch references to cc harness (flip detection direction, drop pi dispatch prose)"
```

---

### Task 4: cc-side contract test

**Spec acceptance IDs:** A1

**Files:**
- Create: `tests/unit/test_cr_batch_plugin_contracts.py`

**Interfaces:**
- Consumes: cc plugin scripts at `plugins/pr-automation/skills/github-code-review-batch/scripts/` as subprocess black boxes (same pattern as `tests/unit/test_cr_batch_contracts.py::_run/_run_json`); cc SKILL.md text.
- Produces: `TestCcPluginContracts` covering: (1) build→parse round-trip with `cc-cr-meta` marker asserted; (2) SKILL.md static contract assertions — three trigger phrases, `NEEDS_FIX|PASS|NO_NEW_COMMITS`, `<zima-review>`, `gh pr` instructions; (3) `run_tool_layer.py --files` smoke (exit 0 + valid JSON on minimal input).

- [ ] **Step 1: Write the test file** — scaffold: `_PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "pr-automation" / "skills" / "github-code-review-batch"`, `_SCRIPTS`, `_run`/`_run_json` helpers mirroring the pi contract test's stdlib-only subprocess pattern. Minimal metadata payload for round-trip: one open issue, `round: 1`, `head_sha: "a"*40`; assert parsed-back dict equals normalized payload and that the emitted body contains `<!-- cc-cr-meta` and `Generated with Claude Code`.
- [ ] **Step 2: Run the new test (must pass)**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
cd $WT && uv run pytest tests/unit/test_cr_batch_plugin_contracts.py -q
```

- [ ] **Step 3: Lint/format gate**

```bash
cd $WT && uv run ruff check tests/unit/test_cr_batch_plugin_contracts.py && uv run black tests/unit/test_cr_batch_plugin_contracts.py --line-length 100
```

- [ ] **Step 4: Commit**

```bash
git -C $WT add tests/unit/test_cr_batch_plugin_contracts.py
git -C $WT commit -m "test(pr-automation): add cc plugin contract tests (round-trip + SKILL.md contracts + --files smoke)"
```

---

### Task 5: version bump + README + full gate

**Spec acceptance IDs:** A3, A2, plus release-note obligation

**Files:**
- Modify: `plugins/pr-automation/.claude-plugin/plugin.json` (`0.5.1` → `0.6.0`)
- Modify: `.claude-plugin/marketplace.json` (`0.5.1` → `0.6.0`)
- Modify: `plugins/pr-automation/README.md` — (a) Skills table: add blocking/advisory + XML trailer + #174 files filtering to the capability wording; (b) "Relationship to zima daemon" paragraph: ignore list becomes `pi-cr-meta` + `kimi-cr-meta`; (c) add a short release-note callout: advisory-only rounds now report `PASS` and no longer trigger fix (scheduler-visible boundary change for the 8 fallback PJob configs)

- [ ] **Step 1: Bump both version fields**

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-221-cc-cr-skill-sync
cd $WT
sed -i 's/"version": "0.5.1"/"version": "0.6.0"/' plugins/pr-automation/.claude-plugin/plugin.json .claude-plugin/marketplace.json
```

- [ ] **Step 2: Verify (A3)**

```bash
grep -h '"version"' $WT/plugins/pr-automation/.claude-plugin/plugin.json $WT/.claude-plugin/marketplace.json
# Expected: both "version": "0.6.0"
```

- [ ] **Step 3: README edits** (three sites per Files list above; keep English README prose)
- [ ] **Step 4: Full unit gate (A2 — pi untouched regression)**

```bash
cd $WT && uv run pytest tests/unit/ -q
# Expected: all green, including the 6 existing test_cr_batch_* files and the new plugin test
```

- [ ] **Step 5: Commit**

```bash
git -C $WT add plugins/pr-automation/.claude-plugin/plugin.json .claude-plugin/marketplace.json plugins/pr-automation/README.md
git -C $WT commit -m "chore(pr-automation): bump to 0.6.0 + README alignment notes"
```

---

## Acceptance mapping (spec → plan)

| Spec ID | Covered by |
|---|---|
| A1 (round-trip + SKILL.md contracts + --files smoke) | Task 4 |
| A2 (pi regression) | Task 5 Step 4 |
| A3 (version bump) | Task 5 Steps 1–2 |
| A4 (scripts zero pi literals) | Task 1 Step 3 |
| A5 (prose zero pi-env residue) | Task 2 Step 2, Task 3 Step 5 |
| U1 (real PR cc CR) | Post-merge manual task — see below |

## Post-implementation manual verification (U1, pending)

After merge: update the installed plugin (`/plugin marketplace update zima-blue` or reinstall), run one real PR through the cc fallback PJob path, verify: PR comment carries `cc-cr-meta` + status report, job stdout contains `<zima-review>`, postExec label transition fires. Record observation on issue #221. This item stays `pending` until executed by the user.
