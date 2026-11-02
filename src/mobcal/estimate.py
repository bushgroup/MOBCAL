"""How long a batch will take, and how it uses the cores: the estimate and ``--split auto``.

A run costs, per coordinate set, a part every process pays before its first trajectory and a
part proportional to the trajectories of the trajectory method. The first is the reader, the
asymmetry scan, in helium the projection and hard-sphere pass (``inum`` trajectories), the
orientation, the velocity grid and the b2max search; the second is ``itn * inp * imp``
trajectories at a cost per trajectory that grows with the atom count. A serial run pays
``prologue + trajectories``. A run split across W processes pays the prologue in every worker
and once more in the combining run, and its workers, claiming blocks slowest velocity point
first, end within a fraction of a block of each other unless one block outlasts the even
share, so its wall is ``2 * prologue + max(trajectories / W, floor)``, the floor being the
costliest block (the slowest velocity point's, ``SLOWEST`` times the mean block, summed over
the sets). Measured (lab record, task 47: the claimed dealing on one workstation, choline in
helium and nitrogen at W = 10, 20 and 40 and a 433-atom protein ion in nitrogen at W = 20 and
40) this is within -14 to +4 % of every wall given each run's own costs; without the floor the
protein ion at W = 40 was 39 % under. Splitting therefore pays when the trajectories dominate
and not when the prologue does (the 2000 release's example at ``imp`` 25 is the latter), not
past ``trajectories / floor`` processes, and never past about 25 times however many are given.

``COSTS`` holds the measured points per gas: atoms, the prologue per set at the 2012 ``inum``,
and seconds per trajectory, on one workstation (Windows 11, 80 threads, MSYS2 gfortran 16.2.0,
the recorded flags). Between points the model interpolates on log-log axes and beyond them
extrapolates with the end slope; a gas with fewer points borrows helium's slopes. In helium
``PROJECTION_SHARE`` of the prologue scales with ``inum``. A machine slower or faster than that
workstation scales every number, which is why the estimate is printed as "about". The costs
hold with a core per process: with every core busy a trajectory costs 11 to 30 % more on that
workstation, and with every hyperthread busy as well each run takes about 1.5 times as long.
The carbon globules carry no charge, and a charged protein ion of 433 atoms in nitrogen costs
1.6 to 1.9 times what the curve gives (lab record, task 52, open).

``allocate`` is ``--split auto`` and the window's default, in one of three ``MODES``, counting
physical cores (``mobcal.run.cores``). A run is split only when the model says that saves at
least a fifth of its wall (``MIN_GAIN``), and across at most ``MAX_SPLIT`` processes, the
blocks it has, and ``trajectories / floor`` rounded up.

- ``throughput``: with at least as many runs as cores, one process per run; with fewer, every
  run at once, each split across its share of the cores. Nothing finishes before the first
  wave, which on a long batch is hours.
- ``in-order``: one run at a time across every core it can use; cores it cannot use (the floor
  cap) take further runs at the same split.
- ``balanced`` (the default): the fewest runs at once whose share of the cores keeps every
  run's efficiency, serial wall / (W * split wall), at least ``BALANCE``; a batch of no more
  runs than that is run as ``throughput`` runs it. On a 40-core workstation choline in helium
  goes three at a time across 13 processes, in nitrogen one at a time across 40, and the
  433-atom ion two at a time across 19; on 8 cores each goes one at a time across 8.

Split equals serial to the bit, so the rule moves time and never a number.

    from mobcal import estimate
    plan = estimate.allocate(jobs, mode="balanced")
    print(estimate.describe(plan))
"""

from __future__ import annotations

import dataclasses
import heapq
import math
from collections.abc import Sequence
from dataclasses import dataclass

from mobcal.io.mfj import Mfj, MfjError
from mobcal.run import Job, cores
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
# (atoms, the slowest velocity point's block over the mean block). Measured 2026-11-01 and -02
# from the block files of split runs (lab record, tasks 46 and 47): choline 1.96 in helium and
# 3.0 to 3.4 in nitrogen; a 433-atom protein ion 4+ in nitrogen 4.3 to 4.6.
SLOWEST: dict[str, tuple[tuple[int, float], ...]] = {
    "he": ((21, 2.0),),
    "n2": ((21, 3.4), (433, 4.4)),
}
PROJECTION_SHARE = 0.77  # of the helium prologue that scales with inum: 0.72 to 0.78 measured
MAX_SPLIT = 40  # past this the shares are under ten blocks and the doubled prologue dominates
MIN_GAIN = 0.8  # split only when the split wall is at most this fraction of the serial wall
BALANCE = 0.7  # the balanced mode's least efficiency, serial wall / (W * split wall)

