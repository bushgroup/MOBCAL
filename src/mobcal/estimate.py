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
and seconds per trajectory, on one workstation (Windows 11, 2 x 18 cores, 72 threads, MSYS2
gfortran 16.2.0, the recorded flags) with 36 runs at once, every physical core busy. Helium
rests on choline, carbon globules of 30 to 300 atoms and protein ions of 433, 1,236 and 5,220
atoms (4+, 5+ and 12+); nitrogen on choline and the two smaller protein ions. Between points
the model interpolates on log-log axes and beyond them, past 5,220 atoms in helium and 1,236 in
nitrogen, extrapolates with the end slope; a gas with fewer points borrows helium's slopes. In
helium ``PROJECTION_SHARE`` of the prologue scales with ``inum``.

The curve reads atoms only, so one curve per gas costs every input, whatever its charge. In
helium the protein ions sit near the globules and every point predicted from the others is
within 15 %; past the last point the end slope runs high, a 10,000-atom globule 36 % in the
prologue and 53 % per trajectory. In nitrogen a protein ion's prologue is 3.7 times a 300-atom
globule's at 1.44 times the atoms, and the curve follows the protein ions: a singly charged
input between 100 and 1,000 atoms is costed 1.7 to 2.3 times its prologue and 1.25 to 1.65
times its trajectories, and the 1,236-atom ion predicted from the other two is 33 % high in
the prologue. ``COSTS``' comment gives every point's error (lab record, task 52).

A machine slower or faster than that workstation scales every number, which is why the estimate
is printed as "about". With fewer runs at once than cores a trajectory costs less (11 to 30 %
between a quarter and every core busy on an earlier 40-core workstation), and with every
hyperthread busy as well each run takes about 1.5 times as long.

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
  runs than that is run as ``throughput`` runs it. On 40 cores choline in helium goes two at a
  time across 20 processes, in nitrogen one at a time across 40, as does the 433-atom ion in
  nitrogen; on 8 cores each goes one at a time across 8.

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

from mobcal.io.ion import IonError
from mobcal.io.mfj import MfjError
from mobcal.run import Job, cores
from mobcal.run import size as input_size
from mobcal.settings import DEFAULTS, Settings

# (atoms, prologue seconds per coordinate set at inum 250,000, seconds per trajectory). Measured
# 2026-11-11 and -12 as serial runs at two values of imp, two repeats, minimum wall, with 36 runs
# at once throughout on the 36 physical cores (lab record, task 52): choline (21 atoms), carbon
# globules of 30 to 300 atoms (tests/synthetic.py, helium only), and protein ions from PDB 2MLT
# (433 atoms, 4+), 1UBQ (1,236, 5+) and 1BSY (5,220, 12+, helium only). Each point predicted
# from the others (leave one out), prologue / per trajectory: helium within 15 % (the 5,220-atom
# ion -15 / +9 %); nitrogen choline +128 / -8 %, the 433-atom ion -19 / +2 %, the 1,236-atom ion
# +33 / -3 %. Out of sample: the 2000 release's 104-atom example -21 / +21 % in helium and
# +83 / +41 % in nitrogen; the 1,000-atom globule +10 / +19 % and +129 / +65 %; the 10,000-atom
# helium globule +36 / +53 %, past the last point.
COSTS: dict[str, tuple[tuple[int, float, float], ...]] = {
    "he": ((21, 1.81, 4.17e-4), (30, 2.65, 5.54e-4), (100, 7.68, 1.81e-3),
           (300, 23.2, 5.76e-3), (433, 36.3, 8.82e-3), (1236, 106.0, 3.21e-2),
           (5220, 552.0, 0.174)),
    "n2": ((21, 6.80, 1.01e-2), (433, 359.0, 0.351), (1236, 1070.0, 1.24)),
}
# (atoms, the slowest velocity point's block over the mean block). Measured 2026-11-11 and -12
# from the block files of one split run per ion at 36 processes, 2/40/1000, on the same machine
# (lab record, task 52; choline in helium the mean of four runs, 1.66 to 2.06).
SLOWEST: dict[str, tuple[tuple[int, float], ...]] = {
    "he": ((21, 1.827), (433, 2.419), (1236, 2.366), (5220, 2.9)),
    "n2": ((21, 3.615), (433, 4.475), (1236, 4.32)),
}
PROJECTION_SHARE = 0.73  # of the helium prologue that scales with inum: 0.59 to 0.84 measured
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
            sizes[job.input] = input_size(job.input)
        except (OSError, MfjError, IonError):
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
