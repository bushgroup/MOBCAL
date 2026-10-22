"""The driver: independent calculations one process each, and one calculation across W processes.

The binary is a black box with a working directory. It reads ``mobcal.in`` from the directory
it is started in, takes no arguments, writes its output where that file says, and exits 0 when
it computed a cross section and 1 when it refused its input. So every run gets a directory of
its own, parallelism is one process per directory, and what the package knows about a run it
learns from the exit status and the output file: a nonzero exit is a failure, and so is an
output without the SUMMARY block that is the evidence the calculation completed, each with the
last line the file holds as its message (``type not defined for atom number``, ``units not
specified``, ``masses do not add up``).

A ``Job`` is one calculation: an input file, a gas and a seed, and the element table to use,
the package's own for the gas unless the job names another. ``run_one`` checks the table
(``mobcal.parameters``) and gives the job the directory ``<out_dir>/<name>/`` holding a copy of
the input (under the name the output will echo), its ``mobcal.in``, the table rendered as
``parameters.tab``, the binary's ``mobcal.out`` and ``stdout.log``, so the directory is a
complete record that reruns by itself; when the run ends it adds ``record.json``, the run's own
account of itself: the package, the binary and its build, the input and its hash, the seed, the
parameter set and its hash, the times, the verdict and the cross sections. ``run_many`` runs a
list of jobs with a cap on how many are in flight, calls back as each lands, and returns a
``Summary`` that writes ``summary.csv`` and ``summary.json`` beside the run directories.

A job with ``split=W`` is one calculation across W processes, with the serial result exactly.
Each worker runs in ``<run_dir>/wNN/`` with a ``mobcal.in`` naming it worker ``w`` of ``W``;
it integrates its share of the 400 trajectory blocks per coordinate set, draws the random
stream through the rest, and writes a file per block it integrated. When every worker has
landed and every block it owed is on disk, the block files are copied into the run directory
and the program runs there once more as the combining run (``W 0``): it integrates nothing,
reads the blocks back, and makes the sums, the averages and the SUMMARY with its own
statements. That output is the run's output, read exactly as a serial one. A worker whose
blocks are missing is a failure, with its output's last line as the reason, and the combining
run never starts.

No Qt here. The window, when it exists, calls ``run_many`` from a worker thread and draws from
the callbacks.

    from mobcal.run import Job, run_many
    jobs = [Job(Path("choline.mfj"), gas, 5013489, Path("runs")) for gas in ("he", "n2")]
    summary = run_many(jobs, workers=2, progress=print)
    split = run_one(Job(Path("choline.mfj"), "he", 5013489, Path("runs"), split=8))
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import mobcal
from mobcal import fortran, parameters
from mobcal.io.block import BLOCKS_PER_SET, expected_names
from mobcal.io.infile import FIELD_WIDTH, InFile, InFileError
from mobcal.io.mfj import Mfj, MfjError
from mobcal.io.outfile import OutFile
from mobcal.parameters import ParameterError, ParameterSet

OUTPUT_NAME = "mobcal.out"
LOG_NAME = "stdout.log"
RECORD_JSON = "record.json"
FALLBACK_STAGED_NAME = "input.mfj"  # for an input whose name would not fit the a30 field
SUMMARY_CSV = "summary.csv"
SUMMARY_JSON = "summary.json"
CSV_COLUMNS = ("name", "input", "gas", "seed", "status", "PA", "EHS", "TM", "sets", "seconds",
               "output", "message")
BLOCK_GLOB = "block-*.dat"
POLL_SECONDS = 0.25  # how often a split run counts its workers' block files

Launcher = Callable[["Job"], Sequence[str]]
"""The command line to run for a job, in the job's directory. The default is the built binary
for the job's gas; a test passes one that runs a stand-in."""


@dataclass(frozen=True)
class Job:
    input: Path
    gas: str
    seed: int
    out_dir: Path
    name: str | None = None  # the run directory's name; default <input stem>-<gas>-<seed>
    staged_name: str | None = None  # the input's name inside the run directory
    split: int | None = None  # W: run this one calculation across W processes
    parameters: Path | None = None  # the element table; None is the package's for the gas

    def __post_init__(self) -> None:
        if self.gas not in fortran.GASES:
            raise ValueError(f"gas must be one of {fortran.GASES}, not {self.gas!r}")
        if self.split is not None and not (isinstance(self.split, int)
                                           and 1 <= self.split <= BLOCKS_PER_SET):
            raise ValueError(f"split must be a worker count from 1 to {BLOCKS_PER_SET}, "
                             f"not {self.split!r}")
        object.__setattr__(self, "input", Path(self.input))
        object.__setattr__(self, "out_dir", Path(self.out_dir))
        if self.parameters is not None:
            object.__setattr__(self, "parameters", Path(self.parameters))

    @property
    def label(self) -> str:
        return self.name or f"{self.input.stem}-{self.gas}-{self.seed}"

    @property
    def run_dir(self) -> Path:
        return self.out_dir / self.label

    @property
    def staged(self) -> str:
        """The name the input is copied to, and the name the output echoes."""
        if self.staged_name:
            return self.staged_name
        return self.input.name if len(self.input.name) <= FIELD_WIDTH else FALLBACK_STAGED_NAME

    def worker_dir(self, w: int) -> Path:
        return self.run_dir / f"w{w:02d}"

    @property
    def parameters_path(self) -> Path:
        return self.parameters or parameters.default_path(self.gas)


