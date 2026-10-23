"""The regression gate's two list files, its tier-1 filter, and the shared run pool's types.

The choline runs themselves go through ``mobcal.run`` from the session fixture in
``conftest.py``; what lives here is what the comparison needs beyond that: the stochastic-lines
list and the filter that applies it, the strict-platforms list, the key this platform is listed
under, where the references are (``tests/reference/``, derived from the 2012 originals under
``fortran/sample-output/`` by two changes of print format that ``test_reference.py`` checks),
the line a split run's worker adds to its output, and the dataclasses the pool fixture hands
the tests.
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

ORIGINALS = fortran.FORTRAN_DIR / "sample-output"
"""The 2012 outputs, never edited."""
REFS = HERE / "reference"
"""What the gate compares with: the 2012 outputs as the current programs print them, tied to
``ORIGINALS`` line by line by ``test_reference.py``."""
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
    the one-cycle worker run per gas checked that way, and the choline runs in helium under
    Philox per selected worker count (0 is the serial run)."""
    binaries: dict[str, Path]
    runs: dict[str, GateRun] = field(default_factory=dict)
    splits: dict[int, Result] = field(default_factory=dict)
    cycles: dict[str, WorkerRun] = field(default_factory=dict)
    philox: dict[int, Result] = field(default_factory=dict)

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


ATOMS = re.compile(r"^ number of atoms =\s*(\d+)$")
Q1ST_HEADER = " average values for q1st"
Q1ST_FACTOR = 4
"""inp / itn at the shipped settings: what the q1st column gained when its divisor was fixed."""


def ulp(token: str) -> float:
    """The unit in the last place of a value printed ``1pe11.4``: one in the fourth decimal of
    the mantissa."""
    return 10.0 ** (int(token[-3:]) - 4)


def q1st_bound(old: str) -> float:
    """How far a correctly rounded 4x-the-true value may print from 4x a 2012-format value.

    The old token is the true quarter rounded, so the true value is 4x it within 4 x half its
    unit; the new token is that true value rounded, within half its own unit. Where 4x keeps the
    exponent the sum is two and a half units of the new last digit; where it carries, under one.
    """
    return Q1ST_FACTOR * ulp(old) / 2 + ulp(f"{Q1ST_FACTOR * float(old):.4E}") / 2


def q1st_rows(lines: list[str]) -> list[int]:
    """The indices of the rows of every q1st table (gst2, wgst, q1st), one table per set."""
    rows = []
    for i, s in enumerate(lines):
        if s == Q1ST_HEADER:
            assert lines[i + 1] == "" and lines[i + 2].split() == ["gst2", "wgst", "q1st"]
            j = i + 3
            while j < len(lines) and lines[j].strip():
                rows.append(j)
                j += 1
    return rows


def _q1st_derives(old: str, new: str) -> bool:
    a, b = old.split(), new.split()
    return (len(a) == len(b) == 3 and a[:2] == b[:2]
            and abs(float(b[2]) - Q1ST_FACTOR * float(a[2])) <= q1st_bound(a[2]) * (1 + 1e-9))


def underived(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    """The lines of an output in the 2012 print format and of the current programs' output of
    the same run that differ other than by the two changes of print format made since.

    The changes: the atom count printed ``i7`` where 2012 printed ``i4``, and the q1st column
    divided by ``itn`` where 2012 divided by ``inp``, so ``Q1ST_FACTOR`` times larger, within
    ``q1st_bound``. Empty means the two are the same run printed two ways.
    """
    assert len(new) == len(old), (len(old), len(new))
    rows = q1st_rows(old)
    assert q1st_rows(new) == rows
    out = []
    for i, (a, b) in enumerate(zip(old, new, strict=True)):
        if a == b:
            continue
        m = ATOMS.match(a)
        if m and a == f" number of atoms ={int(m.group(1)):4d}" and \
                b == f" number of atoms ={int(m.group(1)):7d}":
            continue
        if i in rows and _q1st_derives(a, b):
            continue
        out.append((a, b))
    return out


def strict_platforms(path: Path = STRICT_PLATFORMS) -> set[str]:
    return {s.strip() for s in _entries(path)}


def platform_key() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)
