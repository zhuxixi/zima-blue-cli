"""PJob Executor - executes PJob with all configurations."""

from __future__ import annotations

import copy
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from zima.config.manager import ConfigManager
from zima.execution.actions_runner import (
    ActionsRunner,
    SkipAction,
    normalize_pr_number,
    pr_number_ok,
    repo_ok,
)
from zima.execution.failure_guard import (
    FailureGuard,
    GuardStateError,
    classify_execution_result,
    normalize_target,
)
from zima.execution.history import ExecutionHistory
from zima.models.config_bundle import ConfigBundle
from zima.models.pjob import Overrides, PJobConfig
from zima.review.parser import ReviewParser
from zima.utils import generate_timestamp, get_zima_home

# Well-formed owner/name (same charset contract as zima.webhook.payload's
# repo allow-list). Scan-provided repo values must match before they may
# drive rendering or postExec gh targets (#158).

# Free-text scan values (pr_title/pr_url/pr_diff) entering the agent env /
# templates are capped to keep E2BIG and render blowups off the table
# (#158 R21). Diff text is the largest legitimate payload — 1 MiB headroom.
_DISCOVERED_TEXT_MAX = 1_048_576

# Byte-based cap for the same free-text values. The kernel limits a single
# argv/envp string to MAX_ARG_STRLEN = 131072 BYTES (incl. the "KEY=" prefix
# and trailing NUL), so a char-based cap cannot bound byte length for CJK
# text (1 char = 3 bytes UTF-8) — #158's 1 MiB char cap never actually
# prevented E2BIG (#201). Task 2 rewires the truncation loop to this.
_DISCOVERED_TEXT_MAX_BYTES = 100_000


def truncate_utf8_bytes(text: str, limit: int) -> str:
    """Truncate text to at most ``limit`` UTF-8 bytes without splitting a
    codepoint; the partial tail is dropped via errors="ignore" (#201).

    The kernel counts envp strings in bytes, so env-injected free text must
    be capped in bytes, not characters.
    """
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit}")
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