@dataclass(frozen=True)
class Result:
    job: Job
    ok: bool
    message: str  # empty when ok; otherwise why not, with the exit status
    returncode: int | None  # None when the binary was never started
    seconds: float  # wall time of the binary alone (of workers and combining run, split)
    output: Path | None  # the output file, whether or not it holds a SUMMARY
    cross_sections: dict[str, float]  # the run's reported values (the mean over sets)
    conformers: list[dict[str, float]]  # per coordinate set
    parameters: dict = dataclasses.field(default_factory=dict)  # the set's record; {} if unread

    @property
    def status(self) -> str:
        return "ok" if self.ok else "failed"

    def record(self) -> dict:
        j = self.job
        return {"name": j.label, "input": str(j.input), "gas": j.gas, "seed": j.seed,
                "split": j.split, "status": self.status, "message": self.message,
                "returncode": self.returncode, "seconds": round(self.seconds, 2),
                "output": str(self.output or ""), "cross_sections": self.cross_sections,
                "conformers": self.conformers, "parameters": self.parameters.get("name"),
                "parameters_sha256": self.parameters.get("sha256")}

    def row(self) -> dict[str, object]:
        cs = self.cross_sections
        return {"name": self.job.label, "input": str(self.job.input), "gas": self.job.gas,
                "seed": self.job.seed, "status": self.status,
                "PA": cs.get("PA", ""), "EHS": cs.get("EHS", ""), "TM": cs.get("TM", ""),
                "sets": len(self.conformers) if self.ok else "",
                "seconds": round(self.seconds, 1), "output": str(self.output or ""),
                "message": self.message}

    def __str__(self) -> str:
        split = f"  ({self.job.split} workers)" if self.job.split else ""
        if not self.ok:
            return f"{self.job.label}  FAILED  {self.message}{split}"
        cs = "  ".join(f"{k} {v:g}" for k, v in self.cross_sections.items())
        sets = f"  ({len(self.conformers)} sets)" if len(self.conformers) > 1 else ""
        return f"{self.job.label}  ok  {cs} A^2{sets}  {self.seconds:.0f} s{split}"


def default_launcher(job: Job) -> Sequence[str]:
    return [str(fortran.find_binary(job.gas))]


def _failed(job: Job, message: str, returncode: int | None = None, seconds: float = 0.0,
            output: Path | None = None) -> Result:
    return Result(job, False, message, returncode, seconds, output, {}, [])


def usable(pset: ParameterSet) -> None:
    """Raise ParameterError for a table the binaries would not actually use: any but the
    shipped one, while they still carry the 2012 tables in their source
    (``fortran.READS_PARAMETERS``)."""
    if not (pset.shipped or fortran.READS_PARAMETERS):
        raise ParameterError(
            f"{pset.path}: the programs in this version take the element table from their "
            f"source, which equals the shipped {parameters.FILES[pset.gas]}, and do not yet "
            f"read parameters.tab; a run can name no other table, since its record would name "
            f"a table the program did not use")


def _prepare(job: Job, d: Path, split: tuple[int, int] | None, pset: ParameterSet) -> None:
    """Make ``d`` ready for one start of the program: the input copied in under its staged name,
    ``mobcal.in`` written, the element table rendered, and any output, record or block file of
    an earlier run removed, so that nothing stale is ever read as this run's."""
    d.mkdir(parents=True, exist_ok=True)
    (d / OUTPUT_NAME).unlink(missing_ok=True)
    (d / RECORD_JSON).unlink(missing_ok=True)
    for p in d.glob(BLOCK_GLOB):
        p.unlink()
    shutil.copyfile(job.input, d / job.staged)
    InFile(job.staged, OUTPUT_NAME, job.seed, split).write(d)
    pset.render(d)


def _start(command: Sequence[str], d: Path,
           running: set[subprocess.Popen] | None) -> subprocess.Popen:
    """Start the program in ``d``, its console output to ``stdout.log``. Raises OSError."""
    with open(d / LOG_NAME, "wb") as log:
        proc = subprocess.Popen(command, cwd=d, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL)
    if running is not None:
        running.add(proc)
    return proc


