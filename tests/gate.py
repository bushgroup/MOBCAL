"""The regression gate's two list files, its tier-1 filter, and the shared run pool's types.

The choline runs themselves go through ``mobcal.run`` from the session fixture in
``conftest.py``; what lives here is what the comparison needs beyond that: the stochastic-lines
list and the filter that applies it, the strict-platforms list, the key this platform is listed
under, where the references are, the line a split run's worker adds to its output, and the
dataclasses the pool fixture hands the tests.
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

PROVENANCE = re.compile(r"^ blocks of imp trajectories: ")
CYCLE = (10, 10)
"""The one-cycle check's worker, (W, w). A split deals block k = (ig - 1)*itn + ic to worker
(k - 1) mod W + 1, so at the 2012 ``itn = 10`` worker w of 10 integrates exactly cycle w."""


@dataclass(frozen=True)
class GateRun:
    gas: str
    ref: OutFile
    new: OutFile


@dataclass(frozen=True)
class WorkerRun:
    """One worker of a split choline run, run alone: the reference it answers to, its exit
    status, the binary's wall time, its output (None if it wrote none) and its console."""
    gas: str
    ref: OutFile
    returncode: int
    seconds: float
    out: OutFile | None
    log: str


@dataclass(frozen=True)
class Pool:
    """What the session built and ran: one binary per gas a selected test needs, the serial
    choline run per selected gas, the split choline runs in helium per selected worker count,
    and the one-cycle worker run per gas checked that way."""
    binaries: dict[str, Path]
    runs: dict[str, GateRun] = field(default_factory=dict)
    splits: dict[int, Result] = field(default_factory=dict)
    cycles: dict[str, WorkerRun] = field(default_factory=dict)

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


def provenance(integrated: int, read: int, empty: int, me: int, total: int) -> str:
    """The line a split run's worker (``me`` >= 1) or combining run (0) prints after the cycle
    loop, once per coordinate set."""
    return (f" blocks of imp trajectories: integrated{integrated:4d}, read from files{read:4d},"
            f" empty{empty:4d} (worker{me:3d} of{total:3d})")


def strict_platforms(path: Path = STRICT_PLATFORMS) -> set[str]:
    return {s.strip() for s in _entries(path)}


def platform_key() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)
