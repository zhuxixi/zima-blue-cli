# Docs Automation (issue #228) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the documentation automation chain: English doc baseline, generated CLI reference, example-pack validation tests, and a CI drift gate (4 PRs).

**Architecture:** Human-maintained README tells the dual-path story (CLI constrained write / YAML direct write); `scripts/generate_cli_docs.py` deterministically renders `docs/cli-reference.md` from the real Typer command tree + `docs/cli-descriptions.yaml` (exact bidirectional coverage); example packs (`examples/webhook/`, `examples/sdd/`) are validated by pytest (structure + strict template render); CI lint job re-runs the generator and fails on drift. Mirrors the validated jfox #456 route (Phases 1/2A/3).

**Tech Stack:** Python 3.10+, Typer/Click (command-tree extraction via `typer.main.get_command`), PyYAML (descriptions catalog), pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-docs-automation-design.md` (authoritative; acceptance IDs A1–A10/U1 below refer to its §8 matrix).

## Global Constraints

- User-facing docs in English, per spec §3 list: `README.md`, `docs/guides/**`, `docs/cli-reference.md`, `docs/cli-descriptions.yaml`, `examples/*/README.md`. Chinese OK in `docs/{design,decisions,history,reports}/**` and workflow YAML prompt bodies.
- All work in the worktree `$WT` (= repo `.pi/worktrees/issue-228-docs-automation`); never touch main checkout.
- Style: black/ruff line-length 100; conventional commits (`docs:`, `feat:`, `test:`, `chore:`, `ci:`).
- Tests: `uv run pytest tests/ -m "not slow"` must stay green; coverage floor 60% unchanged (`--cov=zima` excludes scripts/, so new script code does not affect the floor, but unit tests still required).
- Each PR phase ends at a **push gate**: stop, wait for explicit user approval before push/PR/Zima CR. After each PR merges, sync the worktree branch to origin/main before starting the next phase (`git fetch origin && git reset --hard origin/main` inside worktree — branch history is squash-merged anyway).
- Single branch `issue-228-docs-automation` carries all four PR phases sequentially; each phase is pushed as a separate PR from the same branch after the previous one merged (branch is reset to main between phases).

---

## Phase PR 1 — Documentation baseline (spec §4)

### Task 1: Create `docs/guides/configuration.md` (absorbs API-INTERFACE §4 + §1.5)

**Files:**
- Create: `docs/guides/configuration.md`
- Reference source: `docs/API-INTERFACE.md` (§1.5 Env 密钥来源 table, §4 配置文件规范)

**Interfaces:**
- Produces: the canonical English config guide later linked from README (Task 3) and `examples/webhook/README.md` (Task 2).

- [ ] **Step 1: Write the guide** with exactly these sections (English, active voice, no Chinese):

```markdown
# Configuration Guide

## Config Root
- Table: `${ZIMA_HOME:-~/.zima}/configs/` is the ONLY directory the runtime reads; 7 entity subdirs (`agents/ workflows/ variables/ envs/ pmgs/ pjobs/ schedules/`), file = `<code>.yaml`.
- Note: YAML written elsewhere (e.g. project dir) is NOT auto-discovered.

## Two Ways to Configure
- **YAML path**: copy `examples/webhook/` (or `examples/sdd/`) into the config root, edit, validate, run. Best for agents, bulk setup, version control.
- **CLI path**: `zima quickstart` or `zima <kind> create --example` to bootstrap, fine-grained commands for small edits, `validate` as the shared quality gate.
- `--set-var`/`--set-env`/`--set-param` on `pjob run` are per-run overrides only; they never write back to YAML.

## Entity Reference (7 subsections)
For each of Agent / Workflow / Variable / Env / PMG / PJob / Schedule: one minimal annotated YAML example (reuse examples from `examples/webhook/` where possible; Agent example may take `zima/templates/examples.py` AGENT_EXAMPLE as base), plus a 1-line "what it's for".

## Secrets
- Env entity: `variables` (plain) vs `secrets` (reference only — never the value). Secret sources table (env / file / cmd / vault), each with a 3-line YAML snippet. Port the table content from API-INTERFACE §1.5 but re-verify field names against `zima/models/env.py` (`SecretDef`: name/source/key/path/command).
- `zima env get <code> --key <name> --resolve` resolves at read time.

## Validation Workflow
```
zima <kind> validate <code>          # entity-level
zima pjob validate <code> --check-render   # cross-refs + template render
zima pjob run <code> --dry-run       # full preview, no execution
```
Explain exit codes: non-zero on validation failure (CI-friendly).
```

- [ ] **Step 2: Verify** — no Chinese characters in the file (`grep -P '[\x{4e00}-\x{9fff}]' docs/guides/configuration.md` returns nothing); every YAML snippet in it parses (`uv run python -c "import yaml,sys; [yaml.safe_load(b) for b in []]"` visual check acceptable for prose examples, but the 7 entity examples must each round-trip: paste-check via a scratch `uv run python -c` loop loading each block from the guide is overkill — instead ensure they are copies of already-validated examples).
- [ ] **Step 3: Commit** — `git add docs/guides/configuration.md && git commit -m "docs(guides): add English configuration guide (absorbs API-INTERFACE config spec)"`

### Task 2: Translate `examples/webhook/README.md` to English; annotate stale design docs

**Files:**
- Modify: `examples/webhook/README.md` (translate, keep all commands/paths identical)
- Modify: `docs/design/CLI-INTERFACE.md` (header note only)
- Modify: `examples/sdd/` — check for README (none exists → no action)

**Interfaces:**
- Consumes: config-root wording from Task 1 (keep consistent: `${ZIMA_HOME:-~/.zima}/configs/`).

- [ ] **Step 1: Translate** webhook README fully to English. Preserve: the `cp -r examples/webhook/...` install block verbatim (it is the canonical install snippet), smee/webhook steps, multi-repo routing section, all flags. Update any link to API-INTERFACE → point to `../docs/guides/configuration.md` and README.
- [ ] **Step 2: Add stale-note** to `docs/design/CLI-INTERFACE.md` top: `> ⚠️ Historical design document, written pre-implementation. NOT a user-facing CLI reference — see README and docs/guides/configuration.md.` (one line, no other edits).
- [ ] **Step 3: Verify** — `grep -P '[\x{4e00}-\x{9fff}]' examples/webhook/README.md` → empty (except none expected); links resolve.
- [ ] **Step 4: Commit** — `git commit -am "docs(examples): translate webhook README to English; mark CLI-INTERFACE design doc as historical"`

### Task 3: Create `docs/architecture/data-and-runtime-reference.md`, delete `docs/API-INTERFACE.md`

**Files:**
- Create: `docs/architecture/data-and-runtime-reference.md`
- Delete: `docs/API-INTERFACE.md`
- Reference source: API-INTERFACE §2 数据模型接口, §3 核心运行接口, §5 执行流程 (Chinese content is kept — this is an internal architecture doc)

**Interfaces:**
- Consumes: migration map in spec §4.
- Produces: the only surviving content of API-INTERFACE (data models, runtime interfaces, execution flow), cited as `docs/architecture/data-and-runtime-reference.md`.

- [ ] **Step 1: Port content** — copy §2 (data models: AgentConfig/WorkflowConfig/VariableConfig/EnvConfig/PMGConfig/PJobConfig/结果模型), §3 (AgentRunner/KimiRunner/ConfigManager), §5 (PJob 执行流程/单次执行) into the new file. Header: `# Data & Runtime Reference（内部参考）` + provenance line `> Migrated from docs/API-INTERFACE.md §2/§3/§5 (2026-09-05); CLI command tables were superseded by the generated docs/cli-reference.md.` Keep Chinese prose as-is; fix any obviously-drifted signatures against current code ONLY where a table contradicts reality (e.g. add `pjob actions` to runtime flow if absent) — do not rewrite.
- [ ] **Step 2: Delete** `docs/API-INTERFACE.md` (`git rm docs/API-INTERFACE.md`). §1 CLI tables die here (superseded by upcoming cli-reference); §4/§1.5 already absorbed in Task 1; §6 version history dropped (CHANGELOG covers it).
- [ ] **Step 3: Verify** — `rg -l "API-INTERFACE" README.md docs/ examples/ zima/` returns only acceptable mentions (data-and-runtime-reference.md provenance line OK; README hits are fixed in Task 4; zero hits in code).
- [ ] **Step 4: Commit** — `git add -A docs/ && git commit -m "docs(architecture): split API-INTERFACE into config guide + runtime reference; remove stale CLI snapshot"`

### Task 4: Rewrite README configuration sections (A8, U1)

**Files:**
- Modify: `README.md` (Quick Start / Advanced Usage / CLI Commands / Documentation-tree sections)

**Interfaces:**
- Consumes: Task 1 guide (link target), Task 3 removal (must update links).

- [ ] **Step 1: Rewrite** with this structure:
  - **Configuration** (new section right after Architecture → Configuration Entities): dual-path narrative — two bullet blocks "YAML path" / "CLI path" (one sentence each on when to use), then the 7-entity directory table with config root, then a 5-line quick sample of the YAML path (`cp -r examples/webhook/... $ZIMA_HOME/configs/` → edit → `zima pjob validate <code> --check-render` → `zima pjob run <code>`).
  - **Quick Start**: keep install + `zima quickstart` wizard first (it remains the recommended human entry), then "Or start from an example pack" pointing at examples/webhook README.
  - **Advanced Usage: Composed Configuration**: retitle "Manual configuration (power users)"; keep CLI create flow as-is (it is the CLI path demo) but cap it with a note that YAML direct-write is equivalent and where it lives (link `docs/guides/configuration.md`).
  - **CLI Commands**: shrink to a one-screen overview (pjob run/status/ps/cancel/history, validate per entity, daemon, webhook-server, quickstart) + link "Full CLI reference: docs/cli-reference.md (generated)" — until PR 2 lands, link label says "being automated, see `zima --help`"; a follow-up commit in PR 2 flips it.
  - **Documentation** tree section: add guides/ entries, remove API-INTERFACE.md line, add architecture/data-and-runtime-reference.md.
  - Verify no link to deleted API-INTERFACE remains; no Chinese introduced.
- [ ] **Step 2: Verify** — `rg -n "API-INTERFACE" README.md` → empty; `grep -P '[\x{4e00}-\x{9fff}]' README.md` → empty; markdown headings ordered.
- [ ] **Step 3: Commit** — `git commit -am "docs(readme): dual-path configuration narrative; link new guides; drop API-INTERFACE references"`

### Task 5: ADR 006 (A9)

**Files:**
- Create: `docs/decisions/006-docs-architecture.md`

- [ ] **Step 1: Write the ADR** per repo ADR style (see 005 for format): status Accepted, date 2026-09-05, context = docs drift history (README single-path story, API-INTERFACE manual snapshot drifted: pjob actions / --failure-guard-off missing), decision = three-layer boundary (README human baseline / cli-reference generated / CI gate) + English-only user-facing docs (spec §3 table inline) + no new CLI write path (#196), alternatives rejected (generate README — narrative not derivable; keep manual snapshot — proven to drift; bot/AI first — layer ordering per docs-as-code), consequences (86-entry description catalog maintenance; generator dependency on click becomes direct).
- [ ] **Step 2: Commit** — `git commit -am "docs(adr): ADR 006 docs architecture — human baseline, generated reference, CI drift gate"`

### Task 6: PR 1 verification + push gate

- [ ] **Step 1:** `uv run pytest tests/ -m "not slow" -q` → green (docs-only change; guard against accidental code edits: `git diff --stat origin/main` shows only .md files).
- [ ] **Step 2:** `uv run ruff check zima/ tests/ && uv run black --check zima/ tests/ --line-length 100` → pass.
- [ ] **Step 3:** Cross-check spec §4 migration map — every API-INTERFACE section has an explicit destination (§1→dead/PR2, §1.5+§4→guide, §2/3/5→runtime reference, §6→dropped).
- [ ] **Step 4:** STOP — push gate: ask user for push/PR approval. PR body references A8/A9/U1 + spec. After merge: `git fetch origin && git reset --hard origin/main`.

---

## Phase PR 2 — CLI reference generator (spec §5)

### Task 7: Normalization + extraction core with unit tests (A1)

**Files:**
- Create: `scripts/generate_cli_docs.py`
- Create: `scripts/__init__.py` (empty)
- Test: `tests/unit/test_generate_cli_docs.py`

**Interfaces:**
- Produces: `NormalizedParameter(name, kind, syntax, type_name, required, default, choices, multiple, is_flag)` frozen dataclass; `NormalizedCommand(path, is_group, usage, parameters)`; `normalize_parameter(param: click.Parameter) -> NormalizedParameter`; `extract_commands(root: click.Command, root_name: str = "zima") -> tuple[NormalizedCommand, ...]` (recursive over root+groups+leaves, no callback invocation, sorted children).

- [ ] **Step 1: Write failing tests** building a synthetic click group:

```python
import click
from scripts.generate_cli_docs import extract_commands, normalize_parameter

def _build_tree():
    @click.group()
    def cli():
        """Root group."""

    @cli.command()
    @click.option("--model", "-m", default="kimi", help="Model name")
    @click.option("--yolo/--no-yolo", default=False)
    @click.option("--label", "-l", multiple=True)
    @click.argument("code")
    def create(model, yolo, label, code):
        """Create a thing."""
    return cli

def test_extract_includes_root_group_and_leaf():
    paths = [c.path for c in extract_commands(_build_tree(), "zima")]
    assert paths == ["zima", "zima create"]

def test_normalize_option_defaults_and_flag():
    cmd = _build_tree().commands["create"]
    by_name = {p.name: p for p in cmd.params}
    assert by_name["model"].default == "kimi"
    assert by_name["model"].syntax == "--model, -m"
    assert by_name["yolo"].is_flag and by_name["yolo"].syntax == "--yolo / --no-yolo"
    assert by_name["label"].multiple is True
    assert by_name["code"].kind == "argument" and by_name["code"].required

def test_extract_no_side_effects():
    # extraction never invokes callbacks: a raising callback proves it
    import click as _c

    @_c.group()
    def cli2():
        """Root.""

    @cli2.command()
    def boom2():
        raise RuntimeError("callback must not run")

    cmds = extract_commands(cli2, "zima")
    assert any(c.path == "zima boom2" for c in cmds)  # no exception raised
```

  - [ ] **Step 2: Run** `uv run pytest tests/unit/test_generate_cli_docs.py -v` → FAIL (module missing).
  - [ ] **Step 3: Implement** `NormalizedParameter`/`NormalizedCommand`/`normalize_parameter`/`extract_commands` — port from jfox `scripts/generate_docs.py` (`_format_value`, `_type_name`, `_metavar`, `_option_syntax`, `_command_usage`, `_walk_commands`), root_name `"zima"`, treat `None`/Sentinel defaults as MISSING "—".
  - [ ] **Step 4: Run** → PASS.
  - [ ] **Step 5: Commit** `feat(docs-gen): command-tree extraction core with unit tests (A1)`

### Task 8: Description catalog loader + bidirectional validation (A2)

**Files:**
- Modify: `scripts/generate_cli_docs.py`
- Test: `tests/unit/test_generate_cli_docs.py`

**Interfaces:**
- Produces: `load_descriptions(path: Path) -> dict[str, str]` (YAML `commands: {"<path>": {description: "..."}}`; rejects duplicate keys via unique-key SafeLoader, unknown fields, non-string/empty descriptions); `validate_descriptions(command_paths, descriptions)` raising `ValueError` with grouped `Missing ...` / `Unknown ...` lines on set inequality.

- [ ] **Step 1: Failing tests** — duplicate-key YAML (two identical keys in raw text), empty description, extra field (`summary:`), missing entry vs extracted paths, unknown extra entry. Use `tmp_path` fixtures.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (port jfox `_UniqueKeyLoader` + `load_descriptions` + `validate_descriptions`). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(docs-gen): descriptions catalog loader with exact bidirectional coverage validation (A2)`

### Task 9: Deterministic renderer + writer (A3)

**Files:**
- Modify: `scripts/generate_cli_docs.py`
- Test: `tests/unit/test_generate_cli_docs.py`

**Interfaces:**
- Produces: `render_reference(commands, descriptions) -> str` (GENERATED_MARKER header + per-command `## \`<path>\`` + description + usage block + parameter table `| Parameter | Syntax | Type | Required | Default | Choices | Multiple | Flag |`; sort key `path.split()`; table cells escape `|` and newlines); `write_reference(path, content)` (mkdir parents, `newline="\n"`, `.replace("\r\n", "\n")`).

- [ ] **Step 1: Failing tests**: render twice → identical strings; description containing `a|b` renders escaped `\|`; write to tmp_path then read → bytes end with `\n` and contain no `\r`.
- [ ] **Step 2/3/4:** FAIL → implement (port jfox `_markdown_cell`, `_parameter_table`, `render_reference`, `write_reference`; header text adapted: "Zima Blue CLI Reference", regenerate command `uv run python scripts/generate_cli_docs.py`). **Step 5: Commit** `feat(docs-gen): deterministic markdown renderer and LF-stable writer (A3)`

### Task 10: Full catalog + generated reference + CLI entry (A10 partial)

**Files:**
- Create: `docs/cli-descriptions.yaml` (~86 entries)
- Create: `docs/cli-reference.md` (generated)
- Modify: `scripts/generate_cli_docs.py` (add `generate_all(...)` + `main()` with argparse `--output/--descriptions`, repo-root sys.path bootstrap)
- Modify: `pyproject.toml` (add `click>=8.0` to dependencies)
- Modify: `.github/workflows/integration-test.yml` (ruff/black lines add `scripts/`)

- [ ] **Step 1: Dump paths** — `uv run python -c "from typer.main import get_command; from zima.cli import app; from scripts.generate_cli_docs import extract_commands; [print(c.path) for c in extract_commands(get_command(app))]"`
- [ ] **Step 2: Author descriptions** — one English line per path (use command docstrings as base; imperative mood, ≤100 chars). Group order: zima, agent, daemon, env, pjob (+actions), pmg, quickstart, schedule, variable, webhook-server, workflow.
- [ ] **Step 3: Generate** — `uv run python scripts/generate_cli_docs.py` → creates `docs/cli-reference.md`; rerun → `git diff` empty (determinism spot-check).
- [ ] **Step 4: Promote click** in pyproject dependencies (one line) + `uv lock` (`uv run uv lock` or `uv lock`).
- [ ] **Step 5: CI lint scope** — change workflow ruff/black commands to `zima/ tests/ scripts/` (both occurrences if two steps). Run locally: `uv run ruff check scripts/ && uv run black --check scripts/ --line-length 100` → fix any violations in the script.
- [ ] **Step 6: Commit** `feat(docs-gen): full command catalog, generated cli-reference.md, click as direct dep, scripts in lint scope`

### Task 11: Real-app smoke test + lint-imports proof (A10)

**Files:**
- Test: `tests/integration/test_generate_cli_docs_smoke.py`

- [ ] **Step 1: Write test**:

```python
from typer.main import get_command
from zima.cli import app
from scripts.generate_cli_docs import extract_commands, load_descriptions, validate_descriptions
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

def test_real_tree_key_commands_present():
    paths = {c.path for c in extract_commands(get_command(app))}
    for key in ("zima pjob actions add", "zima pjob run", "zima daemon start",
                "zima webhook-server", "zima quickstart"):
        assert key in paths, key

def test_catalog_matches_extracted_tree_exactly():
    paths = {c.path for c in extract_commands(get_command(app))}
    catalog = load_descriptions(REPO / "docs" / "cli-descriptions.yaml")
    validate_descriptions(paths, catalog)  # raises on any mismatch
```

  - [ ] **Step 2: Run** `uv run pytest tests/integration/test_generate_cli_docs_smoke.py -v` → PASS.
  - [ ] **Step 3:** `uv run lint-imports` → PASS (scripts/ outside contracts; record output in PR body).
  - [ ] **Step 4: Full check** `uv run pytest tests/ -m "not slow" -q` → green.
  - [ ] **Step 5: Commit** `test(docs-gen): real-app smoke — key commands, exact catalog coverage, lint-imports (A10)`

### Task 12: PR 2 verification + push gate

- [ ] **Step 1:** `uv run python scripts/generate_cli_docs.py && git status --short` → clean (generated file committed, no drift).
- [ ] **Step 2:** README link flip: the "Full CLI reference" link from Task 4 now points to `docs/cli-reference.md` (edit + commit `docs(readme): link generated cli-reference`).
- [ ] **Step 3:** STOP — push gate. After merge: reset branch to origin/main.

---

## Phase PR 3 — Example-pack validation tests (spec §6)

### Task 13: Structure validation for both packs (A6)

**Files:**
- Test: `tests/integration/test_examples_validate.py`

**Interfaces:**
- Produces: `_install_scene(scene: str, zima_home: Path) -> None` (copies `examples/<scene>/{agents,workflows,variables,envs,pjobs}` — only dirs that exist — into `<zima_home>/configs/`); `_validate_entity(kind: str, code: str, manager: ConfigManager) -> list[str]` (load + `<Model>.from_dict` + `.validate()`); module-level `MODEL_MAP = {"agent": AgentConfig, "workflow": WorkflowConfig, "variable": VariableConfig, "env": EnvConfig, "pjob": PJobConfig}`.

- [ ] **Step 1: Write failing tests** (autouse `isolated_zima_home` fixture per test):

```python
SCENES = {
    "webhook": {"agent": 2, "workflow": 2, "variable": 1, "env": 1, "pjob": 2},
    "sdd": {"agent": 4, "workflow": 6, "env": 1, "pjob": 12},
}

@pytest.mark.parametrize("scene", list(SCENES))
def test_scene_all_entities_validate(scene, isolated_zima_home):
    _install_scene(scene, isolated_zima_home)
    manager = ConfigManager()
    errors = []
    for kind in SCENES[scene]:
        for code in manager.list_config_codes(kind):
            errors += [f"{kind}/{code}: {e}" for e in _validate_entity(kind, code, manager)]
    assert not errors, errors
```

  - [ ] **Step 2: Run** → FAIL (helpers missing). **Step 3: Implement** helpers (ConfigManager import inside test module; kinds map to `<kind>s` dirs already handled by manager).
  - [ ] **Step 4: Run** `uv run pytest tests/integration/test_examples_validate.py -v` → PASS (verified feasible in review: both packs pass entity validate today).
  - [ ] **Step 5: Commit** `test(examples): validate webhook+sdd example packs structure in CI (A6)`

### Task 14: Strict template render for example PJobs (A7)

**Files:**
- Test: `tests/integration/test_examples_validate.py` (extend)

**Interfaces:**
- Produces: `_strict_render_check(pjob_code: str, manager: ConfigManager) -> None` (raises AssertionError on failure): load PJobConfig → referenced WorkflowConfig → `jinja2.meta.find_undeclared_variables` on parsed template → sentinel dict `{name: f"XTEST_{name}" for ...}` → render with `Environment(undefined=StrictUndefined)` → assert no exception AND every sentinel string appears in output.

- [ ] **Step 1: Failing test**:

```python
@pytest.mark.parametrize("scene", list(SCENES))
def test_scene_pjobs_strict_render(scene, isolated_zima_home):
    _install_scene(scene, isolated_zima_home)
    manager = ConfigManager()
    for code in manager.list_config_codes("pjob"):
        _strict_render_check(code, manager)  # asserts internally
```

  - [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (import `from jinja2 import Environment; from jinja2.meta import find_undeclared_variables; from jinja2 import StrictUndefined`; env settings match template_renderer: trim_blocks/lstrip_blocks/keep_trailing_newline; plain-format workflows skip render check). **Step 4: Run** → PASS (review verified webhook templates use repo/pr/head_sha which sentinel covers; sdd likewise).
  - [ ] **Step 5: Full suite** `uv run pytest tests/ -m "not slow" -q` → green.
  - [ ] **Step 6: Commit** `test(examples): strict-render every example PJob template with sentinels (A7)`

### Task 15: PR 3 verification + push gate

- [ ] **Step 1:** `uv run pytest tests/integration/test_examples_validate.py -v` full file green; `git diff --stat origin/main` shows only the new test file.
- [ ] **Step 2:** STOP — push gate. After merge: reset branch to origin/main.

---

## Phase PR 4 — CI drift gate (spec §7)

### Task 16: Gate step + path filters (A4)

**Files:**
- Modify: `.github/workflows/integration-test.yml`

- [ ] **Step 1: Add step** after `Run import-linter` in lint job (exact shell from spec §7 — generator run, untracked check limited to `docs/cli-reference.md`, tracked `git diff --exit-code`, `::error::` annotation with regenerate command, `exit 1`).
- [ ] **Step 2: Add paths** to BOTH push and pull_request triggers: `'scripts/**'`, `'docs/cli-descriptions.yaml'`, `'**/*.md'`, `'examples/**'`.
- [ ] **Step 3: Local sanity** — `uv run python scripts/generate_cli_docs.py && git status --short` → clean (gate would pass on HEAD).
- [ ] **Step 4: Commit** `ci(docs): drift gate for generated cli-reference + path filters (A4)`

### Task 17: Gate logic red/green self-proof (A5) + final gate

- [ ] **Step 1: Red** — temporarily add a fake option to one command (e.g. `--zzz-drift-test` on `agent list` in worktree only), run `uv run python scripts/generate_cli_docs.py`, then `git diff --exit-code` → capture non-zero exit + diff output (this is exactly what CI gate runs); capture in PR body. Revert the fake option and regenerate (green: diff clean).
- [ ] **Step 2: Full local suite** — `uv run pytest tests/ -m "not slow" -q` + `uv run ruff check zima/ tests/ scripts/` + `uv run black --check zima/ tests/ scripts/ --line-length 100` + `uv run lint-imports` → all pass.
- [ ] **Step 3: Commit** evidence text into PR body draft (not a commit).
- [ ] **Step 4: STOP — final push gate.** After merge: post-merge cleanup per skill Step 10 (worktree remove, branch delete) after ALL four PRs merged.

---

## Acceptance traceability summary

| PR | Tasks | Acceptance IDs |
|----|-------|----------------|
| PR 1 | 1–6 | A8, A9, U1 |
| PR 2 | 7–12 | A1, A2, A3, A10 |
| PR 3 | 13–15 | A6, A7 |
| PR 4 | 16–17 | A4, A5 |
