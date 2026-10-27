"""A batch: inputs, gases, seeds, a method and its fields, and a results folder, as data.

What the window's form makes, its queue holds and saves between launches, and the command
line builds from its options: a frozen, Qt-free description that turns into the driver's jobs.
Each field left as None takes the method's value (``mobcal.methods``), so a batch saved as
"MOBCAL 2000, these inputs" stays that, and a field set over the method makes the runs
``custom``, as their records will say. ``to_dict``/``from_dict`` are the queue file's form,
``format = 1``, paths as strings.

The results folder is a study's: every batch adds its run directories to it, and the summary
covers them all (``mobcal.run.Summary.write``). ``prior`` says, before a batch starts, which of
its runs the folder already holds: done (an ok record of the same input, by its SHA-256), not
done (a failed or stopped record), or a clash (a record of another input under the same name,
which this batch would overwrite).

    from mobcal.batch import Batch
    b = Batch((Path("choline.mfj"),), Path("results"), gases=("he", "n2"), method="2012")
    plan = b.plan()
    summary = run_many(plan.jobs, plan.workers)
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mobcal import estimate, fortran, methods, parameters, settings
from mobcal.run import RECORD_JSON, Job
from mobcal.settings import Settings, Source

FORMAT = 1
DEFAULT_SEED = 5013489  # the seed the shipped mobcal.in carries, at which 2012 was run
AUTO = "auto"


class BatchError(ValueError):
    """A batch that cannot become runs: a method for another gas, an unknown table name."""


@dataclass(frozen=True)
class Batch:
    inputs: tuple[Path, ...]
    out_dir: Path
    gases: tuple[str, ...] = ("he",)
    seeds: tuple[int, ...] = (DEFAULT_SEED,)
    method: str = methods.CURRENT  # the method the fields start from
    parameters: str | None = None  # a shipped set's name or a file; None: the method's
    generator: str | None = None  # None: the method's
    settings: Settings | None = None  # None: the method's
    split: int | str | None = AUTO  # W, "auto" (mobcal.estimate.allocate), or None: serial
    workers: int | None = None  # runs in flight; None: the allocation's, or the CPU count
    skip_done: bool = False  # leave out, when the batch starts, runs the folder holds complete

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(Path(p) for p in self.inputs))
        object.__setattr__(self, "out_dir", Path(self.out_dir))
        object.__setattr__(self, "gases", tuple(self.gases))
        object.__setattr__(self, "seeds", tuple(int(s) for s in self.seeds))
        m = methods.get(self.method)
        bad = [g for g in self.gases if g not in fortran.GASES]
        if bad or not self.gases:
            raise BatchError(f"gases must be among {fortran.GASES}, not {self.gases!r}")
        if not self.seeds:
            raise BatchError("a batch needs at least one seed")
        try:
            for g in self.gases:
                m.check_gas(g)
        except methods.MethodError as e:
            raise BatchError(str(e)) from None
        if not (self.split in (None, AUTO) or (isinstance(self.split, int) and self.split >= 1)):
            raise BatchError(f"split must be a worker count, {AUTO!r} or None, not "
                             f"{self.split!r}")

    # --- what the runs use ---------------------------------------------------------------

    @property
    def resolved_generator(self) -> str:
        return self.generator or methods.get(self.method).generator

    @property
    def resolved_settings(self) -> Settings:
        if self.settings is not None:
            return self.settings
        m = methods.get(self.method)
        return settings.resolve(None, **m.overrides())

    def table(self, gas: str) -> Path | None:
        """The element table file for a gas, None for the gas's default set."""
        name = self.parameters if self.parameters is not None else methods.get(
            self.method).parameters
        if name == parameters.DEFAULT and self.parameters is None:
            return None
        try:
            return parameters.path_for(name, gas)
        except parameters.ParameterError as e:
            raise BatchError(str(e)) from None

    def jobs(self) -> list[Job]:
        """One job per input, gas and seed in that order, serial (``plan`` sets the split)."""
        gen, st = self.resolved_generator, self.resolved_settings
        tables = {g: self.table(g) for g in self.gases}
        return [Job(p, g, s, self.out_dir, parameters=tables[g], generator=gen, settings=st)
                for p in self.inputs for g in self.gases for s in self.seeds]

    def to_run(self) -> list[Job]:
        """The jobs, less those the folder holds complete when ``skip_done``."""
        jobs = self.jobs()
        if not self.skip_done:
            return jobs
        done = {p.job.label for p in prior(jobs) if p.kind == DONE}
        return [j for j in jobs if j.label not in done]

    def plan(self, cpus: int | None = None, jobs: Sequence[Job] | None = None,
             sizes: dict | None = None) -> estimate.Plan:
        """The jobs as they will run, the runs in flight and the estimate; of ``jobs`` (some
        of this batch's, say those the folder does not hold yet) when given. ``sizes`` as
        ``mobcal.estimate.plan`` takes it."""
        jobs = self.jobs() if jobs is None else list(jobs)
        if self.split == AUTO:
            p = estimate.allocate(jobs, cpus, sizes)
            return p if self.workers is None else estimate.plan(p.jobs, self.workers, cpus,
                                                                sizes)
        split = self.split if isinstance(self.split, int) and self.split > 1 else None
        jobs = [dataclasses.replace(j, split=split) for j in jobs]
        workers = self.workers or max(1, (cpus or os.cpu_count() or 1) // (split or 1))
        return estimate.plan(jobs, max(1, min(workers, len(jobs) or 1)), cpus, sizes)

    @property
    def method_now(self) -> str:
        """The method the runs will record: the method's own key while no field is set over
        it, and whatever the fields make otherwise (``custom`` unless they happen to make
        another method)."""
        names = {j.method for j in self.jobs()}
        return names.pop() if len(names) == 1 else methods.CUSTOM

    def title(self) -> str:
        """``MOBCAL 2012``, or ``Custom (from MOBCAL 2012)``: what the window shows."""
        now = self.method_now
        if now == self.method:
            return methods.TITLES[now]
        if now == methods.CUSTOM:
            return f"Custom (from {methods.TITLES[self.method]})"
        return methods.TITLES[now]

    # --- the queue file's form -----------------------------------------------------------

    def to_dict(self) -> dict:
        st = self.settings
        return {"format": FORMAT, "inputs": [str(p) for p in self.inputs],
                "out_dir": str(self.out_dir), "gases": list(self.gases),
                "seeds": list(self.seeds), "method": self.method,
                "parameters": self.parameters, "generator": self.generator,
                "settings": None if st is None else st.values(),
                "split": self.split, "workers": self.workers, "skip_done": self.skip_done}

    @classmethod
    def from_dict(cls, doc: dict) -> Batch:
        if doc.get("format") != FORMAT:
            raise BatchError(f"batch format {doc.get('format')!r}; this version reads "
                             f"{FORMAT}")
        st = doc.get("settings")
        if st is not None:
            given = {k: v for k, v in st.items() if v != getattr(settings.DEFAULTS, k)}
            st = Settings(**st, source=Source(overrides=given))
        try:
            return cls(inputs=tuple(doc["inputs"]), out_dir=Path(doc["out_dir"]),
                       gases=tuple(doc["gases"]), seeds=tuple(doc["seeds"]),
                       method=doc["method"], parameters=doc.get("parameters"),
                       generator=doc.get("generator"), settings=st,
                       split=doc.get("split", AUTO), workers=doc.get("workers"),
                       skip_done=bool(doc.get("skip_done", False)))
        except (KeyError, TypeError, settings.SettingsError, methods.MethodError) as e:
            raise BatchError(f"not a batch: {e}") from None


def save(batches: Sequence[Batch], path: Path) -> Path:
    """Write a queue file: the batches in order, JSON, UTF-8."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"format": FORMAT, "batches": [b.to_dict() for b in batches]},
                              indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load(path: Path) -> tuple[list[Batch], list[str]]:
    """Read a queue file: the batches that still read, and why each other one does not, so
    that one stale entry never loses the rest."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    batches, problems = [], []
    for i, d in enumerate(doc.get("batches", []), 1):
        try:
            batches.append(Batch.from_dict(d))
        except BatchError as e:
            problems.append(f"queued batch {i}: {e}")
    return batches, problems


# --- the results, one row per ion and gas ------------------------------------------------

@dataclass(frozen=True)
class Row:
    """One ion in one gas: its runs over the seeds, and what the window's table shows."""
    input: Path
    gas: str
    results: tuple  # mobcal.run.Result, in seed order

    @property
    def ok(self) -> tuple:
        return tuple(r for r in self.results if r.ok)

    def value(self, kind: str) -> str:
        """``55.40`` for one completed run, ``55.40 ± 0.12`` over several, empty for none."""
        vals = [r.cross_sections[kind] for r in self.ok if kind in r.cross_sections]
        return methods.summary_line(vals) if vals else ""

    @property
    def status(self) -> str:
        n, ok = len(self.results), len(self.ok)
        if ok == n:
            return "ok" if n == 1 else f"ok ({n} seeds)"
        bad = [r for r in self.results if not r.ok]
        word = "stopped" if all(r.stopped for r in bad) else "failed"
        return word if ok == 0 and n == 1 else f"{word} {n - ok} of {n}"

    @property
    def message(self) -> str:
        return next((r.message for r in self.results if not r.ok and r.message), "")

    @property
    def seconds(self) -> float:
        return sum(r.seconds for r in self.results)

    @property
    def run_dir(self) -> Path:
        return self.results[0].job.run_dir

    @property
    def output(self) -> Path | None:
        return next((r.output for r in self.results if r.output), None)


def rows(results: Sequence) -> list[Row]:
    """Results grouped by input and gas, in the order each pair first appears."""
    groups: dict[tuple[Path, str], list] = {}
    for r in results:
        groups.setdefault((r.job.input, r.job.gas), []).append(r)
    return [Row(i, g, tuple(sorted(rs, key=lambda r: r.job.seed)))
            for (i, g), rs in groups.items()]


# --- what the results folder already holds -----------------------------------------------

DONE, NOT_DONE, CLASH = "done", "not done", "clash"


@dataclass(frozen=True)
class Prior:
    """A run of the batch the folder already has a directory for."""
    job: Job
    kind: str  # DONE, NOT_DONE or CLASH
    detail: str = field(default="")


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def prior(jobs: Sequence[Job]) -> list[Prior]:
    """For each job whose run directory exists: done, not done, or a clash."""
    found = []
    shas: dict[Path, str | None] = {}
    for j in jobs:
        rec = j.run_dir / RECORD_JSON
        if not j.run_dir.exists():
            continue
        try:
            doc = json.loads(rec.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            found.append(Prior(j, NOT_DONE, "a directory without a readable record"))
            continue
        if j.input not in shas:
            shas[j.input] = _sha256(j.input)
        theirs = (doc.get("input") or {}).get("sha256")
        if theirs != shas[j.input]:
            found.append(Prior(j, CLASH, f"holds a run of {doc.get('input', {}).get('path')}, "
                                         "another input of the same name"))
        elif doc.get("status") == "ok":
            found.append(Prior(j, DONE))
        else:
            found.append(Prior(j, NOT_DONE, doc.get("message", "")))
    return found
