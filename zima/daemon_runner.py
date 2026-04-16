"""
Daemon runner - executed as a separate process for background scheduling.

Usage: python -m zima.daemon_runner --schedule <schedule_code>
"""

import argparse
import os
import sys
from pathlib import Path

from zima.config.manager import ConfigManager
from zima.core.daemon_scheduler import DaemonScheduler
from zima.models.schedule import ScheduleConfig
from zima.utils import setup_windows_utf8

setup_windows_utf8()


def parse_args():
    parser = argparse.ArgumentParser(description="Zima Daemon Runner")
    parser.add_argument("--schedule", required=True, help="Schedule code to run")
    return parser.parse_args()


def main():
    args = parse_args()
    schedule_code = args.schedule

    manager = ConfigManager()
    if not manager.config_exists("schedule", schedule_code):
        print(f"Error: Schedule '{schedule_code}' not found")
        sys.exit(1)

    data = manager.load_config("schedule", schedule_code)
    schedule = ScheduleConfig.from_dict(data)

    errors = schedule.validate(resolve_refs=True)
    if errors:
        print("Error: Schedule validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    daemon_dir = Path.home() / ".zima" / "daemon"
    scheduler = DaemonScheduler(schedule, daemon_dir)

    # Write PID file
    pid_file = daemon_dir / "daemon.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    try:
        scheduler.run()
    except KeyboardInterrupt:
        scheduler.stop()
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
