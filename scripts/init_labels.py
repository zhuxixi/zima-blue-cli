#!/usr/bin/env python3
"""
Initialize zima PR labels in a GitHub repository.

Usage:
    python scripts/init_labels.py --repo owner/repo
    python scripts/init_labels.py --repo owner/repo --force
    python scripts/init_labels.py --repo owner/repo --dry-run
"""

import argparse
import json
import subprocess
import sys

LABELS = [
    {"name": "zima:needs-review", "color": "0969DA", "description": "等待 code review"},
    {"name": "zima:needs-fix", "color": "CF222E", "description": "CR 发现问题，需要修复"},
    {"name": "zima:needs-re-review", "color": "BC4C00", "description": "fix 后等待重新 review"},
    {
        "name": "zima:wait-human-merge",
        "color": "2DA44E",
        "description": "CR 阶段完成，等待人工 merge",
    },
    {"name": "zima:jesus-help", "color": "8250DF", "description": "循环超限，需人工介入"},
]


def run_gh(args: list[str]) -> subprocess.CompletedProcess:
    """Run gh CLI command."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return result


def list_labels(repo: str) -> list[dict]:
    """List all labels in the repo. Returns empty list on error."""
    result = run_gh(["label", "list", "--repo", repo, "--json", "name"])
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def label_exists(repo: str, name: str) -> bool:
    """Check if a label already exists in the repo."""
    existing = list_labels(repo)
    return any(item["name"] == name for item in existing)


def create_label(repo: str, label: dict, force: bool = False) -> str:
    """Create a single label. Returns 'created', 'skipped', or 'failed'."""
    name = label["name"]
    exists = label_exists(repo, name)

    if exists and not force:
        print(f"  [SKIP] {name} already exists")
        return "skipped"

    if exists and force:
        # Delete and recreate
        run_gh(["label", "delete", name, "--repo", repo, "--yes"])
        print(f"  [DELETE] {name} (force mode)")

    result = run_gh(
        [
            "label",
            "create",
            name,
            "--repo",
            repo,
            "--color",
            label["color"],
            "--description",
            label["description"],
        ]
    )

    if result.returncode == 0:
        print(f"  [OK] {name} (#{label['color']})")
        return "created"
    else:
        print(f"  [FAIL] {name}: {result.stderr.strip()}")
        return "failed"


def main():
    parser = argparse.ArgumentParser(description="Initialize zima PR labels")
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument("--force", action="store_true", help="Recreate existing labels")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    # Validate gh is available
    result = run_gh(["--version"])
    if result.returncode != 0:
        print("[ERROR] gh CLI not found. Install from https://cli.github.com/")
        sys.exit(1)

    print(f"Initializing zima labels for {args.repo}...")
    if args.dry_run:
        print("[DRY-RUN] No changes will be made")

    created = 0
    skipped = 0
    failed = 0

    # In dry-run, list labels once to avoid repeated API calls
    existing_labels = set()
    if args.dry_run:
        existing_labels = {item["name"] for item in list_labels(args.repo)}

    for label in LABELS:
        if args.dry_run:
            exists = label["name"] in existing_labels
            if exists and not args.force:
                print(f"  [DRY-RUN] Would skip: {label['name']} (exists)")
                skipped += 1
            else:
                action = "recreate" if exists else "create"
                print(f"  [DRY-RUN] Would {action}: {label['name']} (#{label['color']})")
                created += 1
        else:
            status = create_label(args.repo, label, force=args.force)
            if status == "created":
                created += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1

    print(f"\nDone: {created} created, {skipped} skipped, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
