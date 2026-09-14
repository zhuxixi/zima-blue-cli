"""Usage ledger collection for PJob executions (#213).

Reads pi session files and pi-subagents artifact metadata written under the
execution's own temp directory, aggregates them into a single ``usage`` dict
that is persisted with the execution history record.

Every function is fail-open: unreadable or malformed input degrades to an
empty result instead of raising. The orchestration entry point
(:func:`collect_usage`) never raises at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional, Sequence

ROLE_PARENT = "parent"
ROLE_CHILD = "child"

#: Keys shared by every totals bucket. Order matters only for readability.
_TOTAL_KEYS = ("input", "output", "cache_read", "cache_write", "total_tokens")


def _empty_totals() -> dict:
    """Return a zeroed totals bucket."""
    totals = {key: 0 for key in _TOTAL_KEYS}
    totals["cost_usd"] = 0.0
    return totals


def _add_into(target: dict, entry: dict) -> None:
    """Add an entry's numeric fields into a totals bucket (in place)."""
    for key in _TOTAL_KEYS:
        try:
            target[key] += int(entry.get(key) or 0)
        except (TypeError, ValueError):
            continue
    try:
        target["cost_usd"] += float(entry.get("cost_usd") or 0.0)
    except (TypeError, ValueError):
        pass


def _iter_session_messages(path: Path) -> Iterator[dict]:
    """Yield parsed JSON objects from a session JSONL file.

    Malformed lines and unreadable files are skipped silently so that one bad
    line cannot discard an otherwise valid ledger.
    """
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _parent_entry(message: dict) -> Optional[dict]:
    """Extract a usage entry from a pi session ``assistant`` message.

    Returns ``None`` for any message that carries no provider-reported usage.
    """
    if message.get("role") != "assistant":
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    cost = usage.get("cost")
    return {
        "input": usage.get("input", 0),
        "output": usage.get("output", 0),
        "cache_read": usage.get("cacheRead", 0),
        "cache_write": usage.get("cacheWrite", 0),
        "total_tokens": usage.get("totalTokens", 0),
        "cost_usd": cost.get("total", 0.0) if isinstance(cost, dict) else 0.0,
        "provider": message.get("provider") or "unknown",
        "model": message.get("model") or "unknown",
    }


def parse_parent_usage(session_files: Sequence[Path]) -> dict:
    """Aggregate parent-agent usage from top-level pi session files.

    Args:
        session_files: Top-level session JSONL paths. Files under ``forks/``
            must NOT be passed here — they contain copies of parent messages
            and would double count.

    Returns:
        ``{"totals": <totals>, "by_model": [<bucket>, ...]}`` where each bucket
        is grouped by ``(provider, model)``.
    """
    totals = _empty_totals()
    buckets: dict[tuple[str, str], dict] = {}

    for path in session_files:
        for entry in _iter_session_messages(Path(path)):
            if entry.get("type") != "message":
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            parsed = _parent_entry(message)
            if parsed is None:
                continue

            _add_into(totals, parsed)
            key = (parsed["provider"], parsed["model"])
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "role": ROLE_PARENT,
                    "agent": None,
                    "provider": key[0],
                    "model": key[1],
                    "turns": None,
                    **_empty_totals(),
                }
                buckets[key] = bucket
            _add_into(bucket, parsed)

    return {"totals": totals, "by_model": list(buckets.values())}


def _split_child_model(raw: str) -> tuple[str, str]:
    """Split a pi-subagents model string into ``(provider, model)``.

    ``model`` keeps the reported value verbatim (including any ``:thinking``
    suffix) so the ledger can show which tier actually ran. Aggregation
    therefore happens per exact model string.
    """
    raw = raw or "unknown"
    if "/" in raw:
        provider, model = raw.split("/", 1)
        return provider, model
    return "unknown", raw


def _child_entry(meta: dict) -> Optional[dict]:
    """Extract a usage entry from a pi-subagents ``*_meta.json`` payload.

    pi-subagents metadata reports no ``totalTokens`` field, so the total is
    computed as the sum of the four token counters. Returns ``None`` when the
    payload carries no usable ``usage`` object.
    """
    usage = meta.get("usage")
    if not isinstance(usage, dict):
        return None
    provider, model = _split_child_model(str(meta.get("model") or ""))
    try:
        input_tokens = int(usage.get("input") or 0)
        output = int(usage.get("output") or 0)
        cache_read = int(usage.get("cacheRead") or 0)
        cache_write = int(usage.get("cacheWrite") or 0)
        cost = float(usage.get("cost") or 0.0)
    except (TypeError, ValueError):
        return None
    turns = usage.get("turns")
    try:
        turns = int(turns) if turns is not None else None
    except (TypeError, ValueError):
        turns = None
    return {
        "input": input_tokens,
        "output": output,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "total_tokens": input_tokens + output + cache_read + cache_write,
        "cost_usd": cost,
        "agent": meta.get("agent") or "unknown",
        "provider": provider,
        "model": model,
        "turns": turns,
    }


