#!/bin/bash
# Zima Blue CLI - Quick cleanup script for Unix/Linux/Mac
# Usage: ./cleanup.sh [options]
#
# Options:
#   -a, --auto      Auto mode, no confirmation
#   -n, --dry-run   Preview only
#   -A, --all       Clean including logs
#   -t, --temp-only Only clean temp files
#   -c, --cache-only Only clean cache
#   -h, --help      Show help

cd "$(dirname "$0")"
python3 scripts/cleanup.py "$@"
