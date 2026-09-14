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
