#!/usr/bin/env python3
"""Mock agent for testing. Simulates kimi CLI with minimal delay."""

import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    # Flags matching _build_kimi_command() output
    parser.add_argument("--prompt", required=True, help="Path to prompt file")
    parser.add_argument("--model", default="mock", help="Model name")
    parser.add_argument("--max-steps-per-turn", type=int, default=10, help="Max steps per turn")
    parser.add_argument("--max-ralph-iterations", type=int, default=3)
    parser.add_argument("--max-retries-per-step", type=int, default=1)
    parser.add_argument(
        "--add-dir", action="append", default=[], help="Additional working directories"
    )
    parser.add_argument("--output-format", default="text")
    # Flags from get_cli_command_template() and build_command()
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--print", action="store_true", dest="print_mode")
    parser.add_argument("--work-dir", default=".", help="Working directory")
    args = parser.parse_args()

    # Validate prompt file exists
    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        return 1

    # Read and echo back a snippet (proves file was read)
    prompt_content = prompt_path.read_text(encoding="utf-8")
    summary = prompt_content[:200].replace("\n", " ")

    # Simulate work
    time.sleep(2)

    # Output structured result
    result = {
        "status": "success",
        "model": args.model,
        "steps": args.max_steps_per_turn,
        "summary": f"Mock agent completed. Prompt preview: {summary}...",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
