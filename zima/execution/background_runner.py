"""Background runner for PJob execution.

This module is invoked as a detached subprocess to run a PJob in the background.
"""

from __future__ import annotations

import json
import sys


def run_pjob_in_background(
    pjob_code: str,
    overrides_json: str | None = None,
    keep_temp: bool = False,
) -> int:
    """Execute a PJob in background and record history.

    Args:
        pjob_code: PJob code to execute.
        overrides_json: JSON string of Overrides dict (optional).
        keep_temp: Whether to keep temporary files.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    from zima.execution.executor import PJobExecutor
    from zima.execution.history import ExecutionHistory, ExecutionRecord
    from zima.models.pjob import Overrides

    overrides = Overrides()
    if overrides_json:
        try:
            overrides = Overrides.from_dict(json.loads(overrides_json))
        except Exception:
            pass

    executor = PJobExecutor()
    result = executor.execute(
        pjob_code=pjob_code,
        overrides=overrides,
        dry_run=False,
        keep_temp=keep_temp,
    )

    # Save to history
    history = ExecutionHistory()
    history.add(ExecutionRecord.from_result(result))

    return 0 if result.status.value == "success" else 1


def main() -> int:
    """CLI entry point for background runner."""
    import argparse

    parser = argparse.ArgumentParser(description="Run a PJob in the background")
    parser.add_argument("pjob_code", help="PJob code to execute")
    parser.add_argument("--overrides", default=None, help="JSON string of overrides")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files")
    args = parser.parse_args()

    return run_pjob_in_background(
        pjob_code=args.pjob_code,
        overrides_json=args.overrides,
        keep_temp=args.keep_temp,
    )


if __name__ == "__main__":
    sys.exit(main())
