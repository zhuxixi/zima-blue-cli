#!/usr/bin/env bash
# Issue #38 verification wrapper
# Usage: ./scripts/verify-issue38.sh [--run-real-agent]

set -euo pipefail

REAL_AGENT=""
if [[ "${1:-}" == "--run-real-agent" ]]; then
    REAL_AGENT="--run-real-agent"
    echo "Running with REAL agent (slow)..."
else
    echo "Running mock verification suite..."
fi

echo ""
echo "=== Running pytest integration tests ==="
pytest tests/integration/test_issue38_daemon_verification.py -v ${REAL_AGENT}

echo ""
echo "=== Running filesystem checklist ==="
python scripts/verify_issue38_checklist.py

echo ""
echo "Verification complete."
