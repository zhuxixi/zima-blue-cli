"""
Daemon runner - executed as a separate process for background agent execution

Usage: python -m zima.daemon_runner <agent_dir>
"""

import sys
from datetime import datetime
from pathlib import Path

from zima.utils import setup_windows_utf8

setup_windows_utf8()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m zima.daemon_runner <agent_dir>")
        sys.exit(1)

    agent_dir = Path(sys.argv[1])

    if not agent_dir.exists():
        print(f"Error: Agent directory not found: {agent_dir}")
        sys.exit(1)

    # Load config
    from zima.models import AgentConfig

    config_path = agent_dir / "agent.yaml"

    if not config_path.exists():
        print(f"Error: Agent config not found: {config_path}")
        sys.exit(1)

    config = AgentConfig.from_yaml(config_path)

    # Initialize components
    from zima.core import CycleScheduler, KimiRunner, StateManager

    runner = KimiRunner(config, agent_dir)
    state_manager = StateManager(agent_dir)
    scheduler = CycleScheduler(config, runner, state_manager)

    print(f"[{datetime.now().isoformat()}] Daemon started for agent: {config.name}")
    print(f"[{datetime.now().isoformat()}] Agent directory: {agent_dir}")

    try:
        scheduler.run()
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Daemon error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print(f"[{datetime.now().isoformat()}] Daemon stopped")


if __name__ == "__main__":
    main()
