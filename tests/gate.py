"""The regression gate's two list files, its tier-1 filter, and the shared run pool's types.

The choline runs themselves go through ``mobcal.run`` from the session fixture in
``conftest.py``; what lives here is what the comparison needs beyond that: the stochastic-lines
list and the filter that applies it, the strict-platforms list, the key this platform is listed
under, where the references are, and the dataclasses the pool fixture hands the tests.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mobcal import fortran
from mobcal.io.outfile import OutFile
from mobcal.run import Job, Result

HERE = Path(__file__).resolve().parent
STOCHASTIC_LINES = HERE / "stochastic-lines.txt"
STRICT_PLATFORMS = HERE / "strict-platforms.txt"
PLATFORMS = ("linux", "macos", "windows")

REFS = fortran.FORTRAN_DIR / "sample-output"
REFERENCE = {"he": "Choline_He.out", "n2": "Choline_N2.out"}
CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"


@dataclass(frozen=True)
class GateRun:
    gas: str
    ref: OutFile
    new: OutFile


@dataclass(frozen=True)
class Pool:
    """What the session built and ran: one binary per selected gas, the serial choline run per
    gas, and the split choline runs in helium per selected worker count."""
    binaries: dict[str, Path]
    runs: dict[str, GateRun] = field(default_factory=dict)
    splits: dict[int, Result] = field(default_factory=dict)

    def launcher(self, job: Job) -> list[str]:
        return [str(self.binaries[job.gas])]


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
