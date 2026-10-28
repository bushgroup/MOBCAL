"""The driver: independent calculations one process each, and one calculation across W processes.

The binary is a black box with a working directory. It reads ``mobcal.in`` from the directory
it is started in, takes no arguments, writes its output where that file says, and exits 0 when
it computed a cross section and 1 when it refused its input. So every run gets a directory of
its own, parallelism is one process per directory, and what the package knows about a run it
learns from the exit status and the output file: a nonzero exit is a failure, and so is an
output without the SUMMARY block that is the evidence the calculation completed, each with the
last line the file holds as its message (``type not defined for atom number``, ``units not
specified``, ``masses do not add up``).

A ``Job`` is one calculation: an input file, a gas and a seed, the element table to use, the
package's own for the gas unless the job names another, the random number generator,
Philox4x32-10 unless the job says ``ranlux``, the 2012 generator, which is what reproduces a
2012 number, and the run settings (``mobcal.settings``: the temperature and the five sampling
counts), the 2012 values unless the job says otherwise. The run directory's name carries
``-ranlux`` when the job does, the table when it is not the gas's default (``-lj2000`` for a
shipped set, ``-lj`` and the first eight hex digits of its SHA-256 for any other file), and each
setting that differs from 2012 (``-t298-imp25``), so the same input and seed under another
method never share a directory, and one results folder can hold a whole study.
``run_one`` checks the table (``mobcal.parameters``) and gives the job the directory
``<out_dir>/<name>/`` holding a copy of the input (under the name the output will echo), its
``mobcal.in``, the table rendered as ``parameters.tab``, the settings rendered as
``settings.tab``, the binary's ``mobcal.out`` and ``stdout.log``, so the directory is a
complete record that reruns by itself; when the run ends it adds ``record.json``, the run's own
account of itself: the package, the binary and its build, the input and its hash, the seed, the
parameter set and its hash, the settings and where they came from, the method they make
(``mobcal.methods``: a shipped method's key such as ``2012-philox-he``, the name of the method
file the job was made from with that file's path and SHA-256, or ``custom``), the times, the
verdict and the cross sections. ``run_many`` runs a list of jobs with a cap on how many are in
flight, calls back as each lands, and returns a ``Summary`` that writes ``summary.csv`` and
``summary.json`` beside the run directories, covering every run the folder holds: the batch's
own results and every earlier run's ``record.json``. A ``Stop`` handed to ``run_many`` ends the
batch from another thread: no run starts after it, every process running is killed with its
whole process tree, and the runs it ended report ``stopped`` and keep their directories as
partial records.

A job with ``split=W`` is one calculation across W processes, with the serial result exactly.
Each worker runs in ``<run_dir>/wNN/`` with a ``mobcal.in`` naming it worker ``w`` of ``W``;
it integrates its share of the ``itn * inp`` trajectory blocks per coordinate set (400 at the
2012 settings), draws the random stream through the rest (or, at ``philox``, moves the draw
count past them), and writes a file per block it integrated. When every worker has
landed and every block it owed is on disk, the block files are copied into the run directory
and the program runs there once more as the combining run (``W 0``): it integrates nothing,
reads the blocks back, and makes the sums, the averages and the SUMMARY with its own
statements. That output is the run's output, read exactly as a serial one. A worker whose
blocks are missing is a failure, with its output's last line as the reason, and the combining
run never starts.

No Qt here. The window calls ``run_many`` from a worker thread and draws from the callbacks.

    from mobcal.run import Job, run_many
    jobs = [Job(Path("choline.mfj"), gas, 5013489, Path("runs")) for gas in ("he", "n2")]
    summary = run_many(jobs, workers=2, progress=print)
    split = run_one(Job(Path("choline.mfj"), "he", 5013489, Path("runs"), split=8))
    as_2012 = run_one(Job(Path("choline.mfj"), "he", 5013489, Path("runs"), generator="ranlux"))
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
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import mobcal
from mobcal import fortran, methods, parameters, settings
from mobcal.io.block import expected_names
from mobcal.io.infile import FIELD_WIDTH, GENERATORS, InFile, InFileError
from mobcal.io.mfj import Mfj, MfjError
from mobcal.io.outfile import OutFile
from mobcal.parameters import ParameterError, ParameterSet
from mobcal.settings import Settings

OUTPUT_NAME = "mobcal.out"
LOG_NAME = "stdout.log"
RECORD_JSON = "record.json"
FALLBACK_STAGED_NAME = "input.mfj"  # for an input whose name would not fit the a30 field
SUMMARY_CSV = "summary.csv"
SUMMARY_JSON = "summary.json"
CSV_COLUMNS = ("name", "input", "gas", "seed", "rng", "method", *settings.NAMES, "status", "PA",
               "EHS", "TM", "sets", "seconds", "output", "message")
BLOCK_GLOB = "block-*.dat"
POLL_SECONDS = 0.25  # how often a split run counts its workers' block files
# The driver's generator. It differs from the run file's on purpose: a mobcal.in without the
# word is the 2012 run (ranlux), so a file written by hand or shipped means what it meant in
# 2012; a job the driver writes draws from Philox, whose split runs are exact by construction.
# The default method, 2012-philox-he (mobcal.methods.DEFAULT), carries the same choice.
DEFAULT_RNG = "philox"

Launcher = Callable[["Job"], Sequence[str]]
"""The command line to run for a job, in the job's directory. The default is the built binary
for the job's gas; a test passes one that runs a stand-in."""


