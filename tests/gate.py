"""The regression gate's two list files and its tier-1 filter.

The choline runs themselves go through ``mobcal.run``; what lives here is what the comparison
needs beyond that: the stochastic-lines list and the filter that applies it, the strict-platforms
list, and the key this platform is listed under.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STOCHASTIC_LINES = HERE / "stochastic-lines.txt"
STRICT_PLATFORMS = HERE / "strict-platforms.txt"
PLATFORMS = ("linux", "macos", "windows")


def _entries(path: Path) -> list[str]:
    """Non-blank lines of a list file that are not ``#`` comments."""
    return [s for s in path.read_text(encoding="utf-8").splitlines()
            if s.strip() and not s.lstrip().startswith("#")]


def stochastic_patterns(path: Path = STOCHASTIC_LINES) -> list[re.Pattern[str]]:
    return [re.compile(s) for s in _entries(path)]


def deterministic(lines: list[str], patterns: list[re.Pattern[str]]) -> list[str]:
    """The lines no stochastic pattern matches, in order.

    A blank line directly before a matched line goes with it: the energy-conservation
    diagnostics each open with one, and how many of them a run prints depends on the stream.
    """
    drop = [any(p.search(x) for p in patterns) for x in lines]
    for i in range(len(lines) - 1):
        if not lines[i].strip() and drop[i + 1]:
            drop[i] = True
    return [x for x, d in zip(lines, drop, strict=True) if not d]


def strict_platforms(path: Path = STRICT_PLATFORMS) -> set[str]:
    return {s.strip() for s in _entries(path)}


def platform_key() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)