def _finish(proc: subprocess.Popen, running: set[subprocess.Popen] | None) -> None:
    if running is not None:
        running.discard(proc)


def _collect(job: Job, d: Path, rc: int, seconds: float) -> Result:
    """The verdict on a run from what the program left in ``d``."""
    out = d / OUTPUT_NAME
    if not out.is_file():
        return _failed(job, f"no output file written (exit {rc})", rc, seconds)
    o = OutFile.read(out)
    if rc != 0:
        return _failed(job, f"exit {rc}: {o.last_line}" if o.last_line else f"exit {rc}",
                       rc, seconds, out)
    if not o.ok:
        return _failed(job, f"no SUMMARY: {o.last_line}", rc, seconds, out)
    return Result(job, True, "", rc, seconds, out, o.cross_sections, o.conformers)


BlocksProgress = Callable[[Job, int, int], None]
"""Called by a split run as its workers write block files: the job, blocks written, blocks
expected. Called at least once, when the workers have landed."""


def run_one(job: Job, launcher: Launcher | None = None, *,
            _running: set[subprocess.Popen] | None = None,
            blocks: BlocksProgress | None = None) -> Result:
    """Stage one job in its own directory, run the binary there, and read what it wrote.

    The input and the element table are read first, and a file the program would stop on, or
    a table ``mobcal.parameters`` refuses, is reported as failed without starting the binary or
    making the run directory. A stale ``mobcal.out`` in the directory is removed before the run,
    so that an output is never read from an earlier run. A job with ``split`` runs its workers
    and then the combining run; see the module docstring. Every run that got as far as its
    directory ends with ``record.json`` written there, failed or not.
    """
    try:
        mfj = Mfj.read(job.input)
    except OSError as e:
        return _failed(job, f"cannot read input: {e}")
    except MfjError as e:
        return _failed(job, f"input refused: {e}")
    try:
        pset = parameters.load(job.parameters_path, gas=job.gas)
        usable(pset)
    except ParameterError as e:
        return _failed(job, f"parameters refused: {e}")
    try:
        InFile(job.staged, OUTPUT_NAME, job.seed)
    except InFileError as e:
        return _failed(job, str(e))
    try:
        command = list((launcher or default_launcher)(job))
    except (FileNotFoundError, ValueError) as e:
        return _failed(job, str(e))

    started = dt.datetime.now().astimezone()
    if job.split:
        r = _run_split(job, command, mfj.coordinate_sets, pset, _running, blocks)
    else:
        r = _run_serial(job, command, pset, _running)
    r = dataclasses.replace(r, parameters=pset.record())
    _write_record(r, command, mfj, started)
    return r


def _run_serial(job: Job, command: list[str], pset: ParameterSet,
                running: set[subprocess.Popen] | None) -> Result:
    d = job.run_dir
    _prepare(job, d, None, pset)
    t0 = time.perf_counter()
    try:
        proc = _start(command, d, running)
    except OSError as e:
        return _failed(job, f"cannot start {command[0]}: {e}")
    try:
        rc = proc.wait()
    finally:
        _finish(proc, running)
    return _collect(job, d, rc, time.perf_counter() - t0)


