"""The process-fanout driver: independent calculations, one process each, N at a time.

The 2012 binary is a black box with a working directory. It reads ``mobcal.in`` from the
directory it is started in, takes no arguments, writes its output where that file says, and
exits 0 whether it computed a cross section or refused its input. So every run gets a directory
of its own, parallelism is one process per directory, and what the package knows about a run it
learns from the output file: the SUMMARY block at the end is the evidence that the calculation
completed, and an output without one is a failure whose message is the last line the file holds
(``type not defined for atom number``, ``units not specified``, ``masses do not add up``).

A ``Job`` is one calculation: an input file, a gas and a seed. ``run_one`` gives it the
directory ``<out_dir>/<name>/`` holding a copy of the input (under the name the output will
echo), its ``mobcal.in``, the binary's ``mobcal.out`` and ``stdout.log``, so the directory is a
complete record that reruns by itself. ``run_many`` runs a list of jobs with a cap on how many
are in flight, calls back as each lands, and returns a ``Summary`` that writes ``summary.csv``
and ``summary.json`` beside the run directories. The Fortran is single-threaded and unchanged;
the speedup is across runs. Splitting one calculation across workers is a later task.

No Qt here. The window, when it exists, calls ``run_many`` from a worker thread and draws from
the callback.

    from mobcal.run import Job, run_many
    jobs = [Job(Path("choline.mfj"), gas, 5013489, Path("runs")) for gas in ("he", "n2")]
    summary = run_many(jobs, workers=2, progress=print)
"""

from __future__ import annotations

import csv
import datetime as dt
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
from mobcal import fortran
from mobcal.io.infile import FIELD_WIDTH, InFile, InFileError
from mobcal.io.mfj import Mfj, MfjError
from mobcal.io.outfile import OutFile

OUTPUT_NAME = "mobcal.out"
LOG_NAME = "stdout.log"
FALLBACK_STAGED_NAME = "input.mfj"  # for an input whose name would not fit the a30 field
SUMMARY_CSV = "summary.csv"
SUMMARY_JSON = "summary.json"
CSV_COLUMNS = ("name", "input", "gas", "seed", "status", "PA", "EHS", "TM", "sets", "seconds",
               "output", "message")

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

    def __post_init__(self) -> None:
        if self.gas not in fortran.GASES:
            raise ValueError(f"gas must be one of {fortran.GASES}, not {self.gas!r}")
        object.__setattr__(self, "input", Path(self.input))
        object.__setattr__(self, "out_dir", Path(self.out_dir))

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


@dataclass(frozen=True)
class Result:
    job: Job
    ok: bool
    message: str  # empty when ok; otherwise why not, with the exit status
    returncode: int | None  # None when the binary was never started
    seconds: float  # wall time of the binary alone
    output: Path | None  # the output file, whether or not it holds a SUMMARY
    cross_sections: dict[str, float]  # the run's reported values (the mean over sets)
    conformers: list[dict[str, float]]  # per coordinate set

    @property
    def status(self) -> str:
        return "ok" if self.ok else "failed"

    def record(self) -> dict:
        j = self.job
        return {"name": j.label, "input": str(j.input), "gas": j.gas, "seed": j.seed,
                "status": self.status, "message": self.message, "returncode": self.returncode,
                "seconds": round(self.seconds, 2), "output": str(self.output or ""),
                "cross_sections": self.cross_sections, "conformers": self.conformers}

    def row(self) -> dict[str, object]:
        cs = self.cross_sections
        return {"name": self.job.label, "input": str(self.job.input), "gas": self.job.gas,
                "seed": self.job.seed, "status": self.status,
                "PA": cs.get("PA", ""), "EHS": cs.get("EHS", ""), "TM": cs.get("TM", ""),
                "sets": len(self.conformers) if self.ok else "",
                "seconds": round(self.seconds, 1), "output": str(self.output or ""),
                "message": self.message}

    def __str__(self) -> str:
        if not self.ok:
            return f"{self.job.label}  FAILED  {self.message}"
        cs = "  ".join(f"{k} {v:g}" for k, v in self.cross_sections.items())
        sets = f"  ({len(self.conformers)} sets)" if len(self.conformers) > 1 else ""
        return f"{self.job.label}  ok  {cs} A^2{sets}  {self.seconds:.0f} s"


def default_launcher(job: Job) -> Sequence[str]:
    return [str(fortran.find_binary(job.gas))]


def _failed(job: Job, message: str, returncode: int | None = None, seconds: float = 0.0,
            output: Path | None = None) -> Result:
    return Result(job, False, message, returncode, seconds, output, {}, [])


def run_one(job: Job, launcher: Launcher | None = None, *,
            _running: set[subprocess.Popen] | None = None) -> Result:
    """Stage one job in its own directory, run the binary there, and read what it wrote.

    The input is read first and a file the program would stop on is reported as failed without
    starting the binary. A stale ``mobcal.out`` in the directory is removed before the run, so
    that an output is never read from an earlier run.
    """
    try:
        Mfj.read(job.input)
    except OSError as e:
        return _failed(job, f"cannot read input: {e}")
    except MfjError as e:
        return _failed(job, f"input refused: {e}")
    try:
        infile = InFile(job.staged, OUTPUT_NAME, job.seed)
    except InFileError as e:
        return _failed(job, str(e))
    try:
        command = list((launcher or default_launcher)(job))
    except (FileNotFoundError, ValueError) as e:
        return _failed(job, str(e))

    d = job.run_dir
    d.mkdir(parents=True, exist_ok=True)
    out = d / OUTPUT_NAME
    out.unlink(missing_ok=True)
    shutil.copyfile(job.input, d / job.staged)
    infile.write(d)

    t0 = time.perf_counter()
    with open(d / LOG_NAME, "wb") as log:
        try:
            proc = subprocess.Popen(command, cwd=d, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL)
        except OSError as e:
            return _failed(job, f"cannot start {command[0]}: {e}")
        if _running is not None:
            _running.add(proc)
        try:
            rc = proc.wait()
        finally:
            if _running is not None:
                _running.discard(proc)
    seconds = time.perf_counter() - t0

    if not out.is_file():
        return _failed(job, f"no output file written (exit {rc})", rc, seconds)
    o = OutFile.read(out)
    if rc != 0:
        return _failed(job, f"exit {rc}: {o.last_line}" if o.last_line else f"exit {rc}",
                       rc, seconds, out)
    if not o.ok:
        return _failed(job, f"no SUMMARY: {o.last_line}", rc, seconds, out)
    return Result(job, True, "", rc, seconds, out, o.cross_sections, o.conformers)


Progress = Callable[[Result, int, int], None]
"""Called as each run lands, with the result, how many have landed and how many there are."""


def run_many(jobs: Iterable[Job], workers: int | None = None, progress: Progress | None = None,
             launcher: Launcher | None = None) -> Summary:
    """Run the jobs with at most ``workers`` binaries in flight (default: the CPU count).

    Each job runs in its own directory from a supervising thread; results are returned in the
    jobs' order whatever order they land in. A KeyboardInterrupt stops every running binary
    and is re-raised.
    """
    jobs = list(jobs)
    workers = max(1, min(workers or os.cpu_count() or 1, len(jobs) or 1))
    results: list[Result | None] = [None] * len(jobs)
    running: set[subprocess.Popen] = set()
    lock = threading.Lock()
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mobcal-run") as pool:
        futures = {pool.submit(run_one, job, launcher, _running=running): i
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