@dataclass(frozen=True)
class Job:
    input: Path
    gas: str
    seed: int
    out_dir: Path
    name: str | None = None  # the run directory's name; default <stem>-<gas>-<seed>[-ranlux]
    staged_name: str | None = None  # the input's name inside the run directory
    split: int | None = None  # W: run this one calculation across W processes
    parameters: Path | None = None  # the element table; None is the package's for the gas
    generator: str = DEFAULT_RNG  # the random number generator: philox, or ranlux (2012)
    settings: Settings = settings.DEFAULTS  # the temperature and the sampling counts
    # the method the job was made from, which its record names while the job's fields are the
    # method's; None: the record names the shipped method the fields make, or custom
    method_from: methods.Method | None = field(default=None, compare=False, repr=False)
    # the shipped set the table is by its pin (None for any other file), its SHA-256 and the
    # label's part for it, all from the file's bytes when the job is made
    set_name: str | None = field(default=None, init=False, compare=False, repr=False)
    table_sha256: str | None = field(default=None, init=False, compare=False, repr=False)
    table_tag: str = field(default="", init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.gas not in fortran.GASES:
            raise ValueError(f"gas must be one of {fortran.GASES}, not {self.gas!r}")
        if self.generator not in GENERATORS:
            raise ValueError(f"generator must be one of {GENERATORS}, not {self.generator!r}")
        if not isinstance(self.settings, Settings):
            raise ValueError(f"settings must be a mobcal.settings.Settings, not "
                             f"{self.settings!r}")
        blocks = self.settings.blocks_per_set
        if self.split is not None and not (isinstance(self.split, int)
                                           and 1 <= self.split <= blocks):
            raise ValueError(f"split must be a worker count from 1 to {blocks} (itn * inp), "
                             f"not {self.split!r}")
        object.__setattr__(self, "input", Path(self.input))
        object.__setattr__(self, "out_dir", Path(self.out_dir))
        if self.parameters is not None:
            object.__setattr__(self, "parameters", Path(self.parameters))
        set_name, sha, tag = _table(self.gas, self.parameters)
        object.__setattr__(self, "set_name", set_name)
        object.__setattr__(self, "table_sha256", sha)
        object.__setattr__(self, "table_tag", tag)

    def _from_file(self) -> methods.Method | None:
        """The method file the job was made from, while its fields are the file's."""
        m = self.method_from
        if m is None or m.shipped or not m.matches(self.gas, self.set_name, self.table_sha256,
                                                   self.generator, self.settings):
            return None
        return m

    @property
    def method(self) -> str:
        """The method the record names (``mobcal.methods``): the method file's name while the
        job's gas, table, generator and settings are the file's, else the shipped method they
        make, else custom."""
        m = self._from_file()
        if m is not None:
            return m.key
        return methods.identify(self.gas, self.set_name, self.generator, self.settings)

    @property
    def method_file(self) -> dict | None:
        """The method file's path and SHA-256 when the record names one, else None."""
        m = self._from_file()
        return m.record() if m is not None else None

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        rng = "" if self.generator == DEFAULT_RNG else f"-{self.generator}"
        return (f"{self.input.stem}-{self.gas}-{self.seed}{rng}{self.table_tag}"
                f"{self.settings.suffix()}")

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
    stopped: bool = False  # ended by a Stop, not by itself

    @property
    def status(self) -> str:
        return "ok" if self.ok else "stopped" if self.stopped else "failed"

    def record(self) -> dict:
        j = self.job
        return {"name": j.label, "input": str(j.input), "gas": j.gas, "seed": j.seed,
                "rng": j.generator, "method": j.method, "method_file": j.method_file,
                "split": j.split,
                "settings": j.settings.record(),
                "status": self.status,
                "message": self.message, "returncode": self.returncode,
                "seconds": round(self.seconds, 2), "output": str(self.output or ""),
                "cross_sections": self.cross_sections,
                "conformers": self.conformers, "parameters": self.parameters.get("name"),
                "parameters_sha256": self.parameters.get("sha256")}

    def row(self) -> dict[str, object]:
        return row(self.record())

    def __str__(self) -> str:
        split = f"  ({self.job.split} workers)" if self.job.split else ""
        if not self.ok:
            return f"{self.job.label}  {self.status.upper()}  {self.message}{split}"
        cs = "  ".join(f"{k} {v:g}" for k, v in self.cross_sections.items())
        sets = f"  ({len(self.conformers)} sets)" if len(self.conformers) > 1 else ""
        return f"{self.job.label}  ok  {cs} A^2{sets}  {self.seconds:.0f} s{split}"


def _table(gas: str, path: Path | None) -> tuple[str | None, str | None, str]:
    """The shipped set a table file is by its pin, its SHA-256, and the label's part for it:
    ``""`` for the gas's default set, ``-lj2000`` for another shipped set, ``-lj`` and eight hex
    digits of the SHA-256 for any other file, ``-lj-<stem>`` for one that cannot be read (the
    run says why)."""
    if path is None:
        return parameters.DEFAULT, parameters.SHA256[parameters.FILES[gas]], ""
    try:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None, None, f"-lj-{path.stem}"
    name = next((n for n, f in parameters.SETS[gas].items() if parameters.SHA256[f] == sha), None)
    if name == parameters.DEFAULT:
        return name, sha, ""
    return name, sha, f"-lj{name}" if name else f"-lj{sha[:8]}"


def row(run: dict) -> dict[str, object]:
    """A summary.csv row from a run's entry in summary.json."""
    cs, ok = run["cross_sections"], run["status"] == "ok"
    return {"name": run["name"], "input": run["input"], "gas": run["gas"], "seed": run["seed"],
            "rng": run["rng"], "method": run.get("method", ""),
            **{k: (f"{run['settings'][k]:g}" if k == "temperature" else run["settings"][k])
               for k in settings.NAMES},
            "status": run["status"],
            "PA": cs.get("PA", ""), "EHS": cs.get("EHS", ""), "TM": cs.get("TM", ""),
            "sets": len(run["conformers"]) if ok else "",
            "seconds": round(run["seconds"], 1), "output": run["output"],
            "message": run["message"]}


def from_record(doc: dict, run_dir: Path) -> dict:
    """A run's entry in summary.json from the ``record.json`` it left in ``run_dir``: the same
    fields ``Result.record`` gives a run of this batch."""
    out = run_dir / doc.get("output", OUTPUT_NAME)
    p = doc.get("parameters") or {}
    return {"name": doc["name"], "input": doc["input"]["path"], "gas": doc["binary"]["gas"],
            "seed": doc["mobcal_in"]["seed"], "rng": doc["mobcal_in"]["generator"],
            "method": methods.record_method(doc), "method_file": doc.get("method_file"),
            "split": doc["mobcal_in"]["split"],
            "settings": doc["settings"], "status": doc["status"], "message": doc["message"],
            "returncode": doc["returncode"], "seconds": doc["seconds"],
            "output": str(out) if out.is_file() else "",
            "cross_sections": doc["cross_sections"], "conformers": doc["conformers"],
            "parameters": p.get("name"), "parameters_sha256": p.get("sha256")}


def read_records(out_dir: Path) -> dict[str, dict]:
    """Every run directory's record in ``out_dir`` as summary.json entries, by name. A record
    that cannot be read or parsed is skipped: the folder may hold anything else besides."""
    found = {}
    for f in sorted(Path(out_dir).glob(f"*/{RECORD_JSON}")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            found[doc["name"]] = from_record(doc, f.parent)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


class Stop:
    """Ends a ``run_many`` batch from any thread: once called, no run starts, every process
    running is killed with its whole tree, and the runs it ended report stopped."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._procs: set[subprocess.Popen] = set()

    def __call__(self) -> None:
        self._event.set()
        with self._lock:
            procs = list(self._procs)
        for p in procs:
            _kill_tree(p)

    stop = __call__

    def is_set(self) -> bool:
        return self._event.is_set()

    def add(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.add(proc)
        if self._event.is_set():  # started as the stop came: end it too
            _kill_tree(proc)

    def discard(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(proc)


# A process group of its own on POSIX, so that killing the run kills whatever it started. On
# Windows no console window: a console program started by one that has none, as the window's
# mobcal-gui.exe has none, is given a console window of its own, one per run on the screen.
# The program's output goes to stdout.log, and a terminal's Ctrl+C, which reaches neither, is
# passed on by run_many and _wait, which kill the running binaries.
_POPEN_EXTRA = ({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt"
                else {"start_new_session": True})


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process and every process it started. On Windows ``taskkill /T`` walks the tree
    (a venv's python.exe, for one, is a launcher that starts the real interpreter as a child);
    elsewhere the run is its own process group."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                           **_POPEN_EXTRA)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.kill()
    except OSError:
        pass


def default_launcher(job: Job) -> Sequence[str]:
    return [str(fortran.find_binary(job.gas))]


def _failed(job: Job, message: str, returncode: int | None = None, seconds: float = 0.0,
            output: Path | None = None) -> Result:
    return Result(job, False, message, returncode, seconds, output, {}, [])


def _prepare(job: Job, d: Path, split: tuple[int, int] | None, pset: ParameterSet) -> None:
    """Make ``d`` ready for one start of the program: the input copied in under its staged name,
    ``mobcal.in`` written, the element table and the settings rendered, and any output, record
    or block file of an earlier run removed, so that nothing stale is ever read as this run's."""
    d.mkdir(parents=True, exist_ok=True)
    (d / OUTPUT_NAME).unlink(missing_ok=True)
    (d / RECORD_JSON).unlink(missing_ok=True)
    for p in d.glob(BLOCK_GLOB):
        p.unlink()
    shutil.copyfile(job.input, d / job.staged)
    InFile(job.staged, OUTPUT_NAME, job.seed, split, job.generator).write(d)
    pset.render(d)
    job.settings.render(d)


def _start(command: Sequence[str], d: Path, running: Stop | None) -> subprocess.Popen:
    """Start the program in ``d``, its console output to ``stdout.log``. Raises OSError."""
    with open(d / LOG_NAME, "wb") as log:
        proc = subprocess.Popen(command, cwd=d, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, **_POPEN_EXTRA)
    if running is not None:
        running.add(proc)
    return proc


def _wait(proc: subprocess.Popen) -> int:
    """Wait for the program; a KeyboardInterrupt while waiting kills it and is re-raised. Its
    own process group, or no console on Windows, keeps a terminal's Ctrl+C from reaching it."""
    try:
        return proc.wait()
    except BaseException:
        _kill_tree(proc)
        raise


def _finish(proc: subprocess.Popen, running: Stop | None) -> None:
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
            _running: Stop | None = None,
            blocks: BlocksProgress | None = None,
            on_start: Callable[[Job], None] | None = None) -> Result:
    """Stage one job in its own directory, run the binary there, and read what it wrote.

    The input and the element table are read first, and a file the program would stop on, or
    a table ``mobcal.parameters`` refuses, is reported as failed without starting the binary or
    making the run directory. A stale ``mobcal.out`` in the directory is removed before the run,
    so that an output is never read from an earlier run. A job with ``split`` runs its workers
    and then the combining run; see the module docstring. Every run that got as far as its
    directory ends with ``record.json`` written there, failed or not. A KeyboardInterrupt
    stops the job's processes and is re-raised.
    """
    try:
        mfj = Mfj.read(job.input)
    except OSError as e:
        return _failed(job, f"cannot read input: {e}")
    except MfjError as e:
        return _failed(job, f"input refused: {e}")
    try:
        pset = parameters.load(job.parameters_path, gas=job.gas)
    except ParameterError as e:
        return _failed(job, f"parameters refused: {e}")
    try:
        InFile(job.staged, OUTPUT_NAME, job.seed, generator=job.generator)
    except InFileError as e:
        return _failed(job, str(e))
    try:
        command = list((launcher or default_launcher)(job))
    except (FileNotFoundError, ValueError) as e:
        return _failed(job, str(e))

    if _running is not None and _running.is_set():
        return dataclasses.replace(_failed(job, "not started: the batch was stopped"),
                                   stopped=True)
    if on_start is not None:
        on_start(job)
    started = dt.datetime.now().astimezone()
    if job.split:
        r = _run_split(job, command, mfj.coordinate_sets, pset, _running, blocks)
    else:
        r = _run_serial(job, command, pset, _running)
    r = dataclasses.replace(r, parameters=pset.record())
    if not r.ok and _running is not None and _running.is_set():
        r = dataclasses.replace(r, stopped=True, message=f"stopped ({r.message})")
    _write_record(r, command, mfj, started)
    return r


def _run_serial(job: Job, command: list[str], pset: ParameterSet,
                running: Stop | None) -> Result:
    d = job.run_dir
    _prepare(job, d, None, pset)
    t0 = time.perf_counter()
    try:
        proc = _start(command, d, running)
    except OSError as e:
        return _failed(job, f"cannot start {command[0]}: {e}")
    try:
        rc = _wait(proc)
    finally:
        _finish(proc, running)
    return _collect(job, d, rc, time.perf_counter() - t0)


def _run_split(job: Job, command: list[str], coordinate_sets: int, pset: ParameterSet,
               running: Stop | None, blocks: BlocksProgress | None) -> Result:
    total, d = job.split, job.run_dir
    blocks_per_set = job.settings.blocks_per_set
    expected = {w: expected_names(coordinate_sets, total, w, blocks_per_set)
                for w in range(1, total + 1)}
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
            if not alive or (running is not None and running.is_set()):
                break
            try:
                alive[0].wait(timeout=POLL_SECONDS)
            except subprocess.TimeoutExpired:
                pass
    except BaseException:  # a KeyboardInterrupt, which does not reach the workers themselves
        for p in procs.values():
            _kill_tree(p)
        raise
    finally:
        for p in procs.values():
            _finish(p, running)

    problems = []
    if running is not None and running.is_set():
        for p in procs.values():
            _kill_tree(p)
            p.wait()
        return _failed(job, "split run ended before its combining run", None,
                       time.perf_counter() - t0)
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
        rc = _wait(proc)
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
        "mobcal_in": {"seed": j.seed, "generator": j.generator, "split": j.split},
        "method": j.method,
        "method_file": j.method_file,
        "parameters": r.parameters,
        "settings": j.settings.record(),
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
             launcher: Launcher | None = None, blocks: BlocksProgress | None = None,
             stop: Stop | None = None,
             on_start: Callable[[Job], None] | None = None) -> Summary:
    """Run the jobs with at most ``workers`` in flight (default: the CPU count).

    Each job runs in its own directory from a supervising thread; results are returned in the
    jobs' order whatever order they land in. ``on_start`` is called as each job's program is
    about to start, once its input and table have been read. A split job counts as one job in
    flight and starts its own W processes. ``stop`` ends the batch from another thread: every
    job still to start returns at once as stopped, and every running one is killed and reports
    stopped. A KeyboardInterrupt stops every running binary and is re-raised.
    """
    jobs = list(jobs)
    workers = max(1, min(workers or os.cpu_count() or 1, len(jobs) or 1))
    results: list[Result | None] = [None] * len(jobs)
    running = stop if stop is not None else Stop()
    lock = threading.Lock()

    def report_blocks(job: Job, n: int, total: int) -> None:
        if blocks is not None:
            with lock:
                blocks(job, n, total)

    def report_start(job: Job) -> None:
        if on_start is not None:
            with lock:
                on_start(job)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mobcal-run") as pool:
        futures = {pool.submit(run_one, job, launcher, _running=running, blocks=report_blocks,
                               on_start=report_start): i
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
            running.stop()
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
        return [r for r in self.results if not r.ok and not r.stopped]

    @property
    def stopped(self) -> list[Result]:
        return [r for r in self.results if r.stopped]

    def write(self, out_dir: Path) -> tuple[Path, Path]:
        """Write ``summary.csv`` (one row per run) and ``summary.json`` (the same, with the
        per-set values and the provenance) into ``out_dir`` and return the two paths. They
        cover every run the folder holds, in name order: this batch's results, and every other
        run directory's ``record.json``; ``summary.json`` also names this batch's runs, its
        workers and its wall time."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path, json_path = out_dir / SUMMARY_CSV, out_dir / SUMMARY_JSON
        found = read_records(out_dir)
        found.update((r.job.label, r.record()) for r in self.results)
        runs = [found[k] for k in sorted(found)]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            for run in runs:
                w.writerow(row(run))
        doc = {
            "mobcal_version": mobcal.__version__,
            "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "workers": self.workers,
            "seconds": round(self.seconds, 1),
            "batch": [r.job.label for r in self.results],
            "runs": runs,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return csv_path, json_path

    def __str__(self) -> str:
        n, bad, stopped = len(self.results), len(self.failed), len(self.stopped)
        w = self.workers
        return (f"{n} run{'s' if n != 1 else ''}, {len(self.ok)} ok, {bad} failed, "
                + (f"{stopped} stopped, " if stopped else "")
                + f"{self.seconds:.0f} s wall on {w} worker{'s' if w != 1 else ''}")
