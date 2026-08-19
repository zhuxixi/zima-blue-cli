"""Tests for the deterministic tool layer (#121).

Unit-tests the pure parts (toolchain detection, diagnostic parsing) by importing
the module, and tests graceful-degrade behavior end-to-end via subprocess.
Nothing here requires a real toolchain to be installed — that's the point.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = _REPO_ROOT / "pi" / "github-code-review-batch" / "scripts" / "run_tool_layer.py"

_spec = importlib.util.spec_from_file_location("run_tool_layer", SCRIPT)
rtl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rtl)


def _run(payload: dict, *flags: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *flags],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


class TestPortability:
    def test_stdlib_only(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
        non_stdlib = sorted({m for m in imports if m not in sys.stdlib_module_names})
        assert not non_stdlib, f"non-stdlib imports: {non_stdlib}"


class TestDetect:
    def test_python_manifest(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        assert [t["tool"] for t in rtl.detect_toolchains(tmp_path)] == ["ruff", "mypy"]

    def test_typescript_manifest(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("")
        tools = [t["tool"] for t in rtl.detect_toolchains(tmp_path)]
        assert "tsc" in tools and "eslint" in tools

    def test_no_manifest(self, tmp_path):
        assert rtl.detect_toolchains(tmp_path) == []


class TestParse:
    def test_ruff(self):
        out = rtl.parse_diagnostics("ruff", "src/a.py:10:5: F401 'os' imported but unused")
        assert len(out) == 1
        assert out[0]["file"] == "src/a.py"
        assert out[0]["lines"] == "10-10"
        assert out[0]["reason"] == "lint"

    def test_mypy_typecheck_severity(self):
        out = rtl.parse_diagnostics("mypy", "src/b.py:20: error: Incompatible type [arg-type]")
        assert out[0]["reason"] == "typecheck"
        assert out[0]["severity"] == "high"

    def test_tsc(self):
        out = rtl.parse_diagnostics("tsc", "src/c.ts(3,5): error TS2322: Type 'string'")
        assert out[0]["file"] == "src/c.ts"
        assert out[0]["lines"] == "3-3"

    def test_eslint(self):
        out = rtl.parse_diagnostics(
            "eslint", "src/d.js: line 1, col 2, Error - 'x' is not defined (no-undef)"
        )
        assert out[0]["reason"] == "lint"

    def test_unparseable_line_ignored(self):
        assert rtl.parse_diagnostics("ruff", "some noise without colons") == []


class TestEndToEnd:
    def test_no_manifest_degrades_to_empty(self, tmp_path):
        assert json.loads(_run({"repo_root": str(tmp_path)})) == []

    def test_detect_only_flag(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        assert json.loads(_run({"repo_root": str(tmp_path)}, "--detect-only")) == ["ruff", "mypy"]

    def test_missing_binary_skipped(self, tmp_path, monkeypatch):
        # pyproject present but neither ruff nor mypy on PATH -> still [], no crash
        (tmp_path / "pyproject.toml").write_text("")
        monkeypatch.setattr(rtl.shutil, "which", lambda _cmd: None)
        assert rtl.run_tool_layer(tmp_path) == []


class TestFilesScoping:
    """#174: --files scopes linters to the PR's changed files.

    Pre-existing findings outside the changed set must not flood the review
    (40 findings on PR #166 drowned the round). Applies to: command targets
    (ruff/mypy/eslint), output intersection (tsc runs project-wide, filter
    after), and the stdin changed_files field.
    """

    def test_ruff_cmd_targets_files_when_given(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        cmds = []

        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            m = type("P", (), {"stdout": "", "stderr": "", "returncode": 0})()
            return m

        orig = rtl.subprocess.run
        rtl.subprocess.run = fake_run
        try:
            rtl.run_tool("ruff", tmp_path, files=["a.py", "b/c.py"])
        finally:
            rtl.subprocess.run = orig
        assert cmds and cmds[0][:3] == ["ruff", "check", "--output-format=concise"]
        assert cmds[0][1:] != rtl._TOOL_CMD["ruff"][1:]  # not the full-repo "."
        assert "a.py" in cmds[0] and "b/c.py" in cmds[0]

    def test_output_intersected_to_files(self):
        raw = "src/changed.py:10: unused import os\n" "scripts/legacy.py:3: old debt\n"
        issues = rtl.parse_diagnostics("ruff", raw)
        scoped = rtl.filter_to_files(issues, ["src/changed.py"])
        assert len(scoped) == 1
        assert scoped[0]["file"] == "src/changed.py"

    def test_path_normalization_in_filter(self):
        issues = rtl.parse_diagnostics("ruff", "./src/x.py:1: msg")
        scoped = rtl.filter_to_files(issues, ["src/x.py"])
        assert len(scoped) == 1

    def test_no_files_runs_full_repo(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        cmds = []

        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            return type("P", (), {"stdout": "", "stderr": "", "returncode": 0})()

        orig = rtl.subprocess.run
        rtl.subprocess.run = fake_run
        try:
            rtl.run_tool("ruff", tmp_path, files=None)
        finally:
            rtl.subprocess.run = orig
        assert cmds[0] == rtl._TOOL_CMD["ruff"]

    def test_cli_files_flag_end_to_end(self, tmp_path):
        # A real clean file: ruff (when installed) must produce zero findings
        # for it; scopes to the file rather than the whole tmp repo.
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "x.py").write_text("import os\n\nprint(os.getcwd())\n")
        out = _run({"repo_root": str(tmp_path)}, "--files", "x.py")
        assert json.loads(out) == []

    def test_stdin_changed_files_scopes_output(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        (tmp_path / "x.py").write_text("import os\n\nprint(os.getcwd())\n")
        out = _run({"repo_root": str(tmp_path), "changed_files": ["x.py"]})
        assert json.loads(out) == []
