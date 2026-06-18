#!/usr/bin/env python3
"""Deterministic tool layer (#121).

Runs the repo's own linters/typecheckers so the high-certainty classes — missing
imports, unresolved references, type errors, syntax errors — are caught with ZERO
false positives, instead of asking the bug-scanner LLM to guess at them from a
diff (a known false-positive source, per edge-cases.md).

No MCP; stdlib only; tools invoked via subprocess. Missing manifest or missing
binary => silently skipped (graceful degrade). Never raises: a tool that isn't
installed or that errors just contributes no issues.

Input (stdin): JSON {"repo_root": str, "changed_files": [str]}
Output (stdout): JSON list of issues in the unified schema:
  [{description, reason, file, lines, suggestion, severity}]   reason in {lint,typecheck}

Flags:
  --detect-only   print detected tool names (JSON list) and exit (for testing)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PYTHON_MANIFESTS = ("pyproject.toml", "setup.cfg", "setup.py")
JS_MANIFESTS = ("package.json",)
TS_MANIFESTS = ("tsconfig.json",)

# ruff/mypy share "file:line[:col]: message"; tsc/eslint have their own shapes.
_RUFF_MYPY_RE = re.compile(r"^(?P<file>.+?):(?P<line>\d+)(?::\d+)?:\s*(?P<msg>.+)$")
_TSC_RE = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?:\d+)\):\s*(?P<msg>.+)$")
_ESLINT_RE = re.compile(
    r"^(?P<file>.+?):\s*line\s+(?P<line>\d+),\s*col\s+\d+,\s*\w+\s*-\s*(?P<msg>.+)$"
)

_TOOL_CMD = {
    "ruff": ["ruff", "check", "--output-format=concise", "."],
    "mypy": ["mypy", "."],
    "tsc": ["npx", "--no-install", "tsc", "--noEmit"],
    "eslint": ["npx", "--no-install", "eslint", "--format=compact", "."],
}
_TOOL_REASON = {"ruff": "lint", "mypy": "typecheck", "tsc": "typecheck", "eslint": "lint"}


def detect_toolchains(repo_root) -> list[dict]:
    """Pure detection of applicable tools from manifest files (no execution)."""
    root = Path(repo_root)
    found: list[dict] = []
    has_py = any((root / m).exists() for m in PYTHON_MANIFESTS)
    has_js = any((root / m).exists() for m in JS_MANIFESTS)
    has_ts = any((root / m).exists() for m in TS_MANIFESTS) or has_js
    if has_py:
        found.append({"tool": "ruff", "reason": "lint"})
        found.append({"tool": "mypy", "reason": "typecheck"})
    if has_ts:
        found.append({"tool": "tsc", "reason": "typecheck"})
    if has_js or has_ts:
        found.append({"tool": "eslint", "reason": "lint"})
    return found


def _make_issue(file: str, line: str, msg: str, reason: str) -> dict:
    return {
        "description": msg.strip(),
        "reason": reason,
        "file": file,
        "lines": f"{line}-{line}",
        "suggestion": "",
        "severity": "high" if reason == "typecheck" else "medium",
    }


def parse_diagnostics(tool: str, text: str) -> list[dict]:
    """Parse a tool's combined stdout+stderr into issues (pure)."""
    reason = _TOOL_REASON.get(tool, "lint")
    pattern = {
        "ruff": _RUFF_MYPY_RE,
        "mypy": _RUFF_MYPY_RE,
        "tsc": _TSC_RE,
        "eslint": _ESLINT_RE,
    }.get(tool)
    if not pattern:
        return []
    out = []
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if m:
            out.append(_make_issue(m["file"], m["line"], m["msg"], reason))
    return out


def run_tool(tool: str, repo_root) -> list[dict]:
    """Run one tool if its runner is installed; return parsed issues. Degrade to []."""
    runner = "npx" if tool in ("tsc", "eslint") else tool
    if not shutil.which(runner):
        return []
    cmd = _TOOL_CMD.get(tool)
    if not cmd:
        return []
    try:
        proc = subprocess.run(
            cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=180, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    return parse_diagnostics(tool, (proc.stdout or "") + (proc.stderr or ""))


def run_tool_layer(repo_root, changed_files=None) -> list[dict]:
    issues: list[dict] = []
    for tc in detect_toolchains(repo_root):
        issues.extend(run_tool(tc["tool"], repo_root))
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--detect-only", action="store_true", help="print detected tool names and exit")
    args = ap.parse_args()
    raw = sys.stdin.read()
    try:
        d = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"run_tool_layer: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2
    repo_root = d.get("repo_root", ".")
    if args.detect_only:
        json.dump(
            [tc["tool"] for tc in detect_toolchains(repo_root)], sys.stdout, ensure_ascii=False
        )
        sys.stdout.write("\n")
        return 0
    out = run_tool_layer(repo_root, d.get("changed_files", []))
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
