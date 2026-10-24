"""Synthetic ions of any size: carbon at protein density, for runs above choline's 21 atoms.

A globular protein packs about one atom per 20 Å^3 counting hydrogens. ``globule(n)`` takes the
``n`` points of a simple cubic lattice of that density (spacing 20^(1/3) Å) nearest its centre,
each moved by up to a quarter spacing per axis from a seeded generator, so the same ``n`` and
seed give the same coordinates on every platform. Every atom is carbon (key 12) with charge
1/n in ``equal`` mode, so the element rows are not the variable when the size is. The file has
five columns, which both programs read in every charge mode. ``run_until`` runs a binary on such
an input only as far as a given output line.
"""

from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from mobcal import parameters
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile

DENSITY = 1 / 20.0  # atoms per Å^3
SPACING = DENSITY ** (-1 / 3)
CARBON = 12


def globule(n: int, seed: int = 19) -> list[tuple[float, float, float]]:
    """``n`` atom positions in Å, centred near the origin, nearest the centre first."""
    r = math.ceil((3 * n / (4 * math.pi * DENSITY)) ** (1 / 3) / SPACING) + 2
    sites = [(i, j, k) for i in range(-r, r + 1) for j in range(-r, r + 1)
             for k in range(-r, r + 1)]
    sites.sort(key=lambda s: (s[0] ** 2 + s[1] ** 2 + s[2] ** 2, s))
    assert len(sites) >= n
    rng = random.Random(seed)
    jitter = SPACING / 4
    return [(SPACING * i + rng.uniform(-jitter, jitter),
             SPACING * j + rng.uniform(-jitter, jitter),
             SPACING * k + rng.uniform(-jitter, jitter)) for i, j, k in sites[:n]]


OUTLIER_DIRECTION = (0.6, 0.48, 0.64)
"""A unit vector off every axis. An outlier on +x puts the farthest atom where MOBIL2's x-axis
orientation needs a rotation of almost nothing, which the binary computes to ~1e-11 rad; at a
100 Å radius that is past the check's absolute 1e-20 m and the program refuses the ion
(``Problem orientating along x axis``), a 2012 property unrelated to what an outlier is for."""


def outlier(core: list[tuple[float, float, float]], gap: float = 8.0) -> tuple[float, ...]:
    """A point ``gap`` Å beyond the farthest atom of ``core``, along ``OUTLIER_DIRECTION``, so
    that it is the farthest atom of the ion it joins."""
    r = max(math.sqrt(x * x + y * y + z * z) for x, y, z in core) + gap
    return tuple(r * c for c in OUTLIER_DIRECTION)


def mfj_text(atoms: list[tuple[float, float, float]], label: str) -> str:
    """One coordinate set, Å, ``equal`` charges, carbon throughout."""
    q = 1.0 / len(atoms)
    rows = [f" {x:.4f} {y:.4f} {z:.4f} {CARBON} {q:.8e}" for x, y, z in atoms]
    return "\n".join([label[:30], "1", str(len(atoms)), "ang", "equal", "1.0000", *rows]) + "\n"


def write(path: Path, atoms: list[tuple[float, float, float]], label: str) -> Path:
    path.write_text(mfj_text(atoms, label), encoding="latin-1", newline="\n")
    return path


@dataclass(frozen=True)
class Partial:
    """A run stopped at a line: the seconds until the line was written (or the process ended),
    the exit status if it ended by itself (None if it was stopped), and the output so far."""
    seconds: float
    returncode: int | None
    lines: list[str]


def run_until(binary: Path, d: Path, mfj: Path, until: str, gas: str = "he",
              seed: int = 5013489, generator: str = "ranlux", timeout: float = 3600.0,
              poll: float = 0.5) -> Partial:
    """Run ``binary`` serially on ``mfj`` in ``d`` and stop it once its output holds a line
    starting with ``until``.

    The trajectory method's Monte Carlo is days for a large ion, while what comes before it --
    the reader, the projection and hard-sphere pass, the orientation and the potential scans --
    is minutes; this runs the latter alone. gfortran buffers a file's lines unless
    ``GFORTRAN_UNBUFFERED_ALL`` is set, so it is, and the output is read as it is written.
    """
    d.mkdir(parents=True, exist_ok=True)
    staged = d / mfj.name
    if staged.resolve() != mfj.resolve():
        shutil.copyfile(mfj, staged)
    InFile(mfj.name, "out.txt", seed, None, generator).write(d)
    parameters.shipped(gas).render(d)
    out = d / "out.txt"
    out.unlink(missing_ok=True)  # an earlier run's output would be read as this one's
    env = dict(os.environ, GFORTRAN_UNBUFFERED_ALL="y")
    t0 = time.perf_counter()
    with open(d / "stdout.log", "wb") as log:
        proc = subprocess.Popen([str(binary)], cwd=d, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env)
        try:
            while True:
                rc = proc.poll()
                lines = OutFile.read(out).lines if out.is_file() else []
                if any(s.startswith(until) for s in lines) or rc is not None:
                    seconds = time.perf_counter() - t0
                    return Partial(seconds, rc, lines)
                if time.perf_counter() - t0 > timeout:
                    raise TimeoutError(f"no line {until!r} in {timeout:.0f} s: {lines[-3:]}")
                time.sleep(poll)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
