#!/usr/bin/env python3
"""Merge-strategy probe for the github-code-review-batch skill (issue #253).

Classifies how PRs land on the default branch so metadata rules (subject
format, ``(#N)`` suffix) are judged against the real merge form instead of a
guess:

  squash   GitHub rewrites branch subjects and appends `` (#N)`` automatically
  rebase   branch subjects land verbatim with no automatic ``(#N)``
  merge    a merge commit lands; branch subjects stay untouched
  unknown  no signal, or an ambiguous history sample

Classification is pure; only ``probe()`` performs IO, via ``gh`` subprocess
calls (stdlib only, no MCP). ``probe()`` never raises: every subprocess or
payload error degrades to ``unknown`` / ``probe-failed`` so the review flow can
continue.

CLI:
  python scripts/merge_strategy.py --repo <owner>/<repo> --pr <N> [--json-out PATH]

stdout is exactly one line: ``merge_strategy=<strategy> basis=<basis>``.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

GH_TIMEOUT = 30
SCHEMA_VERSION = 1
FLAG_KEYS = ("squash", "merge", "rebase")
FLAGS_JQ = "{squash:.allow_squash_merge, merge:.allow_merge_commit, rebase:.allow_rebase_merge}"
HISTORY_SAMPLE = 10
HISTORY_MIN_SAMPLE = 5
HISTORY_MAJORITY = 0.8
MERGE_SUBJECT_PREFIX = "Merge pull request #"

HISTORY_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: MERGED, first: %d, orderBy: {field: MERGED_AT, direction: DESC}) {
      nodes { number mergeCommit { message } }
    }
  }
}
""" % HISTORY_SAMPLE

POLICY_TABLE = {
    "squash": {"inject_branch_subjects": False, "check_pr_title": True},
    "rebase": {"inject_branch_subjects": True, "check_pr_title": False},
    "merge": {"inject_branch_subjects": True, "check_pr_title": False},
    "unknown": {"inject_branch_subjects": False, "check_pr_title": True},
}
METADATA_MAX_SEVERITY = "low"


def classify_flags(flags: dict[str, bool]) -> tuple[str, str] | None:
    """Return (strategy, "flags") when exactly one merge method is enabled."""
    enabled = [key for key in FLAG_KEYS if flags.get(key) is True]
    if len(enabled) != 1:
        return None
    return enabled[0], "flags"


def classify_headline(pr_number: int, headline: str) -> str:
    """Classify one landed subject line as merge, squash, or rebase.

    ``headline`` must be the first line of ``mergeCommit.message``; the GraphQL
    ``messageHeadline`` field is truncated at 70 chars with "…" and would drop
    the `` (#N)`` suffix, misclassifying squash as rebase.
    """
    if headline.startswith(MERGE_SUBJECT_PREFIX):
        return "merge"
    if headline.endswith(f" (#{pr_number})"):
        return "squash"
    return "rebase"


def classify_history(rows: list[tuple[int, str]]) -> tuple[str, str, dict]:
    """Vote on the merge form from recently merged PRs (number, first subject line).

    A bucket wins only with at least ``ceil(0.8 * n)`` votes and ``n >= 5``
    samples; otherwise the sample is too small or too mixed to conclude.
    """
    buckets = {"squash": 0, "rebase": 0, "merge": 0}
    for number, headline in rows:
        buckets[classify_headline(number, headline)] += 1
    sample_size = len(rows)
    evidence = {**buckets, "merged_sampled": sample_size}
    if sample_size < HISTORY_MIN_SAMPLE:
        return "unknown", "history-ambiguous", evidence
    threshold = math.ceil(HISTORY_MAJORITY * sample_size)
    for strategy in ("squash", "rebase", "merge"):
        if buckets[strategy] >= threshold:
            return strategy, "history", evidence
    return "unknown", "history-ambiguous", evidence


def render_policy(strategy: str) -> dict:
    """Derive what the compliance checkers may rely on for this merge form."""
    policy = POLICY_TABLE.get(strategy, POLICY_TABLE["unknown"])
    return {
        "inject_branch_subjects": policy["inject_branch_subjects"],
        "check_pr_title": policy["check_pr_title"],
        "metadata_max_severity": METADATA_MAX_SEVERITY,
    }


