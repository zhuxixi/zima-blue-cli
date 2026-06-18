#!/usr/bin/env python3
"""Compress a unified diff for prompt embedding.

Steps:
  1. Optionally drop test-related files (--filter-tests).
  2. If still too long, keep only +/- hunks plus N lines of context.
  3. If still too long, hard-truncate at --max-len chars (sets diff_truncated).

Input (stdin): unified diff (output of `gh pr diff <PR>`).
Output (stdout): compressed diff.

--meta-file PATH (#120): also write a coverage-meta JSON sidecar
({diff_truncated, total_files, kept_files, covered_files, dropped_test_files,
truncated_dropped_files, input_chars, output_chars}) so the status report can
surface partial coverage instead of silently dropping the diff tail. Omit it to
keep the legacy stdout-only behavior.

Examples:
    gh pr diff 123 | python compress_diff.py --max-len 4000
    gh pr diff 123 | python compress_diff.py --filter-tests --max-len 4000 --meta-file /tmp/meta.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__)/"
    r"|(^|/)[^/]+_(test|tests|spec)\.[A-Za-z0-9]+$"
    r"|\.(test|spec)\.[A-Za-z0-9]+$"
)
FILE_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
HUNK_HEADER_RE = re.compile(r"^@@ ")


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH_RE.search(path))


def split_files(diff: str) -> list[list[str]]:
    """Return a list of file-blocks (each a list of lines including its header)."""
    files: list[list[str]] = []
    current: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current:
                files.append(current)
            current = [line]
        else:
            if not current:
                # Stray preamble; keep as its own block.
                current = []
            current.append(line)
    if current:
        files.append(current)
    return files


def _block_path(block: list[str]) -> str | None:
    """The 'a/...' path of a file-block, or None for stray preamble."""
    header = block[0] if block else ""
    m = FILE_HEADER_RE.match(header)
    return m.group(1) if m else None


def _block_is_test(block: list[str]) -> bool:
    header = block[0] if block else ""
    m = FILE_HEADER_RE.match(header)
    if not m:
        return False
    return is_test_path(m.group(1)) or is_test_path(m.group(2))


def keep_hunks_only(diff: str, context_lines: int = 2) -> str:
    """Drop lines that aren't +/-/hunk-header/file-header or within `context_lines`."""
    lines = diff.splitlines()
    n = len(lines)
    keep_idx: set[int] = set()
    for i, line in enumerate(lines):
        if line.startswith("diff --git ") or line.startswith("---") or line.startswith("+++"):
            keep_idx.add(i)
        elif HUNK_HEADER_RE.match(line):
            keep_idx.add(i)
        elif line.startswith(("+", "-")):
            for j in range(max(0, i - context_lines), min(n, i + context_lines + 1)):
                keep_idx.add(j)
    return "\n".join(lines[i] for i in sorted(keep_idx))


def truncate(diff: str, max_len: int) -> str:
    if len(diff) <= max_len:
        return diff
    return diff[:max_len] + "\n... (diff truncated due to length)"


def compress(diff: str, *, filter_tests: bool, max_len: int) -> tuple[str, dict]:
    """Compress the diff and report coverage meta (#120).

    Returns (compressed_diff, meta). `meta["diff_truncated"]` is True iff the
    hard char-ceiling cut content — the signal the status report surfaces so the
    scheduler knows coverage was partial rather than a clean PASS.
    """
    blocks = split_files(diff)
    total_files = sum(1 for b in blocks if _block_path(b))

    if filter_tests:
        kept = [b for b in blocks if not _block_is_test(b)]
        dropped_test_files = [p for p in (_block_path(b) for b in blocks) if p and is_test_path(p)]
    else:
        kept = list(blocks)
        dropped_test_files = []
    kept_paths = [p for p in (_block_path(b) for b in kept) if p]

    out = "\n".join(line for b in kept for line in b)
    diff_truncated = False
    if len(out) > max_len:
        out = keep_hunks_only(out, context_lines=2)
    if len(out) > max_len:
        out = truncate(out, max_len)
        diff_truncated = True

    covered = []
    for line in out.splitlines():
        m = FILE_HEADER_RE.match(line)
        if m:
            covered.append(m.group(1))
    covered_set = set(covered)
    truncated_dropped_files = [p for p in kept_paths if p not in covered_set]

    meta = {
        "filter_tests": filter_tests,
        "diff_truncated": diff_truncated,
        "total_files": total_files,
        "kept_files": len(kept_paths),
        "covered_files": len(covered_set),
        "dropped_test_files": dropped_test_files,
        "truncated_dropped_files": truncated_dropped_files,
        "input_chars": len(diff),
        "output_chars": len(out),
    }
    return out, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--filter-tests",
        action="store_true",
        help="Drop test-related files (tests/, *_test.py, .spec., etc.)",
    )
    ap.add_argument(
        "--max-len",
        type=int,
        default=4000,
        help="Hard length ceiling in characters (default: 4000)",
    )
    ap.add_argument(
        "--meta-file",
        metavar="PATH",
        default=None,
        help="Write coverage meta JSON to PATH (#120); omit for legacy behavior",
    )
    args = ap.parse_args()
    diff = sys.stdin.read()
    out, meta = compress(diff, filter_tests=args.filter_tests, max_len=args.max_len)
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    if args.meta_file:
        with open(args.meta_file, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
