"""Terminal presentation: colour policy, number formatting and small layout primitives.

The TypeScript implementation carries the same module. CI diffs the rendered output of both
CLIs, so anything added here needs its counterpart there.
"""

from __future__ import annotations

import os
import sys

_CODES = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
}

_enabled = False


def set_color(when: str, *, is_tty: bool | None = None) -> None:
    """Decide whether to emit escape codes.

    Args:
        when: ``auto``, ``always`` or ``never``.
        is_tty: Override the terminal check, for tests.

    ``auto`` follows the NO_COLOR convention first, then whether stdout is a terminal, so
    redirected output and CI logs stay diffable.
    """
    global _enabled
    if when == "never":
        _enabled = False
    elif when == "always":
        _enabled = True
    else:
        tty = sys.stdout.isatty() if is_tty is None else is_tty
        _enabled = tty and os.environ.get("NO_COLOR") is None


def paint(color: str, text: str) -> str:
    """Colour text when colour is enabled."""
    if not _enabled:
        return text
    return f"{_CODES[color]}{text}{_CODES['reset']}"


def num(value: float) -> str:
    """Format a metric to four decimal places."""
    return f"{value:.4f}"


def pct(value: float) -> str:
    """Format a ratio as a whole percentage."""
    return f"{value * 100:.0f}%"


def bar(value: float, width: int = 8) -> str:
    """Render a value between 0 and 1 as blocks, so a column of strata scans at a glance."""
    clamped = min(max(value, 0.0), 1.0)
    filled = round(clamped * width)
    return "█" * filled + "░" * (width - filled)


def heading(text: str) -> str:
    """A dim section heading with a blank line above it."""
    return f"\n  {paint('dim', text)}\n"
