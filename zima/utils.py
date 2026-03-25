"""Utility functions"""

import sys


def safe_print(text: str) -> None:
    """Print text safely handling encoding issues on Windows"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fall back to ASCII-only on encoding errors
        ascii_text = text.encode('ascii', 'ignore').decode('ascii')
        print(ascii_text)


def icon(name: str) -> str:
    """Get an icon (or empty string on Windows to avoid encoding issues)"""
    if sys.platform == "win32":
        return ""
    
    icons = {
        "rocket": "🚀",
        "stop": "⏹️",
        "cycle": "🌅",
        "task": "🎯",
        "result": "📊",
        "sleep": "💤",
        "complete": "🎉",
        "warning": "⚠️",
        "check": "✓",
        "cross": "✗",
    }
    return icons.get(name, "")
