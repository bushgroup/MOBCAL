"""Stage choline, run a built binary on it, and read the gate's two list files.

The thin subprocess helper the regression test uses until the process-fanout driver (lab record,
task 05) exists and the test moves onto it. One run, one directory: the program reads
``mobcal.in`` from its working directory and writes a scratch file ``hold`` there.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from mobcal import fortran

HERE = Path(__file__).resolve().parent
STOCHASTIC_LINES = HERE / "stochastic-lines.txt"
STRICT_PLATFORMS = HERE / "strict-platforms.txt"
PLATFORMS = ("linux", "macos", "windows")


@dataclass(frozen=True)
class Run:
    out: Path
    returncode: int
    seconds: float  # wall time of the binary alone
    log: str  # what the binary wrote to stdout and stderr


def run_choline(binary: Path, run_dir: Path, staged_name: str, seed: int) -> Run:
    """Copy ``fortran/Choline.mfj`` into ``run_dir`` as ``staged_name`` and run it at ``seed``.

    The references echo the name the input had in 2012, so the input is staged under that name
    rather than either side being edited. ``mobcal.in`` is three records -- input file, output
    file, seed -- and the two filename fields are read with an ``a30`` edit descriptor, so
    neither may exceed 30 characters.
    """
    if len(staged_name) > 30:
        raise ValueError(f"{staged_name!r} is longer than the a30 field that reads it")
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fortran.FORTRAN_DIR / "Choline.mfj", run_dir / staged_name)
    (run_dir / "mobcal.in").write_text(f"{staged_name}\ngate.out\n{seed}\n", newline="\n")
    t0 = time.perf_counter()
    proc = subprocess.run([str(binary)], cwd=run_dir, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace")
    return Run(run_dir / "gate.out", proc.returncode, time.perf_counter() - t0, proc.stdout)


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
