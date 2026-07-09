"""smee.io client for receiving GitHub webhooks locally."""

from __future__ import annotations

import json
import time
from typing import Optional

import requests


def parse_smee_event(line: str) -> Optional[dict]:
    """Parse a single SSE data line from smee.io."""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def run_smee_client(smee_url: str, target_url: str) -> None:
    """Connect to smee.io and forward events to local target URL."""
    while True:
        try:
            response = requests.get(smee_url, stream=True, headers={"Accept": "text/event-stream"})
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8")
                event = parse_smee_event(line)
                if event is None:
                    continue
                try:
                    requests.post(target_url, json=event, timeout=10)
                except requests.RequestException:
                    # Local server unavailable; log and continue
                    continue
        except requests.RequestException:
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            break
