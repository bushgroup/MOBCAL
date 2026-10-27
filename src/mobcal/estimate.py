"""How long a batch will take, and how it uses the cores: the estimate and ``--split auto``.

A run costs, per coordinate set, a part every process pays before its first trajectory and a
part proportional to the trajectories of the trajectory method. The first is the reader, the
asymmetry scan, in helium the projection and hard-sphere pass (``inum`` trajectories), the
orientation, the velocity grid and the b2max search; the second is ``itn * inp * imp``
trajectories at a cost per trajectory that grows with the atom count. A serial run pays
``prologue + trajectories``. A run split across W processes pays the prologue in every worker
and once more in the combining run, so its wall is ``2 * prologue + trajectories / W``
(``notes``: within-run parallelism, measured within 10 % of this at W = 10 and 20 for choline
and at W = 40 for a 1e4-atom ion). Splitting therefore pays when the trajectories dominate and
not when the prologue does (the 2000 release's example at ``imp`` 25 is the latter), and never
past about 25 times however many processes are given: the doubled prologue is the floor.

``COSTS`` holds the measured points per gas: atoms, the prologue per set at the 2012 ``inum``,
and seconds per trajectory, on one workstation (Windows 11, 80 threads, MSYS2 gfortran 16.2.0,
the recorded flags). Between points the model interpolates on log-log axes and beyond them
extrapolates with the end slope; a gas with fewer points borrows helium's slopes. In helium
``PROJECTION_SHARE`` of the prologue scales with ``inum``. A machine slower or faster than that
workstation scales every number, which is why the estimate is printed as "about".

``allocate`` is ``--split auto`` and the window's default: with at least as many runs as cores,
one process per run; with fewer, every run at once, each split across its share of the cores
(at most ``MAX_SPLIT``) when the model says splitting saves at least a fifth of its wall.
Split equals serial to the bit, so the rule moves time and never a number.

    from mobcal import estimate
    plan = estimate.allocate(jobs, cpus=os.cpu_count())
    print(estimate.describe(plan))
"""

from __future__ import annotations

import dataclasses
import heapq
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass

from mobcal.io.mfj import Mfj, MfjError
from mobcal.run import Job
from mobcal.settings import DEFAULTS, Settings

# (atoms, prologue seconds per coordinate set at inum 250,000, seconds per trajectory). Measured
# 2026-10-26 as serial runs at two values of imp, two repeats, minimum wall, 28 runs at once:
# choline (21 atoms) and carbon globules of 30 to 1,000 atoms (tests/synthetic.py). The 10,000-
# atom helium point is a 40-way split of 2026-10-23, scaled by the ratio of the two measurements
# at 1,000 atoms. Out of sample, the 2000 release's 104-atom example lies within 10 % of the
# curve per set, and the model is 5 to 20 % above single serial runs of choline in both gases
# and of that example, which ran with less else on the machine.
COSTS: dict[str, tuple[tuple[int, float, float], ...]] = {
    "he": ((21, 2.25, 4.81e-4), (30, 3.10, 6.24e-4), (100, 9.08, 2.06e-3),
           (300, 26.6, 6.43e-3), (1000, 90.4, 2.31e-2), (10000, 1017.0, 0.272)),
    "n2": ((21, 7.78, 1.148e-2), (30, 11.55, 1.673e-2), (100, 37.5, 5.56e-2),
           (300, 117.3, 0.1744)),
}
PROJECTION_SHARE = 0.77  # of the helium prologue that scales with inum: 0.72 to 0.78 measured
MAX_SPLIT = 40  # past this the shares are under ten blocks and the doubled prologue dominates
MIN_GAIN = 0.8  # split only when the split wall is at most this fraction of the serial wall


def _interp(points: Sequence[tuple[float, float]], x: float) -> float:
    """Piecewise log-log interpolation through ``points`` (sorted by x), end slopes outside."""
    if len(points) == 1:
        return points[0][1]
    i = max([k for k in range(len(points) - 1) if points[k][0] <= x], default=0)
    (x0, y0), (x1, y1) = points[i], points[i + 1]
    k = (math.log(y1) - math.log(y0)) / (math.log(x1) - math.log(x0))
    return math.exp(math.log(y0) + k * (math.log(x) - math.log(x0)))


def _curve(gas: str, column: int, atoms: int) -> float:
    pts = COSTS[gas]
    if len(pts) >= 2:
        return _interp([(p[0], p[column]) for p in pts], atoms)
    # one point: helium's shape through this gas's point
    he = [(p[0], p[column]) for p in COSTS["he"]]
    return pts[0][column] * _interp(he, atoms) / _interp(he, pts[0][0])


@dataclass(frozen=True)
class Cost:
    """One run's cost on the reference workstation, all coordinate sets."""
    prologue: float  # seconds each process pays before its trajectories
    trajectories: float  # seconds of the trajectory method, serial

    def wall(self, split: int | None = None) -> float:
        if not split or split == 1:
            return self.prologue + self.trajectories
        return 2 * self.prologue + self.trajectories / split


