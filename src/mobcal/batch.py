"""A batch: inputs, one method and its fields, seeds, and a results folder, as data.

What the window's form makes, its queue holds and saves between launches, and the command
line builds from its options: a frozen, Qt-free description that turns into the driver's jobs.
A batch runs one method (``mobcal.methods``), a shipped one by its key or a method file by its
path, and so one gas; both gases is two batches. Each field left as None takes the method's
value, so a batch saved as "MOBCAL 2000 (He), these inputs" stays that, and a field set over the
method (the gas among them) makes the runs ``custom``, or the shipped method the fields make,
as their records will say. ``to_dict``/``from_dict`` are the queue file's form, ``format = 3``,
paths as strings; ``load`` reads ``format = 2`` (the same, without ``remaining``) and
``format = 1``, whose batch named a method of both gases and a list of gases, as one batch per
gas (``mobcal.methods.ALIASES``).

A batch that was paused or closed part-way holds ``remaining``, the labels of the runs it has
left, and runs only those. ``skip_done`` cannot say it: a batch queued to *run again* over a
folder of complete runs and paused halfway still finds its unreached runs complete in the
folder, from the earlier calculation, and would skip exactly the runs it was asked to repeat.

The results folder is a study's: every batch adds its run directories to it, and the summary
covers them all (``mobcal.run.Summary.write``). ``prior`` says, before a batch starts, which of
its runs the folder already holds: done (an ok record of the same input, by its SHA-256), not
done (a failed or stopped record), or a clash (a record of another input under the same name,
which this batch would overwrite).

    from mobcal.batch import Batch
    b = Batch((Path("choline.mfj"),), Path("results"), method="2012-n2")
    plan = b.plan()
    summary = run_many(plan.jobs, plan.workers)
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mobcal import estimate, fortran, methods, parameters, settings
from mobcal.io.infile import DEALINGS, DEFAULT_DEALING, MAX_SEED
from mobcal.run import DEFAULT_RESULT_ION, RECORD_JSON, RESULT_ION_MODES, Job, cores
from mobcal.settings import Settings, Source

FORMAT = 3
FORMATS = (1, 2, 3)  # what load reads; 1 is the queue file of the version before one method a
# batch, 2 the one before a batch carried its remaining runs
DEFAULT_SEED = methods.DEFAULT_SEED  # the seed the shipped mobcal.in carries, 2012's
AUTO = "auto"


class BatchError(ValueError):
    """A batch that cannot become runs: an unknown method or table, a table for another gas."""


@dataclass(frozen=True)
class Batch:
    inputs: tuple[Path, ...]
    out_dir: Path
    method: str = methods.DEFAULT  # a shipped method's key or a method file's path
    gas: str | None = None  # None: the method's
    seeds: tuple[int, ...] | None = None  # None: the method's first seed (Method.first_seed)
    parameters: str | None = None  # a shipped set's name or a file; None: the method's
    generator: str | None = None  # None: the method's
    settings: Settings | None = None  # None: the method's
    split: int | str | None = AUTO  # W, "auto" (mobcal.estimate.allocate), or None: serial
    dealing: str | None = None  # a split run's dealing, static or claimed; None: the default
    workers: int | None = None  # runs in flight; None: the allocation's, or the cores
    skip_done: bool = False  # leave out, when the batch starts, runs the folder holds complete
    remaining: tuple[str, ...] | None = None  # run labels left, once paused; None: every run
    # whether each result file embeds the ion document or names the file alone; not a field
    # of the calculation. The queue file carries it as an extra key, read as embed when absent.
    result_ion: str = DEFAULT_RESULT_ION
    # the method, read once when the batch is made
    loaded: methods.Method = field(default=None, init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(Path(p) for p in self.inputs))
        object.__setattr__(self, "out_dir", Path(self.out_dir))
        object.__setattr__(self, "method", str(self.method))
        if self.remaining is not None:
            object.__setattr__(self, "remaining", tuple(str(r) for r in self.remaining))
        try:
            object.__setattr__(self, "loaded", methods.get(self.method))
        except methods.MethodError as e:
            raise BatchError(str(e)) from None
        seeds = (self.loaded.first_seed,) if self.seeds is None else self.seeds
        object.__setattr__(self, "seeds", tuple(int(s) for s in seeds))
        if self.gas is not None and self.gas not in fortran.GASES:
            raise BatchError(f"gas must be one of {fortran.GASES}, not {self.gas!r}")
        if not self.seeds:
            raise BatchError("a batch needs at least one seed")
        bad = [s for s in self.seeds if not 1 <= s <= MAX_SEED]
        if bad:
            raise BatchError(f"seed {bad[0]}: a seed is a positive integer up to {MAX_SEED}")
        if not (self.split in (None, AUTO) or (isinstance(self.split, int) and self.split >= 1)):
            raise BatchError(f"split must be a worker count, {AUTO!r} or None, not "
                             f"{self.split!r}")
        if self.dealing is not None and self.dealing not in DEALINGS:
            raise BatchError(f"dealing must be one of {DEALINGS} or None, not {self.dealing!r}")
        if self.result_ion not in RESULT_ION_MODES:
            raise BatchError(f"result_ion must be one of {RESULT_ION_MODES}, not "
                             f"{self.result_ion!r}")

    # --- what the runs use ---------------------------------------------------------------

    @property
    def resolved_gas(self) -> str:
        return self.gas or self.loaded.gas

    @property
    def resolved_generator(self) -> str:
        return self.generator or self.loaded.generator

    @property
    def resolved_settings(self) -> Settings:
        if self.settings is not None:
            return self.settings
        return settings.resolve(**self.loaded.overrides())

    def table(self) -> Path | None:
        """The element table file, None for the gas's default set. A method's own table goes
        with its gas: the gas changed over it, the runs take that gas's default set."""
        gas, m = self.resolved_gas, self.loaded
        if self.parameters is not None:
            name: str | Path = self.parameters
        elif gas != m.gas:
            name = m.parameters if m.parameters in parameters.SETS[gas] else parameters.DEFAULT
        elif m.table is not None:
            return m.table
        else:
            name = m.parameters
        if name == parameters.DEFAULT and self.parameters is None:
            return None
        try:
            return parameters.path_for(name, gas)
        except parameters.ParameterError as e:
            raise BatchError(str(e)) from None

    def jobs(self) -> list[Job]:
        """One job per input and seed in that order, serial (``plan`` sets the split)."""
        gas, gen, st, table = (self.resolved_gas, self.resolved_generator,
                               self.resolved_settings, self.table())
        return [Job(p, gas, s, self.out_dir, parameters=table, generator=gen, settings=st,
                    dealing=self.dealing or DEFAULT_DEALING, method_from=self.loaded,
                    result_ion=self.result_ion)
                for p in self.inputs for s in self.seeds]

    def to_run(self) -> list[Job]:
        """The jobs left: those ``remaining`` names when it is set, else the jobs less those the
        folder holds complete when ``skip_done``."""
        jobs = self.jobs()
        if self.remaining is not None:
            keep = set(self.remaining)
            return [j for j in jobs if j.label in keep]
        if not self.skip_done:
            return jobs
        done = {p.job.label for p in prior(jobs) if p.kind == DONE}
        return [j for j in jobs if j.label not in done]

    def plan(self, cpus: int | None = None, jobs: Sequence[Job] | None = None,
             sizes: dict | None = None, mode: str = estimate.DEFAULT_MODE) -> estimate.Plan:
        """The jobs as they will run, the runs in flight and the estimate; of ``jobs`` (some
        of this batch's, say those the folder does not hold yet) when given. ``sizes`` as
        ``mobcal.estimate.plan`` takes it. ``mode`` is how ``split = auto`` chooses
        (``mobcal.estimate.MODES``): the window's preference or ``--mode``, not the batch's,
        so the queue file does not carry it."""
        jobs = self.jobs() if jobs is None else list(jobs)
        if self.split == AUTO:
            p = estimate.allocate(jobs, cpus, sizes, mode)
            return p if self.workers is None else estimate.plan(p.jobs, self.workers, cpus,
                                                                sizes)
        split = self.split if isinstance(self.split, int) and self.split > 1 else None
        jobs = [dataclasses.replace(j, split=split) for j in jobs]
        workers = self.workers or max(1, (cpus or cores()) // (split or 1))
        return estimate.plan(jobs, max(1, min(workers, len(jobs) or 1)), cpus, sizes)

    @property
    def method_now(self) -> str:
        """The method the runs will record: the method's own while no field is set over it,
        and whatever the fields make otherwise (``custom`` unless they happen to make a shipped
        method)."""
        names = {j.method for j in self.jobs()}
        return names.pop() if len(names) == 1 else methods.CUSTOM

    def title(self) -> str:
        """``MOBCAL 2012 (He)``, a method file's name, or ``Custom (from MOBCAL 2012 (He))``:
        what the window shows."""
        now = self.method_now
        if now == self.loaded.key:
            return self.loaded.title
        if now == methods.CUSTOM:
            return f"Custom (from {self.loaded.title})"
        return methods.TITLES[now]

    # --- the queue file's form -----------------------------------------------------------

    def to_dict(self) -> dict:
        st = self.settings
        return {"format": FORMAT, "inputs": [str(p) for p in self.inputs],
                "out_dir": str(self.out_dir), "method": self.method, "gas": self.gas,
                "seeds": list(self.seeds), "parameters": self.parameters,
                "generator": self.generator,
                "settings": None if st is None else st.values(),
                "split": self.split, "dealing": self.dealing, "workers": self.workers,
                "skip_done": self.skip_done, "result_ion": self.result_ion,
                "remaining": None if self.remaining is None else list(self.remaining)}

    @classmethod
    def from_dict(cls, doc: dict) -> Batch:
        """A ``format = 3`` entry. Raises BatchError."""
        if doc.get("format") != FORMAT:
            raise BatchError(f"batch format {doc.get('format')!r}; from_dict reads {FORMAT}")
        return from_entry(doc)[0]


def from_entry(doc: dict) -> list[Batch]:
    """A queue file's batch entry as batches: one, or for a ``format = 1`` entry, one for each
    gas it listed, under the shipped method its method was in that gas. Raises BatchError."""
    fmt = doc.get("format")
    if fmt not in FORMATS:
        raise BatchError(f"batch format {fmt!r}; this version reads "
                         + ", ".join(map(str, FORMATS)))
    try:
        st = doc.get("settings")
        if st is not None:
            given = {k: v for k, v in st.items() if v != getattr(settings.DEFAULTS, k)}
            st = Settings(**st, source=Source(overrides=given))
        common = dict(inputs=tuple(doc["inputs"]), out_dir=Path(doc["out_dir"]),
                      seeds=tuple(doc["seeds"]), parameters=doc.get("parameters"),
                      generator=doc.get("generator"), settings=st,
                      split=doc.get("split", AUTO), dealing=doc.get("dealing"),
                      workers=doc.get("workers"), skip_done=bool(doc.get("skip_done", False)),
                      result_ion=doc.get("result_ion", DEFAULT_RESULT_ION))
        if fmt == 3:
            return [Batch(method=doc["method"], gas=doc.get("gas"),
                          remaining=doc.get("remaining"), **common)]
        if fmt == 2:
            return [Batch(method=doc["method"], gas=doc.get("gas"), **common)]
        old = doc["method"]
        if old not in methods.ALIASES:
            raise BatchError(f"no method was named {old!r}; the methods were "
                             + ", ".join(methods.ALIASES))
        out = []
        for gas in doc["gases"]:
            key = methods.ALIASES[old].format(gas=gas)
            out.append(Batch(method=key, gas=None if methods.METHODS[key].gas == gas else gas,
                             **common))
        return out
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
            batches += from_entry(d)
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