IN_ORDER, BALANCED, THROUGHPUT = "in-order", "balanced", "throughput"
MODES = (IN_ORDER, BALANCED, THROUGHPUT)
DEFAULT_MODE = BALANCED
MODE_TITLES = {IN_ORDER: "Finish in order", BALANCED: "Balanced", THROUGHPUT: "Most throughput"}


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
    floor: float = 0.0  # seconds of the costliest block, summed over the sets

    def wall(self, split: int | None = None) -> float:
        if not split or split == 1:
            return self.prologue + self.trajectories
        return 2 * self.prologue + max(self.trajectories / split, self.floor)

    def efficiency(self, split: int) -> float:
        """Serial wall / (W * split wall): 1 for a run that loses nothing to the split."""
        return self.wall() / (split * self.wall(split))

    @property
    def widest(self) -> float:
        """The split past which the floor holds the wall: trajectories / floor."""
        return self.trajectories / self.floor if self.floor else math.inf


def slowest(gas: str, atoms: int) -> float:
    """The slowest velocity point's block over the mean block (``SLOWEST``)."""
    pts = SLOWEST[gas] if gas in SLOWEST else SLOWEST["he"]
    return _interp([(float(a), k) for a, k in pts], atoms)


def cost(atoms: int, sets: int, gas: str, settings: Settings = DEFAULTS) -> Cost:
    prologue = _curve(gas, 1, atoms)
    if gas == "he":
        prologue *= (1 - PROJECTION_SHARE) + PROJECTION_SHARE * settings.inum / DEFAULTS.inum
    tau = _curve(gas, 2, atoms)
    return Cost(sets * prologue, sets * settings.points * tau,
                sets * slowest(gas, atoms) * settings.imp * tau)


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
    mode: str | None = None  # the mode that chose the allocation; None when set by hand

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
    return Plan(tuple(jobs), workers, cpus or cores(), walls, seconds, prologue)


def _split(job: Job, c: Cost | None, share: int) -> int | None:
    """The split a job takes on ``share`` cores, None for one process: at most ``MAX_SPLIT``,
    its blocks and the floor's widest split, and only when it saves ``1 - MIN_GAIN``."""
    if c is None:
        return None
    w = min(share, MAX_SPLIT, job.settings.blocks_per_set, math.ceil(c.widest))
    return w if (w > 1 and c.wall(w) <= MIN_GAIN * c.wall()) else None


def _balanced_runs(jobs: Sequence[Job], costs: Sequence[Cost | None], cpus: int) -> int:
    """The fewest runs at once whose share of the cores keeps every job's efficiency at least
    ``BALANCE``; a job that would not split constrains nothing."""
    for n in range(1, cpus + 1):
        splits = [_split(j, c, cpus // n) for j, c in zip(jobs, costs, strict=True)]
        if all(w is None or c.efficiency(w) >= BALANCE
               for w, c in zip(splits, costs, strict=True)):
            return n
    return cpus


def allocate(jobs: Sequence[Job], cpus: int | None = None, sizes: dict | None = None,
             mode: str = DEFAULT_MODE) -> Plan:
    """``--split auto``: how many runs at once and each one's split, with the estimate, in one
    of ``MODES``."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}, not {mode!r}")
    cpus = max(1, cpus or cores())
    jobs = list(jobs)
    if not jobs:
        return Plan((), 1, cpus, (), 0.0, 0.0, mode)
    sizes = {} if sizes is None else sizes
    costs = [job_cost(j, sizes) for j in jobs]
    runs = {IN_ORDER: lambda: 1, BALANCED: lambda: _balanced_runs(jobs, costs, cpus),
            THROUGHPUT: lambda: len(jobs)}[mode]()
    if mode != IN_ORDER and len(jobs) <= runs:  # throughput, or balanced with few runs
        if len(jobs) >= cpus:
            out = [dataclasses.replace(j, split=None) for j in jobs]
            return dataclasses.replace(plan(out, cpus, cpus, sizes), mode=mode)
        share = cpus // len(jobs)
        out = [dataclasses.replace(j, split=_split(j, c, share))
               for j, c in zip(jobs, costs, strict=True)]
        return dataclasses.replace(plan(out, len(out), cpus, sizes), mode=mode)
    out = [dataclasses.replace(j, split=_split(j, c, cpus // runs))
           for j, c in zip(jobs, costs, strict=True)]
    widest = max(j.split or 1 for j in out)
    workers = min(len(out), max(runs, cpus // widest))  # cores a run cannot use take another
    return dataclasses.replace(plan(out, workers, cpus, sizes), mode=mode)


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
    if p.mode:
        how += f" ({MODE_TITLES[p.mode].lower()})"
    if any(w is None for w in p.walls):
        return how + "; no estimate for an input that cannot be read"
    line = f"{how}; about {duration(p.seconds)}"
    if p.prologue >= 60:
        line += (f", of which about {duration(p.prologue)} per process before its first "
                 "trajectory (reading the ion and the projection pass, repeated by every "
                 "process of a split)")
    return line
