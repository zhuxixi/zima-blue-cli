"""Enable ``python -m zima`` to invoke the CLI.

This mirrors the ``zima = "zima.cli:app"`` console-script entry point so that
``subprocess.Popen([sys.executable, "-m", "zima", ...])`` (used by the webhook
server to trigger PJobs) resolves correctly. Without this file, ``python -m
zima`` fails with "No module named zima.__main__" and the webhook trigger
silently no-ops.
"""

from zima.cli import app

if __name__ == "__main__":
    app()
