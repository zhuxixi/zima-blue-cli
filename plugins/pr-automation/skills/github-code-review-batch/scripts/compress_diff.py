#!/usr/bin/env python3
"""Compress a unified diff for prompt embedding.

Steps:
  1. Optionally drop test-related files (--filter-tests).
  2. If still too long, keep only +/- hunks plus N lines of context.
  3. If still too long, hard-truncate at --max-len chars.

Input (stdin): unified diff (output of `gh pr diff <PR>`).
Output (stdout): compressed diff.

Examples:
    gh pr diff 123 | python compress_diff.py --max-len 4000
    gh pr diff 123 | python compress_diff.py --filter-tests --max-len 4000
"""

from __future__ import annotations

import argparse
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


def filter_test_files(diff: str) -> str:
    blocks = split_files(diff)
    keep: list[str] = []
    for block in blocks:
        header = block[0] if block else ""
        m = FILE_HEADER_RE.match(header)
        if m and (is_test_path(m.group(1)) or is_test_path(m.group(2))):
            continue
        keep.extend(block)
    return "\n".join(keep)


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


def compress(diff: str, *, filter_tests: bool, max_len: int) -> str:
    if filter_tests:
        diff = filter_test_files(diff)
    if len(diff) > max_len:
        diff = keep_hunks_only(diff, context_lines=2)
    if len(diff) > max_len:
        diff = truncate(diff, max_len)
    return diff


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--filter-tests", action="store_true",
                    help="Drop test-related files (tests/, *_test.py, .spec., etc.)")
    ap.add_argument("--max-len", type=int, default=4000,
                    help="Hard length ceiling in characters (default: 4000)")
    args = ap.parse_args()
    diff = sys.stdin.read()
    out = compress(diff, filter_tests=args.filter_tests, max_len=args.max_len)
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