def _run_split(job: Job, command: list[str], coordinate_sets: int, pset: ParameterSet,
               running: set[subprocess.Popen] | None, blocks: BlocksProgress | None) -> Result:
    total, d = job.split, job.run_dir
    expected = {w: expected_names(coordinate_sets, total, w) for w in range(1, total + 1)}
    n_expected = sum(len(v) for v in expected.values())
    _prepare(job, d, (total, 0), pset)
    for w in expected:
        _prepare(job, job.worker_dir(w), (total, w), pset)

    t0 = time.perf_counter()
    procs: dict[int, subprocess.Popen] = {}
    try:
        for w in expected:
            procs[w] = _start(command, job.worker_dir(w), running)
    except OSError as e:
        for p in procs.values():
            p.terminate()
            _finish(p, running)
        return _failed(job, f"cannot start {command[0]}: {e}")

    written = -1
    try:
        while True:
            alive = [p for p in procs.values() if p.poll() is None]
            n = sum(1 for w in expected for _ in job.worker_dir(w).glob(BLOCK_GLOB))
            if blocks is not None and n != written:
                blocks(job, n, n_expected)
                written = n
            if not alive:
                break
            try:
                alive[0].wait(timeout=POLL_SECONDS)
            except subprocess.TimeoutExpired:
                pass
    finally:
        for p in procs.values():
            _finish(p, running)

    problems = []
    for w, names in expected.items():
        missing = [n for n in names if not (job.worker_dir(w) / n).is_file()]
        if not missing:
            continue
        out = job.worker_dir(w) / OUTPUT_NAME
        last = OutFile.read(out).last_line if out.is_file() else ""
        why = last or f"exit {procs[w].returncode}"
        problems.append(f"worker {w}: {len(missing)} of {len(names)} blocks missing ({why})")
    if problems:
        rc = next((p.returncode for p in procs.values() if p.returncode), 0)
        return _failed(job, "; ".join(problems), rc, time.perf_counter() - t0)

    for w in expected:
        for p in job.worker_dir(w).glob(BLOCK_GLOB):
            shutil.copyfile(p, d / p.name)
    try:
        proc = _start(command, d, running)
    except OSError as e:
        return _failed(job, f"cannot start the combining run: {e}", None,
                       time.perf_counter() - t0)
    try:
        rc = proc.wait()
    finally:
        _finish(proc, running)
    return _collect(job, d, rc, time.perf_counter() - t0)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_record(r: Result, command: list[str], mfj: Mfj, started: dt.datetime) -> Path:
    """Write ``record.json`` into the run's directory: what ran, on what, with which table, and
    what came of it. Its numbers are the ``Result``'s; the output file stays the evidence."""
    j = r.job
    exe = Path(command[0])
    build = fortran.read_manifest(exe.parent).get("binaries", {}).get(exe.name)
    doc = {
        "mobcal_version": mobcal.__version__,
        "name": j.label,
        "binary": {"gas": j.gas, "path": str(exe), "command": list(command), "build": build},
        "input": {"path": str(j.input), "staged_name": j.staged, "sha256": _sha256(j.input),
                  "atoms": mfj.atoms, "coordinate_sets": mfj.coordinate_sets},
        "mobcal_in": {"seed": j.seed, "split": j.split},
        "parameters": r.parameters,
        "started": started.isoformat(timespec="seconds"),
        "seconds": round(r.seconds, 2),
        "returncode": r.returncode,
        "status": r.status,
        "message": r.message,
        "cross_sections": r.cross_sections,
        "conformers": r.conformers,
        "output": OUTPUT_NAME,
        "console_log": LOG_NAME,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }
    j.run_dir.mkdir(parents=True, exist_ok=True)
    out = j.run_dir / RECORD_JSON
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return out


Progress = Callable[[Result, int, int], None]
"""Called as each run lands, with the result, how many have landed and how many there are."""


def run_many(jobs: Iterable[Job], workers: int | None = None, progress: Progress | None = None,
             launcher: Launcher | None = None, blocks: BlocksProgress | None = None) -> Summary:
    """Run the jobs with at most ``workers`` in flight (default: the CPU count).

    Each job runs in its own directory from a supervising thread; results are returned in the
    jobs' order whatever order they land in. A split job counts as one job in flight and
    starts its own W processes. A KeyboardInterrupt stops every running binary and is
    re-raised.
    """
    jobs = list(jobs)
    workers = max(1, min(workers or os.cpu_count() or 1, len(jobs) or 1))
    results: list[Result | None] = [None] * len(jobs)
    running: set[subprocess.Popen] = set()
    lock = threading.Lock()

    def report_blocks(job: Job, n: int, total: int) -> None:
        if blocks is not None:
            with lock:
                blocks(job, n, total)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mobcal-run") as pool:
        futures = {pool.submit(run_one, job, launcher, _running=running, blocks=report_blocks): i
                   for i, job in enumerate(jobs)}
        done = 0
        try:
            for fut in as_completed(futures):
                r = fut.result()
                results[futures[fut]] = r
                done += 1
                if progress is not None:
                    with lock:
                        progress(r, done, len(jobs))
        except BaseException:
            for p in list(running):
                try:
                    p.terminate()
                except OSError:
                    pass
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    return Summary([r for r in results if r is not None], workers, time.perf_counter() - t0)


@dataclass(frozen=True)
class Summary:
    results: list[Result]
    workers: int
    seconds: float  # wall time of the whole batch

    @property
    def ok(self) -> list[Result]:
        return [r for r in self.results if r.ok]

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok]

    def write(self, out_dir: Path) -> tuple[Path, Path]:
        """Write ``summary.csv`` (one row per run) and ``summary.json`` (the same, with the
        per-set values and the batch's provenance) into ``out_dir``; return the two paths."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path, json_path = out_dir / SUMMARY_CSV, out_dir / SUMMARY_JSON
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            for r in self.results:
                w.writerow(r.row())
        doc = {
            "mobcal_version": mobcal.__version__,
            "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "workers": self.workers,
            "seconds": round(self.seconds, 1),
            "runs": [r.record() for r in self.results],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return csv_path, json_path

    def __str__(self) -> str:
        n, bad = len(self.results), len(self.failed)
        w = self.workers
        return (f"{n} run{'s' if n != 1 else ''}, {n - bad} ok, {bad} failed, "
                f"{self.seconds:.0f} s wall on {w} worker{'s' if w != 1 else ''}")
