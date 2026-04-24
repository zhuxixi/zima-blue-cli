"""Quickstart scene template definitions."""

from __future__ import annotations

QUICKSTART_SCENES: dict[str, dict] = {
    "code-review": {
        "name": "Code Review",
        "description": "Review PRs with Kimi github-code-review skill",
        "workflow_template": "CR {{ pr_url }}",
        "variables": {"pr_url": ""},
    },
    "custom": {
        "name": "Custom Task",
        "description": "Write your own prompt template",
        "workflow_template": "",
        "variables": {},
    },
}
