@echo off
:: Zima Blue CLI - Quick cleanup script for Windows
:: Usage: cleanup.bat [options]
::
:: Options:
::   -a, --auto      Auto mode, no confirmation
::   -n, --dry-run   Preview only
::   -A, --all       Clean including logs
::   -t, --temp-only Only clean temp files
::   -c, --cache-only Only clean cache
::   -h, --help      Show help

cd /d "%~dp0"
python scripts\cleanup.py %*