def parse_child_usage(artifacts_dir: Optional[Path]) -> dict:
    """Aggregate subagent usage from pi-subagents artifact metadata.

    Args:
        artifacts_dir: ``<session_dir>/subagent-artifacts`` (may be missing).

    Returns:
        ``{"totals": <totals>, "by_model": [<bucket>, ...], "children_count": int}``
        where buckets are grouped by ``(agent, provider, model)``.

    A bucket's ``turns`` starts at ``0`` and is summed across its children;
    if any contributing child lacks ``turns``, the bucket's ``turns`` becomes
    ``None`` — unknown must not masquerade as a sum of zeros.
    """
    totals = _empty_totals()
    buckets: dict[tuple[str, str, str], dict] = {}
    children_count = 0

    if artifacts_dir is not None and Path(artifacts_dir).is_dir():
        for meta_file in sorted(Path(artifacts_dir).glob("*_meta.json")):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            parsed = _child_entry(meta)
            if parsed is None:
                continue

            children_count += 1
            _add_into(totals, parsed)
            key = (parsed["agent"], parsed["provider"], parsed["model"])
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "role": ROLE_CHILD,
                    "agent": key[0],
                    "provider": key[1],
                    "model": key[2],
                    "turns": 0,
                    **_empty_totals(),
                }
                buckets[key] = bucket
            _add_into(bucket, parsed)
            if parsed["turns"] is None or bucket["turns"] is None:
                bucket["turns"] = None
            else:
                bucket["turns"] += parsed["turns"]

    return {"totals": totals, "by_model": list(buckets.values()), "children_count": children_count}


#: Marks cost as a price-table estimate rather than a cash spend.
COST_NOTE_ESTIMATED = "estimated"


def merge_usage(parent: dict, children: dict) -> dict:
    """Merge parent and child usage into the persisted ``usage`` payload.

    Args:
        parent: Result of :func:`parse_parent_usage`.
        children: Result of :func:`parse_child_usage`.

    Returns:
        The complete ``usage`` dict stored on the execution record, with
        ``collected: True``.
    """
    totals = _empty_totals()
    _add_into(totals, parent.get("totals") or {})
    _add_into(totals, children.get("totals") or {})

    return {
        "collected": True,
        "totals": totals,
        "by_role": {
            "parent": parent.get("totals") or _empty_totals(),
            "children": children.get("totals") or _empty_totals(),
        },
        "by_model": list(parent.get("by_model") or []) + list(children.get("by_model") or []),
        "children_count": int(children.get("children_count") or 0),
        "cost_note": COST_NOTE_ESTIMATED,
    }


def collect_usage(session_dir: Optional[Path], agent_type: str = "pi") -> dict:
    """Collect the usage ledger for one execution. Never raises.

    This is the fail-open boundary of the module: parse and merge helpers may
    raise on unexpected input, but any exception raised inside the pipeline is
    swallowed here and reported as ``parse_error`` so that observability can
    never break an execution (#213).

    Args:
        session_dir: ``<temp_dir>/pi-sessions`` — the directory handed to pi
            via ``--session-dir``.
        agent_type: Agent type of the executed PJob (only ``"pi"`` is
            supported; anything else reports ``unsupported_agent_type``).

    Returns:
        Either the merged ``usage`` payload (``collected: True``) or
        ``{"collected": False, "reason": <code>}`` with ``code`` in
        ``{"no_session_dir", "empty", "parse_error", "unsupported_agent_type"}``.
        The failed shape deliberately carries no ``totals`` key: a missing
        ledger must never masquerade as zero spend.
    """
    if agent_type != "pi":
        return {"collected": False, "reason": "unsupported_agent_type"}
    if session_dir is None:
        return {"collected": False, "reason": "no_session_dir"}

    try:
        root = Path(session_dir)
        if not root.is_dir():
            return {"collected": False, "reason": "no_session_dir"}

        # Top-level session files only: forks/ holds copies of the parent
        # history and subagent-artifacts/ holds child transcripts — counting
        # either would double count.
        session_files = sorted(p for p in root.glob("*.jsonl") if p.is_file())
        parent = parse_parent_usage(session_files)
        children = parse_child_usage(root / "subagent-artifacts")
        merged = merge_usage(parent, children)

        if merged["totals"]["total_tokens"] <= 0:
            return {"collected": False, "reason": "empty"}
        return merged
    except Exception:
        # Fail-open by design: observability must never break an execution.
        return {"collected": False, "reason": "parse_error"}