def cost(atoms: int, sets: int, gas: str, settings: Settings = DEFAULTS) -> Cost:
    prologue = _curve(gas, 1, atoms)
    if gas == "he":
        prologue *= (1 - PROJECTION_SHARE) + PROJECTION_SHARE * settings.inum / DEFAULTS.inum
    tau = _curve(gas, 2, atoms)
    return Cost(sets * prologue, sets * settings.points * tau)


def job_cost(job: Job, sizes: dict | None = None) -> Cost | None:
    """The cost of a job from its input's size; None when the input cannot be read (the
    driver will report why). ``sizes`` caches (atoms, sets) by input path."""
    sizes = {} if sizes is None else sizes
    if job.input not in sizes:
        try:
            m = Mfj.read(job.input)
            sizes[job.input] = (m.atoms, m.coordinate_sets)
        except (OSError, MfjError):
            sizes[job.input] = None
    size = sizes[job.input]
    return None if size is None else cost(*size, job.gas, job.settings)


@dataclass(frozen=True)
class Plan:
    jobs: tuple[Job, ...]  # as they will run, each with its split
    workers: int  # runs in flight at once
    cpus: int
    walls: tuple[float | None, ...]  # each job's estimated wall, None if unknown
    seconds: float  # the batch's estimated wall
    prologue: float  # the longest per-process prologue in the batch

    @property
    def processes(self) -> int:
        """The most processes the plan has running at once (a split job is W of them)."""
        widths = sorted((j.split or 1 for j in self.jobs), reverse=True)
        return sum(widths[: self.workers])


def _makespan(walls: Sequence[float], workers: int) -> float:
    """Jobs started in order, each when one of ``workers`` slots frees, as run_many does."""
    slots = [0.0] * max(1, workers)
    for w in walls:
        t = heapq.heappop(slots)
        heapq.heappush(slots, t + w)
    return max(slots)


def plan(jobs: Sequence[Job], workers: int, cpus: int | None = None,
         sizes: dict | None = None) -> Plan:
    """The estimate for jobs as given (each with its own split, or none) at ``workers``.
    ``sizes`` maps an input's path to its (atoms, sets) where the caller knows them already;
    any other input is read."""
    sizes = {} if sizes is None else sizes
    costs = [job_cost(j, sizes) for j in jobs]
    walls = tuple(None if c is None else c.wall(j.split) for j, c in zip(jobs, costs, strict=True))
    seconds = _makespan([w or 0.0 for w in walls], workers)
    prologue = max((c.prologue for c in costs if c is not None), default=0.0)
    return Plan(tuple(jobs), workers, cpus or os.cpu_count() or 1, walls, seconds, prologue)


def allocate(jobs: Sequence[Job], cpus: int | None = None, sizes: dict | None = None) -> Plan:
    """``--split auto``: how many runs at once and each one's split, with the estimate."""
    cpus = max(1, cpus or os.cpu_count() or 1)
    jobs = list(jobs)
    if not jobs:
        return Plan((), 1, cpus, (), 0.0, 0.0)
    if len(jobs) >= cpus:
        return plan([dataclasses.replace(j, split=None) for j in jobs], cpus, cpus, sizes)
    share = min(cpus // len(jobs), MAX_SPLIT)
    sizes = {} if sizes is None else sizes
    out = []
    for j in jobs:
        c = job_cost(j, sizes)
        w = min(share, j.settings.blocks_per_set)
        split = w if (c is not None and w > 1 and c.wall(w) <= MIN_GAIN * c.wall()) else None
        out.append(dataclasses.replace(j, split=split))
    return plan(out, len(out), cpus, sizes)


def duration(seconds: float) -> str:
    """``40 s``, ``12 min``, ``3.5 h``, ``2.1 days``: two significant figures at most."""
    if seconds < 90:
        return f"{max(1, round(seconds, -1 if seconds >= 20 else 0)):.0f} s"
    if seconds < 90 * 60:
        return f"{round(seconds / 60):.0f} min"
    if seconds < 48 * 3600:
        h = seconds / 3600
        return f"{h:.1f} h" if h < 10 else f"{h:.0f} h"
    return f"{seconds / 86400:.1f} days"


def describe(p: Plan) -> str:
    """One line for the command line and the window: the allocation and the estimate."""
    n = len(p.jobs)
    splits = sorted({j.split for j in p.jobs if j.split})
    how = f"{n} run{'s' if n != 1 else ''} on {p.workers} worker{'s' if p.workers != 1 else ''}"
    if splits:
        across = splits[0] if len(splits) == 1 else f"{splits[0]} to {splits[-1]}"
        every = all(j.split for j in p.jobs)
        how += f", {'each' if every else 'some'} across {across} processes"
    if any(w is None for w in p.walls):
        return how + "; no estimate for an input that cannot be read"
    line = f"{how}; about {duration(p.seconds)}"
    if p.prologue >= 60:
        line += (f", of which about {duration(p.prologue)} per process before its first "
                 "trajectory (reading the ion and the projection pass, repeated by every "
                 "process of a split)")
    return line