def decide(
    repo: str,
    pr: int,
    flags: dict,
    rows: list[tuple[int, str]] | None,
) -> dict:
    """Combine flag and history signals into the probe payload.

    ``rows is None`` means the history query was not attempted or failed; if no
    single flag decided the form beforehand, the result is ``probe-failed``.
    """
    flags_res = classify_flags(flags)
    evidence: dict = {
        # Always emit all three keys so consumers can index the payload on the
        # degradation path too (missing source fields are reported as False).
        "flags": {key: bool(flags.get(key)) for key in FLAG_KEYS},
        "merged_sampled": 0,
        "buckets": {"squash": 0, "rebase": 0, "merge": 0},
        "sample_prs": [],
    }

    if flags_res is not None:
        strategy, basis = flags_res
    elif rows is None:
        strategy, basis = "unknown", "probe-failed"
    else:
        strategy, basis, history = classify_history(rows)
        evidence["merged_sampled"] = history["merged_sampled"]
        evidence["buckets"] = {key: history[key] for key in ("squash", "rebase", "merge")}
        evidence["sample_prs"] = [number for number, _ in rows][:3]

    return {
        "schema": SCHEMA_VERSION,
        "repo": repo,
        "pr": pr,
        "strategy": strategy,
        "basis": basis,
        "evidence": evidence,
        "policy": render_policy(strategy),
    }


def _run_gh(run, cmd: list[str]) -> subprocess.CompletedProcess:
    return run(
        cmd,
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def _gh_json(run, cmd: list[str]):
    proc = _run_gh(run, cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(cmd[1:3])} failed: {(proc.stderr or '').strip()}")
    return json.loads(proc.stdout)


def _fetch_flags(run, repo: str) -> dict:
    payload = _gh_json(run, ["gh", "api", f"repos/{repo}", "--jq", FLAGS_JQ])
    if not isinstance(payload, dict):
        raise RuntimeError("repository flags payload is not an object")
    return {key: payload.get(key) for key in FLAG_KEYS}


def _fetch_history(run, repo: str) -> list[tuple[int, str]]:
    owner, _, name = repo.partition("/")
    if not owner or not name:
        raise ValueError(f"repo must be owner/name: {repo!r}")
    payload = _gh_json(
        run,
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={HISTORY_QUERY}",
            "-f",
            f"owner={owner}",
            "-f",
            f"name={name}",
        ],
    )
    nodes = payload["data"]["repository"]["pullRequests"]["nodes"]
    rows: list[tuple[int, str]] = []
    for node in nodes:
        commit = node.get("mergeCommit") or {}
        message = commit.get("message") or ""
        headline = message.split("\n")[0].strip()
        if headline:
            rows.append((int(node["number"]), headline))
    return rows


def probe(repo: str, pr: int, run=subprocess.run) -> dict:
    """Classify the repo's merge form; any failure degrades, never raises."""
    try:
        flags = _fetch_flags(run, repo)
    except Exception:  # noqa: BLE001 - probe must fail open, never traceback
        return decide(repo, pr, {}, None)

    if classify_flags(flags) is not None:
        return decide(repo, pr, flags, None)

    try:
        rows = _fetch_history(run, repo)
    except Exception:  # noqa: BLE001 - history is optional; degrade to unknown
        return decide(repo, pr, flags, None)

    return decide(repo, pr, flags, rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify the repo merge strategy.")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    parser.add_argument("--json-out", default=None, help="path for the probe JSON payload")
    args = parser.parse_args(argv)

    # Resolve the module attribute at call time so tests can stub subprocess.run.
    payload = probe(args.repo, args.pr, run=subprocess.run)

    if args.json_out:
        try:
            Path(args.json_out).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            # The probe contract is "degrade, never fail the review flow": an
            # unwritable --json-out must not turn Step 2.5 into a blocker.
            print(f"merge_strategy: could not write {args.json_out}: {exc}", file=sys.stderr)
    print(f"merge_strategy={payload['strategy']} basis={payload['basis']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