class ExecutionStatus(Enum):
    """Execution status enum."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class ExecutionResult:
    """
    Result of PJob execution.

    Attributes:
        pjob_code: PJob code
        status: Execution status
        returncode: Process return code
        stdout: Standard output
        stderr: Standard error
        error_detail: Detailed error information (full Python traceback for failures)
        command: Executed command
        env: Environment variables used
        work_dir: Working directory
        started_at: Start timestamp
        finished_at: Finish timestamp
        execution_id: Unique execution ID
        temp_dir: Temporary directory (if kept)
        action_errors: Post-exec action failure messages
        scan_pr_result: Scan PR result data (repo, pr_number, etc.)
    """

    pjob_code: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    error_detail: str = ""  # Full Python traceback for failures
    command: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)
    work_dir: str = ""
    started_at: str = ""
    finished_at: str = ""
    execution_id: str = ""
    temp_dir: Optional[Path] = None
    prompt_file: Optional[Path] = None  # Rendered workflow prompt file
    prompt_content: str = ""  # Rendered workflow content (kept for dry-run)
    pid: Optional[int] = None  # 执行的进程 PID
    action_errors: list[str] = field(default_factory=list)
    scan_pr_result: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pjob_code": self.pjob_code,
            "status": self.status.value,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_detail": self.error_detail,
            "command": self.command,
            "env": {k: v for k, v in self.env.items() if not k.lower().endswith("key")},
            "work_dir": self.work_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "execution_id": self.execution_id,
            "temp_dir": str(self.temp_dir) if self.temp_dir else None,
            "pid": self.pid,
            "action_errors": self.action_errors,
            **({"scan_pr_result": self.scan_pr_result} if self.scan_pr_result is not None else {}),
        }

    @property
    def duration_seconds(self) -> float:
        """Get execution duration in seconds."""
        if not self.started_at or not self.finished_at:
            return 0.0
        try:
            start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.finished_at.replace("Z", "+00:00"))
            return (end - start).total_seconds()
        except Exception:
            return 0.0


def _friendly_error(exc: Exception) -> str:
    """Convert an exception to a user-friendly error message."""
    msg = str(exc)

    # Known error patterns with friendly messages
    if isinstance(exc, FileNotFoundError):
        return f"File not found: {msg}"
    if isinstance(exc, PermissionError):
        return f"Permission denied: {msg}"
    if isinstance(exc, ValueError):
        return f"Configuration error: {msg}"
    if isinstance(exc, KeyError):
        return f"Missing required field: {msg}"
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return f"Connection error: {msg}"
    if isinstance(exc, AttributeError):
        return f"Invalid configuration: {msg}"

    # Default: error type + message
    return f"{type(exc).__name__}: {msg}"


class PJobExecutor:
    """
    Executor for PJob.

    Handles the complete execution flow:
    1. Load PJob configuration
    2. Resolve config bundle
    3. Create temp directory
    4. Resolve environment variables
    5. Execute preExec actions
    6. Render workflow template
    7. Build agent command
    8. Dry run check
    9. Execute pre-hooks
    10. Run main command
    11. Execute post-hooks
    12. Handle output and cleanup
    13. Execute postExec actions
    """

    def __init__(self):
        """Initialize executor."""
        self.config_manager = ConfigManager()
        self._current_process: Optional[subprocess.Popen] = None
        self._history = ExecutionHistory()
        self._actions_runner = ActionsRunner(
            history=self._history,
            pjob_code=None,
        )

    def execute(
        self,
        pjob_code: str,
        overrides: Optional[Overrides] = None,
        dry_run: bool = False,
        keep_temp: bool = False,
        dedup_off: bool = False,
        execution_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute a PJob.

        Args:
            pjob_code: PJob code to execute
            overrides: Runtime overrides (optional)
            dry_run: If True, only show what would be executed
            keep_temp: Keep temporary files after execution
            dedup_off: If True, skip the duplicate-execution dedup guard.
            execution_id: Optional explicit execution ID; falls back to a fresh UUID.

        Returns:
            ExecutionResult with details
        """
        execution_id = execution_id or str(uuid.uuid4())[:8]
        result = ExecutionResult(
            pjob_code=pjob_code,
            execution_id=execution_id,
            started_at=generate_timestamp(),
        )
        self._actions_runner._pjob_code = pjob_code
        temp_dir: Optional[Path] = None
        # Runtime-only overrides (execute() argument): the pinned-PR
        # short-circuit must trust these alone (#158 R3).
        runtime_overrides = overrides

        try:
            # 1. Load PJob configuration
            pjob = self._load_pjob(pjob_code)

            # 2. Resolve config bundle
            bundle = self._resolve_bundle(pjob, overrides)
            result.work_dir = bundle.work_dir

            # 3. Create temp directory
            temp_dir = self._create_temp_dir(pjob_code, execution_id)
            result.temp_dir = temp_dir

            # 4. Resolve environment variables (moved up for preExec)
            env_vars = self._resolve_env(bundle)
            result.env = env_vars

            # 5. Execute preExec actions (before rendering so dynamic vars are available)
            # Skip preExec in dry_run to avoid side effects (e.g. GitHub API calls)
            if pjob.spec.actions and pjob.spec.actions.pre_exec and not dry_run:
                try:
                    # Merge variable config values into env for {{var}} substitution
                    pre_env = env_vars.copy()
                    for k, v in bundle.get_variable_values().items():
                        if v is not None:
                            pre_env.setdefault(k, str(v))
                    # Runtime-injected variable values only (--set-var /
                    # webhook spawn): the pinned-PR short-circuit must trust
                    # these alone — never static Variable config values nor
                    # PJob YAML spec.overrides (#158 R3: build from the
                    # execute() runtime argument, not the merged bundle.overrides).
                    pin_env = {
                        k: str(v)
                        for k, v in (runtime_overrides or Overrides()).variable_values.items()
                        if v is not None
                    }
                    dynamic_vars = self._actions_runner.run_pre(
                        pjob.spec.actions,
                        pre_env,
                        workdir=bundle.work_dir,
                        pin_env=pin_env,
                    )
                    # A stale/empty pr value — wherever it lives (static
                    # spec.overrides variableValues/envVars, the runtime
                    # overrides object, the resolved env_vars, or the Variable
                    # config values it was deep-merged into) — must not pin
                    # rendering + postExec to a different (or empty) PR than
                    # the one actually scanned (#158 R6/R7). Values are
                    # REWRITTEN to the scanned number (not popped) so the
                    # {{pr}} alias channel also renders it. The caller's
                    # Overrides object is never mutated: we rebind copies.
                    # Scan-path execution with a non-empty runtime pr pin is
                    # impossible (the pinned branch short-circuits), so any
                    # differing value here is static/legacy.
                    _scan_valid = True  # no pr_number -> nothing to validate
                    if "pr_number" in dynamic_vars:
                        _scanned_pr = normalize_pr_number(dynamic_vars["pr_number"])
                        # Length limits are part of validity: an overlong value
                        # is treated as invalid and discarded entirely, so the
                        # persisted copy can never diverge (truncate) from the
                        # in-memory value flowing through holders (#158 R14)
                        _scan_valid = pr_number_ok(_scanned_pr)
                        if not _scan_valid:
                            # Third-party providers (entry-point extension) may
                            # return PR dicts with missing/non-numeric numbers.
                            # Single invariant: an invalid scan is discarded
                            # ENTIRELY — every scan-discovered key (pr aliases,
                            # repo, the pr_* family; prefix-based) is dropped so
                            # merge-back / injection / postExec all keep
                            # configured values, and NOTHING is persisted: no
                            # skip-set registration, no history payload. A
                            # persistently-broken provider is therefore retried
                            # each cycle — accepted as the safer side of the
                            # trade (retrying a broken scan can never act on a
                            # wrong PR, unlike any partial trust of its
                            # output) (#158 R13 simplification).
                            print(
                                f"Warning: scan returned invalid pr_number "
                                f"(non-numeric or overlong; len={len(_scanned_pr)}); "
                                f"discarding the scan result entirely (#158)"
                            )
                            dynamic_vars = {
                                k: v
                                for k, v in dynamic_vars.items()
                                if k not in ("pr_number", "pr", "repo") and not k.startswith("pr_")
                            }
                        else:
                            _scanned_repo = str(dynamic_vars.get("repo") or "").strip()
                            if _scanned_repo and not repo_ok(_scanned_repo):
                                # Same trust boundary as the finally net: a
                                # malformed repo never enters holders — it is
                                # dropped from dynamic_vars entirely below
                                # (#158 R12/R13)
                                _scanned_repo = ""
                            bundle.overrides = copy.copy(bundle.overrides)
                            bundle.overrides.variable_values = dict(
                                bundle.overrides.variable_values
                            )
                            bundle.overrides.env_vars = dict(bundle.overrides.env_vars)
                            if bundle.variable:
                                bundle.variable = copy.copy(bundle.variable)
                                bundle.variable.values = dict(bundle.variable.values)
                            _changed: set = set()
                            for _holder in (
                                bundle.overrides.variable_values,
                                bundle.overrides.env_vars,
                                env_vars,
                            ):
                                for _k in ("pr_number", "pr"):
                                    if _k not in _holder:
                                        continue
                                    _raw = str(_holder[_k])
                                    if _raw == _scanned_pr:
                                        continue  # already in canonical form
                                    _holder[_k] = _scanned_pr
                                    # Warn only when the normalized value points
                                    # at a DIFFERENT PR; same-PR format variants
                                    # ('#123', padded) rewrite silently (#158 R8)
                                    if normalize_pr_number(_raw) != _scanned_pr and _raw.strip():
                                        _changed.add(_k)
                                _cur_repo_h = str(_holder.get("repo") or "").strip()
                                if (
                                    _scanned_repo
                                    and _cur_repo_h
                                    and _cur_repo_h.lower() != _scanned_repo.lower()
                                ):
                                    _holder["repo"] = _scanned_repo
                                    _changed.add("repo")
                            if bundle.variable:
                                for _k in ("pr_number", "pr"):
                                    if _k in bundle.variable.values:
                                        _raw = str(bundle.variable.values[_k])
                                        if _raw == _scanned_pr:
                                            continue
                                        bundle.variable.values[_k] = _scanned_pr
                                        if (
                                            normalize_pr_number(_raw) != _scanned_pr
                                            and _raw.strip()
                                        ):
                                            _changed.add(_k)
                                _cur_repo_v = str(bundle.variable.values.get("repo") or "").strip()
                                if (
                                    _scanned_repo
                                    and _cur_repo_v
                                    and _cur_repo_v.lower() != _scanned_repo.lower()
                                ):
                                    bundle.variable.values["repo"] = _scanned_repo
                                    _changed.add("repo")
                            if _changed:
                                print(
                                    f"Warning: stale/empty override/config value(s) "
                                    f"{sorted(_changed)} differ from scanned "
                                    f"pr_number={_scanned_pr}; using the scanned "
                                    f"value for rendering and postExec"
                                )
                            # Canonicalize the scan values themselves so the
                            # later inject_dynamic_vars cannot overwrite the
                            # holder rewrites with the raw ('#N', padded) forms
                            # (#158 R9/R10). A repo rejected by the format gate
                            # is removed entirely — never backfilled as ""
                            # over configured values (#158 R12).
                            dynamic_vars = {
                                **dynamic_vars,
                                "pr_number": _scanned_pr,
                            }
                            if _scanned_repo:
                                dynamic_vars["repo"] = _scanned_repo
                            else:
                                # Empty/whitespace-only/malformed scanned repo:
                                # drop the key loudly so env merge + inject
                                # keep the configured value (#158 R12/R13/R19)
                                print(
                                    "Warning: scan returned invalid repo "
                                    "(format/length gate failed); dropping it "
                                    "— configured repo will be used (#158)"
                                )
                                dynamic_vars.pop("repo", None)
                    # Single-sink repo gate: whatever shape run_pre returned
                    # (repo with or without pr_number, third-party providers
                    # included), the repo that flows into merge/inject/persist
                    # always passed the format+length gate — the invariant does
                    # not rely on run_pre always emitting both keys (#158 R19).
                    _KEYS_PR = ("pr_number", "pr")

                    # pr validity via the shared predicate (issue 3)

                    for _pk in _KEYS_PR:
                        # Alias-family single sink: a run_pre return shape with
                        # pr (or pr-only) but no pr_number bypasses the gate
                        # above; validate here or drop, mirroring the repo gate
                        # (#158 R20: issue 67). len() reports the RAW input so
                        # '####' (normalizes empty) is not reported as len=0
                        # (#158 R21: issue 71).
                        if _pk in dynamic_vars:
                            _raw_pk = str(dynamic_vars[_pk])
                            _pv = normalize_pr_number(_raw_pk)
                            if _pv and pr_number_ok(_pv):
                                dynamic_vars[_pk] = _pv
                            else:
                                print(
                                    f"Warning: discovered {_pk} is invalid "
                                    f"(non-numeric or overlong; len={len(_raw_pk)}); "
                                    f"dropping it (#158)"
                                )
                                dynamic_vars.pop(_pk, None)
                    # Alias reconciliation: pr_number is authoritative (it
                    # won the gate above or is the runtime override — which
                    # has the HIGHEST precedence and also wins here); a
                    # differing pr is stale and silently synced (#158 R21/R23)
                    _auth_pr = normalize_pr_number(
                        bundle.overrides.variable_values.get("pr_number")
                        or dynamic_vars.get("pr_number")
                        or ""
                    )
                    # The authoritative value must itself be valid before it
                    # may override the alias (#158 R24: issue 18)
                    if not pr_number_ok(_auth_pr):
                        _auth_pr = ""
                    if _auth_pr and "pr" in dynamic_vars:
                        dynamic_vars["pr"] = _auth_pr
                    if "pr_url" in dynamic_vars:
                        _pu = str(dynamic_vars.get("pr_url") or "").strip()
                        if _pu and not (
                            _pu.lower().startswith("https://") or _pu.lower().startswith("http://")
                        ):
                            print(
                                f"Warning: discovered pr_url is invalid "
                                f"(scheme gate failed; len={len(_pu)}); "
                                f"dropping it (#158 R23/R24)"
                            )
                            dynamic_vars.pop("pr_url", None)
                    if "repo" in dynamic_vars:
                        _dv_repo = str(dynamic_vars.get("repo") or "").strip()
                        if _dv_repo and repo_ok(_dv_repo):
                            dynamic_vars["repo"] = _dv_repo
                        else:
                            print(
                                f"Warning: discovered repo is invalid "
                                f"(format/length gate failed; len={len(_dv_repo)}); "
                                f"dropping it — configured repo will be used (#158)"
                            )
                            dynamic_vars.pop("repo", None)

                    # Remaining scan-discovered values (pr_title / pr_url /
                    # pr_diff) are provider/author-controlled free text: cap
                    # them before they enter the agent subprocess env (E2BIG)
                    # and Jinja2 rendering. A cap hit means a pathological
                    # payload, so the value is truncated loudly (#158 R21).
                    for _dk in [k for k in dynamic_vars if k.startswith("pr_")]:
                        _dv = str(dynamic_vars[_dk])
                        if len(_dv) > _DISCOVERED_TEXT_MAX:
                            print(
                                f"Warning: discovered {_dk} exceeds "
                                f"{_DISCOVERED_TEXT_MAX} chars (len={len(_dv)}); "
                                f"truncating (#158)"
                            )
                            dynamic_vars[_dk] = _dv[:_DISCOVERED_TEXT_MAX]

                    # Merge discovered vars into env (for postExec substitution)
                    # Skip keys that already exist in runtime overrides (higher priority)
                    for key, value in dynamic_vars.items():
                        if (
                            key not in bundle.overrides.env_vars
                            and key not in bundle.overrides.variable_values
                        ):
                            env_vars[key] = value
                    # Merge discovered vars into bundle (for Jinja2 rendering)
                    bundle.inject_dynamic_vars(dynamic_vars)
                    # Persist scan_pr_result for skip logic (valid scans only;
                    # invalid scans persist nothing — see the branch above)
                    _persistable_pr = normalize_pr_number(dynamic_vars.get("pr_number") or "")
                    _persistable_repo = str(dynamic_vars.get("repo") or "").strip()
                    # head_sha only exists for webhook-triggered runs
                    # (--set-var=head_sha); normalize to lowercase hex.
                    _persistable_head = (
                        str(bundle.overrides.variable_values.get("head_sha") or "").strip().lower()
                    )
                    if _scan_valid and (_persistable_pr or _persistable_repo):
                        # Not persisted for invalid scans: a garbage pr_number
                        # would pollute the (repo, pr_number) failure skip-set
                        # with an empty/garbage key that never matches a real
                        # candidate PR (#158 R10)
                        # Values are already length-validated upstream
                        # (<=64 / <=256), so the persisted copy is identical
                        # to the in-memory one (#158 R14)
                        # Empty-string fields are omitted (not persisted as
                        # dead skip-set entries, #158 R22)
                        result.scan_pr_result = {
                            k: v
                            for k, v in {
                                "repo": _persistable_repo,
                                "pr_number": _persistable_pr,
                                "head_sha": _persistable_head,
                            }.items()
                            if v
                        }
                        # Persist immediately: concurrent streams (webhook /
                        # manual / daemon) must see this target while the
                        # agent is still running (#181). dry_run writes
                        # nothing (it renders only). Read-merge-write:
                        # update_runtime_state is a no-op when the state
                        # file does not exist (e.g. executor invoked
                        # directly without the CLI layer writing it first).
                        if not dry_run:
                            _state = self._history.get_runtime_state(pjob_code, execution_id)
                            if _state is None:
                                _state = {
                                    "execution_id": execution_id,
                                    "pjob_code": pjob_code,
                                    "status": "running",
                                    "pid": os.getpid(),
                                    "started_at": result.started_at,
                                }
                            _state["scan_pr_result"] = result.scan_pr_result
                            self._history.write_runtime_state(pjob_code, execution_id, _state)
                        # Same-(repo, pr, head) dedup guard (#181): skip when
                        # another stream is already reviewing this target
                        # (running) or reviewed it recently (success within
                        # the window). Runs inside the preExec try block so
                        # SkipAction yields SKIPPED (no postExec, no label
                        # changes).
                        if not dry_run and not dedup_off and result.scan_pr_result:
                            _dup = self._history.find_recent_duplicate(
                                pjob_code=pjob_code,
                                repo=result.scan_pr_result.get("repo", ""),
                                pr_number=result.scan_pr_result.get("pr_number", ""),
                                head_sha=result.scan_pr_result.get("head_sha", ""),
                                exclude_execution_id=execution_id,
                            )
                            if _dup:
                                _dup_spr = _dup.get("scan_pr_result") or {}
                                raise SkipAction(
                                    "dedup: duplicate review skipped — execution "
                                    f"'{_dup.get('execution_id')}' "
                                    f"(status={_dup.get('status')}) already covers "
                                    f"({_dup_spr.get('repo')}, PR "
                                    f"#{_dup_spr.get('pr_number')}); re-run with "
                                    "--dedup-off to force"
                                )
                        # Failure guard (#202): stop burning paid calls on a
                        # target whose recent executions produced no valid
                        # review. Independent of the dedup guard above:
                        # --dedup-off bypasses dedup ONLY; only the explicit
                        # failure-guard override bypasses this check.
                        # Same predicate as the finally-block recording below
                        # (repo AND pr_number): a repo-only scan would probe a
                        # bucket that is never written.
                        _fg_spr = result.scan_pr_result or {}
                        if (
                            not dry_run
                            and _fg_spr.get("repo")
                            and _fg_spr.get("pr_number")
                            and not (runtime_overrides and runtime_overrides.failure_guard_off)
                        ):
                            _fg_target = normalize_target(
                                pjob_code=pjob_code,
                                repo=_fg_spr.get("repo", ""),
                                pr_number=_fg_spr.get("pr_number", ""),
                                head_sha=_fg_spr.get("head_sha", ""),
                            )
                            try:
                                _fg_reason = FailureGuard().check(_fg_target)
                                _fg_status = "cooldown_skip"
                            except GuardStateError as _fg_exc:
                                _fg_reason = (
                                    "failure-guard: state unreadable — refusing to "
                                    f"start a paid execution (fail closed): {_fg_exc}"
                                )
                                _fg_status = "guard_error"
                            if _fg_reason:
                                self._history.update_runtime_state(
                                    pjob_code,
                                    execution_id,
                                    failure_guard={
                                        "status": _fg_status,
                                        "target": _fg_target.to_dict(),
                                        "reason": _fg_reason,
                                    },
                                )
                                raise SkipAction(_fg_reason)
                except SkipAction as e:
                    result.status = ExecutionStatus.SKIPPED
                    result.returncode = 0
                    result.stderr = str(e)
                    result.finished_at = generate_timestamp()
                    return result

            # 6. Render workflow template (after preExec so dynamic vars are available)
            prompt_file = self._render_workflow(bundle, temp_dir)
            result.prompt_file = prompt_file

            # 7. Build command
            command = bundle.build_command(prompt_file)
            result.command = command

            # 8. Dry run - capture prompt content and return
            if dry_run:
                result.status = ExecutionStatus.SUCCESS
                result.stdout = f"DRY RUN: Would execute:\n{' '.join(command)}"
                if prompt_file and prompt_file.exists():
                    result.prompt_content = prompt_file.read_text(encoding="utf-8")
                result.finished_at = generate_timestamp()
                return result

            # 9. Execute pre-hooks
            self._run_hooks(pjob.spec.hooks.get("preExec", []), env_vars, bundle.work_dir)

            # 10. Run main command
            result.status = ExecutionStatus.RUNNING
            self._current_process = None

            # For Claude Code, pipe the prompt file as stdin
            stdin_file = prompt_file if bundle.agent.needs_stdin_pipe else None

            returncode, stdout, stderr, process_pid = self._run_command(
                command=command,
                env=env_vars,
                work_dir=bundle.work_dir,
                timeout=pjob.spec.execution.timeout,
                stdin_file=stdin_file,
            )

            result.returncode = returncode
            result.stdout = stdout
            result.stderr = stderr
            result.pid = process_pid
            result.status = ExecutionStatus.SUCCESS if returncode == 0 else ExecutionStatus.FAILED

            # 11. Execute post-hooks
            self._run_hooks(pjob.spec.hooks.get("postExec", []), env_vars, bundle.work_dir)

            # 12. Handle output
            if pjob.spec.output.save_to:
                self._save_output(result, pjob.spec.output)

        except subprocess.TimeoutExpired:
            result.status = ExecutionStatus.TIMEOUT
            result.returncode = 124
            result.stderr = "Execution timed out"
            result.error_detail = f"Timeout after {pjob.spec.execution.timeout}s"
        except KeyboardInterrupt:
            result.status = ExecutionStatus.CANCELLED
            result.returncode = 130
            result.stderr = "Execution cancelled by user (Ctrl+C)"
            # Attempt to terminate subprocess gracefully
            if self._current_process and self._current_process.poll() is None:
                self._current_process.terminate()
                try:
                    self._current_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._current_process.kill()
        except Exception as e:
            import traceback

            result.status = ExecutionStatus.FAILED
            result.returncode = 1
            result.stderr = _friendly_error(e)
            result.error_detail = traceback.format_exc()
        finally:
            # 13. Execute postExec actions even on timeout/cancel/error,
            # but skip on dry-run and skipped preExec.
            if not dry_run and result.status != ExecutionStatus.SKIPPED:
                try:
                    _pjob = locals().get("pjob")
                    _bundle = locals().get("bundle")
                    _env_vars = locals().get("env_vars")
                    if _pjob is not None and _env_vars is not None and _pjob.spec.actions.post_exec:
                        action_env = _env_vars.copy()
                        if _bundle is not None and _bundle.variable:
                            action_env.update(_bundle.variable.values)
                        # Runtime overrides must reach postExec {{var}} substitution
                        # even when the PJob references no Variable config (#158 R3)
                        if _bundle is not None:
                            for k, v in _bundle.overrides.variable_values.items():
                                if v is not None:
                                    action_env.setdefault(k, str(v))
                            # Safety net on top of the pre-merge stale-key pop:
                            # whatever pr/pr_number value action_env ended up
                            # with, the actually-scanned PR must win (#158 R4/R6:
                            # alias symmetry, '#'-normalization, no raw echo,
                            # empty-override bypass).
                            _spr = getattr(result, "scan_pr_result", None) or {}
                            _scanned = normalize_pr_number(_spr.get("pr_number") or "")
                            if _scanned and not pr_number_ok(_scanned):
                                # Same validation as the pre-merge rewrite: an
                                # invalid (non-numeric or overlong) scan value
                                # must not be forced into postExec substitution
                                # (#158 R9/R18)
                                print(
                                    f"Warning: scan returned invalid pr_number "
                                    f"(non-numeric or overlong; len={len(_scanned)}); "
                                    f"skipping pr correction in postExec"
                                )
                                _scanned = ""
                            if _scanned:
                                for _k in ("pr_number", "pr"):
                                    _cur = normalize_pr_number(action_env.get(_k) or "")
                                    if _cur != _scanned:
                                        if _cur:
                                            print(
                                                f"Warning: override {_k} (len={len(_cur)}) "
                                                f"differs from scanned pr_number={_scanned}; "
                                                f"using the scanned value for postExec"
                                            )
                                        action_env[_k] = _scanned
                            # Repo correction is independent of pr_number
                            # validity (#158 R9); case-insensitive — GitHub repo
                            # paths are case-insensitive, format-only variants
                            # must not warn (#158 R9)
                            _scanned_repo = str(_spr.get("repo") or "").strip()
                            # Only a well-formed owner/name may drive postExec
                            # substitution — a misbehaving provider cannot
                            # smuggle arbitrary strings into gh targets (#158 R10)
                            if not repo_ok(_scanned_repo):
                                _scanned_repo = ""
                            _cur_repo = str(action_env.get("repo") or "").strip()
                            if (
                                _scanned_repo
                                and _cur_repo
                                and _cur_repo.lower() != _scanned_repo.lower()
                            ):
                                print(
                                    f"Warning: override repo differs from scanned "
                                    f"repo={_scanned_repo}; using the scanned "
                                    f"value for postExec"
                                )
                                action_env["repo"] = _scanned_repo
                        self._run_post_exec_actions(_pjob, result, action_env)
                except Exception as e:
                    import traceback

                    error_msg = f"Post-exec action setup failed: {e}"
                    result.action_errors.append(error_msg)
                    print(f"Warning: {error_msg}")
                    print(traceback.format_exc())

            result.finished_at = generate_timestamp()

            # Mark as failed when postExec actions failed but agent succeeded
            if result.status == ExecutionStatus.SUCCESS and result.action_errors:
                result.status = ExecutionStatus.FAILED
                result.returncode = 1

            # Failure-guard accounting (#202): once the terminal status is
            # final, record whether this execution produced a valid review.
            # Skipped / dry-run executions never touch the guard; the operator
            # override bypasses the check but still records outcomes so the
            # streak stays truthful. Recording failures must not fail the run.
            _fg_spr = getattr(result, "scan_pr_result", None) or {}
            if (
                not dry_run
                and result.status != ExecutionStatus.SKIPPED
                and _fg_spr.get("repo")
                and _fg_spr.get("pr_number")
            ):
                try:
                    _fg_outcome = classify_execution_result(
                        status=result.status.value,
                        returncode=result.returncode,
                        stdout=result.stdout,
                        expect_review_verdict=True,
                    )
                    _fg_target = normalize_target(
                        pjob_code=pjob_code,
                        repo=_fg_spr.get("repo", ""),
                        pr_number=_fg_spr.get("pr_number", ""),
                        head_sha=_fg_spr.get("head_sha", ""),
                    )
                    FailureGuard().record(_fg_target, _fg_outcome, execution_id=execution_id)
                    if _fg_outcome.countable_failure:
                        self._history.update_runtime_state(
                            pjob_code,
                            execution_id,
                            failure_guard={
                                "status": "recorded_failure",
                                "kind": _fg_outcome.kind,
                            },
                        )
                    elif _fg_outcome.clears_streak:
                        self._history.update_runtime_state(
                            pjob_code,
                            execution_id,
                            failure_guard={"status": "cleared"},
                        )
                except Exception as _fg_exc:  # noqa: BLE001 - observability must not fail the run
                    print(f"Warning: failure-guard record failed: {_fg_exc}")
                    # Spec §6.1-3: guard errors must leave a runtime-state
                    # trace. A corrupt state file first surfacing at record
                    # time would otherwise leave this execution unmarked
                    # until the next run's check (#202 advisory 5).
                    try:
                        self._history.update_runtime_state(
                            pjob_code,
                            execution_id,
                            failure_guard={
                                "status": "guard_error",
                                "phase": "record",
                                "reason": str(_fg_exc),
                            },
                        )
                    except Exception:  # noqa: BLE001 - observability must not fail the run
                        pass

            # Cleanup temp directory
            _pjob_cleanup = locals().get("pjob")
            if temp_dir and not (
                keep_temp or (_pjob_cleanup is not None and _pjob_cleanup.spec.execution.keep_temp)
            ):
                shutil.rmtree(temp_dir, ignore_errors=True)
                result.temp_dir = None
                result.prompt_file = None

            self._current_process = None

        return result

    def _load_pjob(self, code: str) -> PJobConfig:
        """Load PJob configuration."""
        if not self.config_manager.config_exists("pjob", code):
            raise ValueError(f"PJob '{code}' not found")

        data = self.config_manager.load_config("pjob", code)
        return PJobConfig.from_dict(data)

    def _resolve_bundle(
        self,
        pjob: PJobConfig,
        overrides: Optional[Overrides] = None,
    ) -> ConfigBundle:
        """Resolve configuration bundle."""
        bundle = ConfigBundle.resolve(
            pjob_agent=pjob.spec.agent,
            pjob_workflow=pjob.spec.workflow,
            pjob_variable=pjob.spec.variable,
            pjob_env=pjob.spec.env,
            pjob_pmg=pjob.spec.pmg,
            pjob_work_dir=pjob.spec.execution.work_dir,
            config_store=self.config_manager,
        )

        # Apply PJob overrides
        if pjob.spec.overrides and not pjob.spec.overrides.is_empty():
            bundle.apply_overrides(pjob.spec.overrides)

        # Apply runtime overrides (highest priority)
        if overrides and not overrides.is_empty():
            bundle.apply_overrides(overrides)

        return bundle

    def _create_temp_dir(self, pjob_code: str, execution_id: str) -> Path:
        """Create temporary directory for execution under ZIMA_HOME."""
        temp_dir = get_zima_home() / "temp" / "pjobs" / f"{pjob_code}-{execution_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    # NOTE: parallel implementation in zima/execution/template_renderer.py
    # (render_workflow_template). That one is strict (raises) for the CLI
    # ``workflow render`` path; this one is lenient (swallows render errors into
    # an HTML comment) for the agent run path. Kept separate on purpose.
    def _render_workflow(self, bundle: ConfigBundle, temp_dir: Path) -> Path:
        """Render workflow template to prompt file."""
        template = bundle.workflow.template
        variables = bundle.get_variable_values()

        # Render using Jinja2
        try:
            from jinja2 import Template

            jinja_template = Template(template)
            rendered = jinja_template.render(**variables)
        except Exception as e:
            # If rendering fails, use template as-is with a warning
            rendered = f"<!-- Template render error: {e} -->\n{template}"

        # Write to temp file
        prompt_file = temp_dir / "prompt.md"
        prompt_file.write_text(rendered, encoding="utf-8")

        return prompt_file

    def _resolve_env(self, bundle: ConfigBundle) -> dict[str, str]:
        """Resolve environment variables including secrets."""
        # Start with current environment
        env = dict(os.environ)

        if bundle.env:
            # Add plain variables
            for name, value in bundle.env.variables.items():
                env[name] = str(value)

            # Resolve secrets
            for secret in bundle.env.secrets:
                resolved_value = self._resolve_secret(secret)
                if resolved_value is not None:
                    env[secret.name] = resolved_value

        # Apply override env vars (highest priority)
        for name, value in bundle.overrides.env_vars.items():
            env[name] = str(value)

        return env

    # NOTE: parallel implementation in zima/execution/secret_resolver.py
    # (SecretResolver). That one is strict (raises) for the CLI ``env`` path;
    # this one is lenient (returns None on failure, shorter timeout) for the
    # agent run path. Kept separate on purpose.
    def _resolve_secret(self, secret) -> Optional[str]:
        """Resolve a single secret from its source."""
        source = secret.source

        try:
            if source == "env":
                # Read from environment variable
                key = secret.key or secret.name
                return os.environ.get(key)

            elif source == "file":
                # Read from file
                path = Path(secret.path).expanduser()
                if path.exists():
                    return path.read_text().strip()
                return None

            elif source == "cmd":
                # Execute command and get output
                import subprocess

                result = subprocess.run(
                    self._fix_shell_command(secret.command),
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
                return None

            elif source == "vault":
                # For vault, we'd need actual vault integration
                # For now, return a placeholder
                return None

        except Exception:
            return None

        return None

    @staticmethod
    def _fix_shell_command(cmd: str) -> str:
        """Convert && to ; on Windows for PowerShell 5.x compatibility.

        Skips && inside quoted strings. Note: this changes semantics from
        short-circuit (run next only on success) to always-run.
        """
        if os.name != "nt":
            return cmd

        sq = "'"
        # Replace && only when NOT inside single or double quotes
        pattern = (
            r'&&(?=(?:[^"]*"[^"]*")*[^"]*$)'
            r"(?=(?:[^" + sq + r"]*" + sq + r"[^" + sq + r"]*" + sq + r")*[^" + sq + r"]*$)"
        )
        return re.sub(pattern, ";", cmd)

    def _run_hooks(
        self,
        hooks: list[str],
        env: dict[str, str],
        work_dir: str,
    ) -> None:
        """Execute hook commands."""
        for hook in hooks:
            if not hook.strip():
                continue
            try:
                subprocess.run(
                    self._fix_shell_command(hook),
                    shell=True,
                    env=env,
                    cwd=work_dir if work_dir else None,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                # Log warning but don't fail
                print(f"Warning: Hook failed: {hook}")
                print(f"  Error: {e}")

    def _run_post_exec_actions(
        self, pjob: PJobConfig, result: ExecutionResult, env_vars: dict[str, str]
    ) -> None:
        """Run postExec actions based on execution result.

        Args:
            pjob: PJob configuration.
            result: Execution result from agent.
            env_vars: Resolved environment variables for substitution.
        """
        if not pjob.spec.actions.post_exec:
            return

        # Don't parse review XML on timeout or cancellation — agent didn't finish
        is_timeout_or_cancel = result.status in (
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.CANCELLED,
        )

        review_result = None
        if not is_timeout_or_cancel and "<zima-review>" in result.stdout:
            review_result = ReviewParser.parse(result.stdout)

        # Map review verdict to effective returncode for action conditions
        effective_returncode = result.returncode
        if review_result and review_result.verdict == "approved":
            effective_returncode = 0
        elif review_result and review_result.verdict in ("needs_fix", "needs_discussion"):
            effective_returncode = 1

        try:
            action_errors = self._actions_runner.run(
                actions=pjob.spec.actions,
                returncode=effective_returncode,
                env=env_vars,
            )
            result.action_errors.extend(action_errors)
        except Exception as e:
            import traceback

            error_msg = f"Post-exec action failed: {e}"
            result.action_errors.append(error_msg)
            print(f"Warning: {error_msg}")
            print(traceback.format_exc())

    def _run_command(
        self,
        command: list[str],
        env: dict[str, str],
        work_dir: str,
        timeout: int,
        stdin_file: Optional[Path] = None,
    ) -> tuple[int, str, str, int]:
        """
        Run the main agent command.

        Args:
            command: Command arguments
            env: Environment variables
            work_dir: Working directory
            timeout: Timeout in seconds (0 = no timeout)
            stdin_file: Optional file to pipe as stdin (for Claude Code)

        Returns:
            Tuple of (returncode, stdout, stderr, pid)
        """
        import sys

        cwd = work_dir if work_dir else None
        if cwd:
            Path(cwd).mkdir(parents=True, exist_ok=True)

        # Open stdin file if provided (e.g., for Claude Code prompt piping)
        stdin_handle = None
        if stdin_file and stdin_file.exists():
            stdin_handle = open(stdin_file, "r", encoding="utf-8")

        try:
            # Run command with real-time output
            process = subprocess.Popen(
                command,
                env=env,
                cwd=cwd,
                stdin=stdin_handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self._current_process = process

            stdout_lines = []
            stderr_lines = []

            # Stream output in real-time with error protection
            if process.stdout:
                for line in process.stdout:
                    stdout_lines.append(line)
                    try:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    except (OSError, IOError):
                        # Windows may raise [Errno 22] Invalid argument for certain output
                        # Continue execution without real-time display
                        pass

            if process.stderr:
                for line in process.stderr:
                    stderr_lines.append(line)
                    try:
                        sys.stderr.write(line)
                        sys.stderr.flush()
                    except (OSError, IOError):
                        # Windows may raise [Errno 22] Invalid argument for certain output
                        # Continue execution without real-time display
                        pass

            returncode = process.wait(timeout=timeout if timeout > 0 else None)

            return returncode, "".join(stdout_lines), "".join(stderr_lines), process.pid
        finally:
            # Ensure stdin file handle is closed
            if stdin_handle:
                try:
                    stdin_handle.close()
                except (OSError, IOError):
                    pass

    def _save_output(self, result: ExecutionResult, output_options) -> None:
        """Save output to file."""
        from datetime import datetime

        # Process template variables in path
        path_template = output_options.save_to
        now = datetime.now()

        # Replace {{date}} with current date
        path = path_template.replace("{{date}}", now.strftime("%Y-%m-%d"))
        path = path.replace("{{time}}", now.strftime("%H-%M-%S"))
        path = path.replace("{{pjob}}", result.pjob_code)
        path = path.replace("{{execution_id}}", result.execution_id)

        output_path = Path(path)

        # If path is an existing directory, or ends with separator (user intent: directory),
        # auto-generate a default filename inside it.
        if output_path.exists() and output_path.is_dir():
            default_name = f"result-{now.strftime('%Y-%m-%d-%H-%M-%S')}.md"
            output_path = output_path / default_name
        elif str(path).endswith(("/", "\\")):
            output_path.mkdir(parents=True, exist_ok=True)
            default_name = f"result-{now.strftime('%Y-%m-%d-%H-%M-%S')}.md"
            output_path = output_path / default_name
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # Prepare content
        content = result.stdout

        if output_options.format == "json":
            import json

            content = json.dumps(result.to_dict(), indent=2)
        elif output_options.format == "extract-code-blocks":
            # Extract code blocks from markdown
            code_blocks = re.findall(r"```[\w]*\n(.*?)```", result.stdout, re.DOTALL)
            content = "\n\n".join(code_blocks)

        # Write file
        mode = "a" if output_options.append else "w"
        try:
            with open(output_path, mode, encoding="utf-8") as f:
                if output_options.append and output_path.exists():
                    f.write("\n\n---\n\n")
                f.write(content)
        except PermissionError as e:
            raise PermissionError(
                f"Cannot write output to '{output_path}'. "
                f"If this path is a directory, please specify a file name or remove the directory."
            ) from e

    def cancel(self) -> bool:
        """
        Cancel the current execution.

        Returns:
            True if cancelled successfully
        """
        if self._current_process and self._current_process.poll() is None:
            self._current_process.terminate()
            try:
                self._current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._current_process.kill()
            return True
        return False

    def render_prompt(self, pjob_code: str, overrides: Optional[Overrides] = None) -> str:
        """
        Render the workflow template without executing.

        Args:
            pjob_code: PJob code
            overrides: Runtime overrides (optional)

        Returns:
            Rendered prompt content
        """
        pjob = self._load_pjob(pjob_code)
        bundle = self._resolve_bundle(pjob, overrides)

        template = bundle.workflow.template
        variables = bundle.get_variable_values()

        try:
            from jinja2 import Template

            jinja_template = Template(template)
            return jinja_template.render(**variables)
        except Exception as e:
            return f"<!-- Template render error: {e} -->\n{template}"

    def build_command(
        self,
        pjob_code: str,
        overrides: Optional[Overrides] = None,
    ) -> tuple[list[str], Path, dict[str, str]]:
        """
        Build the command without executing.

        Args:
            pjob_code: PJob code
            overrides: Runtime overrides (optional)

        Returns:
            Tuple of (command list, prompt file path, env vars)
        """
        pjob = self._load_pjob(pjob_code)
        bundle = self._resolve_bundle(pjob, overrides)

        temp_dir = self._create_temp_dir(pjob_code, "preview")
        prompt_file = self._render_workflow(bundle, temp_dir)
        env_vars = self._resolve_env(bundle)
        command = bundle.build_command(prompt_file)

        return command, prompt_file, env_vars
