"""The driver: independent calculations one process each, and one calculation across W processes.

The binary is a black box with a working directory. It reads ``mobcal.in`` from the directory
it is started in, takes no arguments, writes its output where that file says, and exits 0 when
it computed a cross section and 1 when it refused its input. So every run gets a directory of
its own, parallelism is one process per directory, and what the package knows about a run it
learns from the exit status and the output file: a nonzero exit is a failure, and so is an
output without the SUMMARY block that is the evidence the calculation completed, each with the
last line the file holds as its message (``type not defined for atom number``, ``units not
specified``, ``masses do not add up``).

A ``Job`` is one calculation: an input file (a ``.mfj``, or an ion file, ``X.ion.json``,
``mobcal.io.ion``), a gas and a seed, the element table to use, the
package's own for the gas unless the job names another, the random number generator,
Philox4x32-10 unless the job says ``ranlux``, the 2012 generator, which is what reproduces a
2012 number, and the run settings (``mobcal.settings``: the temperature and the five sampling
counts), the 2012 values unless the job says otherwise. The run directory's name carries
``-ranlux`` when the job does, the table when it is not the gas's default (``-lj2000`` for a
shipped set, ``-lj`` and the first eight hex digits of its SHA-256 for any other file), and each
setting that differs from 2012 (``-t298-imp25``), so the same input and seed under another
method never share a directory, and one results folder can hold a whole study.
``run_one`` checks the table (``mobcal.parameters``) and gives the job the directory
``<out_dir>/<name>/`` holding the ``.mfj`` the program reads (``stage``: a ``.mfj`` input
copied as it is, an ion file's written for the job's table, which gives each element its key;
under the name the output will echo, ``<stem>.mfj`` for ``<stem>.ion.json``), its
``mobcal.in``, the table rendered as ``parameters.tab``, the settings rendered as
``settings.tab``, the binary's ``mobcal.out`` and ``stdout.log``, so the directory is a
complete record that reruns by itself; when the run ends it adds ``record.json``, the run's own
account of itself: the package, the binary and its build, the input and its hash (an ion
file's and the staged ``.mfj``'s), the seed, the
parameter set and its hash, the settings and where they came from, the method they make
(``mobcal.methods``: a shipped method's key such as ``2012-philox-he``, the name of the method
file the job was made from with that file's path and SHA-256, or ``custom``), the times, the
verdict and the cross sections. ``run_many`` runs a list of jobs with a cap on how many are in
flight, calls back as each lands, and returns a ``Summary`` that writes ``summary.csv`` and
``summary.json`` beside the run directories, covering every run the folder holds: the batch's
own results and every earlier run's ``record.json``. A ``Stop`` handed to ``run_many`` ends the
batch from another thread: no run starts after it, every process running is killed with its
whole process tree, and the runs it ended report ``stopped`` and keep their directories as
partial records. ``Stop.drain`` is the gentler half: no run starts after it, the runs in flight
finish as usual, and every job not yet started comes back ``waiting``, without a directory or a
record, so the caller knows exactly which runs are left (the window's Pause queue).

A job with ``split=W`` is one calculation across W processes, with the serial result exactly.
Each worker runs in ``<run_dir>/wNN/`` with a ``mobcal.in`` naming it worker ``w`` of ``W``;
it integrates its share of the ``itn * inp`` trajectory blocks per coordinate set (400 at the
2012 settings), draws the random stream through the rest (or, at ``philox``, moves the draw
count past them), and writes a file per block it integrated. The share is dealt one of two
ways (``Job.dealing``): ``static``, a fixed round-robin share of the blocks, or ``claimed``,
where each worker takes the next block no worker has taken, claiming it by creating
``claim-<set>-<k>`` in the run directory (an exclusive create, so one worker wins each), so
that early finishers keep integrating and a slowed worker does not set the wall. When every
worker has landed and every block of the run is on disk (each worker's own share under
``static``; every block exactly once across the workers under ``claimed``), the block files are
copied into the run directory and the program runs there once more as the combining run
(``W 0``): it integrates nothing, reads the blocks back, and makes the sums, the averages and
the SUMMARY with its own statements. That output is the run's output, read exactly as a serial
one. A block missing is a failure, with the worker that owed or claimed it and its output's
last line as the reason, and the combining run never starts. Stale block and claim files are
removed before any start.

How many runs go at once by default is ``cores()``: the physical processor cores, psutil's
count, not the logical processors that hyperthreading doubles (measured on a 40-core
workstation, 80 serial runs at once give 1.28 to 1.36 times the trajectories per second of 40,
and each run then takes half as long again). On Apple Silicon the count includes the
efficiency cores. ``processors()`` is the logical count, the most a user may ask for.

No Qt here. The window calls ``run_many`` from a worker thread and draws from the callbacks.

    from mobcal.run import Job, run_many
    jobs = [Job(Path("choline.mfj"), gas, 5013489, Path("runs")) for gas in ("he", "n2")]
    summary = run_many(jobs, workers=2, progress=print)
    split = run_one(Job(Path("choline.mfj"), "he", 5013489, Path("runs"), split=8))
    as_2012 = run_one(Job(Path("choline.mfj"), "he", 5013489, Path("runs"), generator="ranlux"))
    from_ion = run_one(Job(Path("choline.ion.json"), "n2", 5013489, Path("runs")))
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

import psutil

import mobcal
from mobcal import fortran, methods, parameters, settings
from mobcal.io import ion, mobcalmpi
from mobcal.io.block import all_names, block_of_claim, expected_names
from mobcal.io.infile import (
    DEALINGS,
    DEFAULT_DEALING,
    FIELD_WIDTH,
    GENERATORS,
    RECORD_DEFAULT_DEALING,
    InFile,
    InFileError,
)
from mobcal.io.ion import IonError
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
CLAIM_GLOB = "claim-*"  # a claiming worker's claim files, in the run directory
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
    dealing: str = DEFAULT_DEALING  # how a split run's blocks are shared: claimed, or static
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
        if self.dealing not in DEALINGS:
            raise ValueError(f"dealing must be one of {DEALINGS}, not {self.dealing!r}")
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
    def is_ion(self) -> bool:
        """Whether the input is an ion file, whose ``.mfj`` the run writes, not a ``.mfj``."""
        return ion.is_ion(self.input)

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        rng = "" if self.generator == DEFAULT_RNG else f"-{self.generator}"
        return (f"{ion.stem(self.input)}-{self.gas}-{self.seed}{rng}{self.table_tag}"
                f"{self.settings.suffix()}")

    @property
    def run_dir(self) -> Path:
        return self.out_dir / self.label

    @property
    def staged(self) -> str:
        """The name the ``.mfj`` is staged under, and the name the output echoes: a ``.mfj``
        input's own name, ``<stem>.mfj`` for an ion file."""
        if self.staged_name:
            return self.staged_name
        name = f"{ion.stem(self.input)}.mfj" if self.is_ion else self.input.name
        return name if len(name) <= FIELD_WIDTH else FALLBACK_STAGED_NAME

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
    waiting: bool = False  # never started: the batch was drained first (Stop.drain)

    @property
    def status(self) -> str:
        return ("ok" if self.ok else "stopped" if self.stopped else "waiting" if self.waiting
                else "failed")

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


@dataclass(frozen=True)
class Staged:
    """An input as the run stages it: the ``.mfj`` the program reads, its bytes, and the
    SHA-256 of the input file and of those bytes (one hash for a ``.mfj``, which is staged as
    it is)."""
    mfj: Mfj
    data: bytes
    sha256: str  # the input file's
    staged_sha256: str  # the staged .mfj's


def stage(path: Path, table: ParameterSet) -> Staged:
    """The ``.mfj`` a run on ``table`` stages from ``path``: a ``.mfj`` byte for byte, an ion
    file written by ``Ion.mfj`` for that table. The file is read once, so the hashes are of the
    bytes the run used. Raises OSError, MfjError (a ``.mfj`` the program would stop on, or
    MobCal-MPI's nine-column layout, which the 2012 program misreads as an atom per field
    line) or IonError (an ion file the reader refuses, or one the table cannot write)."""
    path = Path(path)
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if ion.is_ion(path):
        try:
            mfj = ion.Ion.parse(data.decode("utf-8-sig")).mfj(table)
        except UnicodeDecodeError as e:
            raise IonError(f"{path.name}: not UTF-8: {e}") from None
        except IonError as e:
            raise IonError(f"{path.name}: {e}") from None
        staged = mfj.text().encode("latin-1")
        return Staged(mfj, staged, sha, hashlib.sha256(staged).hexdigest())
    text = data.decode("latin-1")
    if mobcalmpi.detect(text):
        raise MfjError(f"{path.name} is in MobCal-MPI's nine-column layout, which the 2012 "
                       "program would misread; `mobcal import` it into an ion file and run that")
    return Staged(Mfj.parse(text), data, sha, sha)


def size(path: Path) -> tuple[int, int]:
    """An input's atoms and coordinate sets, without an element table. Raises OSError,
    MfjError or IonError."""
    if ion.is_ion(path):
        i = ion.Ion.read(path)
        return i.atoms, len(i.conformers)
    m = Mfj.read(path)
    return m.atoms, m.coordinate_sets


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
    running is killed with its whole tree, and the runs it ended report stopped. ``drain``
    only refuses new starts: the runs in flight finish, and the rest report waiting."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._drain = threading.Event()
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

    def drain(self) -> None:
        """Start nothing more; let what is running finish."""
        self._drain.set()

    def draining(self) -> bool:
        return self._drain.is_set()

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


def _prepare(job: Job, d: Path, split: tuple[int, int] | None, pset: ParameterSet,
             staged: Staged, dealing: str = RECORD_DEFAULT_DEALING) -> None:
    """Make ``d`` ready for one start of the program: the staged ``.mfj`` written under its name,
    ``mobcal.in`` written, the element table and the settings rendered, and any output, record,
    block file or claim file of an earlier run removed, so that nothing stale is ever read as
    this run's (a stale claim would keep a block from every worker)."""
    d.mkdir(parents=True, exist_ok=True)
    (d / OUTPUT_NAME).unlink(missing_ok=True)
    (d / RECORD_JSON).unlink(missing_ok=True)
    for glob in (BLOCK_GLOB, CLAIM_GLOB):
        for p in d.glob(glob):
            p.unlink()
    (d / job.staged).write_bytes(staged.data)
    InFile(job.staged, OUTPUT_NAME, job.seed, split, job.generator, dealing).write(d)
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

    The element table and the input are read first, and a table ``mobcal.parameters``
    refuses, a file the program would stop on, an ion file with an element the table lacks or
    a nine-column MobCal-MPI file is reported as failed without starting the binary or making
    the run directory. A stale ``mobcal.out`` in the directory is removed before the run,
    so that an output is never read from an earlier run. A job with ``split`` runs its workers
    and then the combining run; see the module docstring. Every run that got as far as its
    directory ends with ``record.json`` written there, failed or not. A KeyboardInterrupt
    stops the job's processes and is re-raised.
    """
    try:
        pset = parameters.load(job.parameters_path, gas=job.gas)
    except ParameterError as e:
        return _failed(job, f"parameters refused: {e}")
    try:
        staged = stage(job.input, pset)
    except OSError as e:
        return _failed(job, f"cannot read input: {e}")
    except (MfjError, IonError) as e:
        return _failed(job, f"input refused: {e}")
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
    if _running is not None and _running.draining():
        return dataclasses.replace(_failed(job, "not started: the batch was paused"),
                                   waiting=True)
    if on_start is not None:
        on_start(job)
    started = dt.datetime.now().astimezone()
    if job.split:
        r = _run_split(job, command, staged, pset, _running, blocks)
    else:
        r = _run_serial(job, command, staged, pset, _running)
    r = dataclasses.replace(r, parameters=pset.record())
    if not r.ok and _running is not None and _running.is_set():
        r = dataclasses.replace(r, stopped=True, message=f"stopped ({r.message})")
    _write_record(r, command, staged, started)
    return r


def _run_serial(job: Job, command: list[str], staged: Staged, pset: ParameterSet,
                running: Stop | None) -> Result:
    d = job.run_dir
    _prepare(job, d, None, pset, staged)
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


def _run_split(job: Job, command: list[str], staged: Staged, pset: ParameterSet,
               running: Stop | None, blocks: BlocksProgress | None) -> Result:
    total, d = job.split, job.run_dir
    coordinate_sets = staged.mfj.coordinate_sets
    blocks_per_set = job.settings.blocks_per_set
    claimed = job.dealing == "claimed"
    every = all_names(coordinate_sets, blocks_per_set)
    expected = {w: expected_names(coordinate_sets, total, w, blocks_per_set)
                for w in range(1, total + 1)}
    n_expected = len(every)
    _prepare(job, d, (total, 0), pset, staged)  # the combining run, which never claims
    for w in expected:
        _prepare(job, job.worker_dir(w), (total, w), pset, staged, job.dealing)

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

    if running is not None and running.is_set():
        for p in procs.values():
            _kill_tree(p)
            p.wait()
        return _failed(job, "split run ended before its combining run", None,
                       time.perf_counter() - t0)

    def why(w: int) -> str:
        out = job.worker_dir(w) / OUTPUT_NAME
        last = OutFile.read(out).last_line if out.is_file() else ""
        return last or f"exit {procs[w].returncode}"

    problems = []
    if not claimed:
        for w, names in expected.items():
            missing = [n for n in names if not (job.worker_dir(w) / n).is_file()]
            if missing:
                problems.append(f"worker {w}: {len(missing)} of {len(names)} blocks missing "
                                f"({why(w)})")
    else:
        problems = _judge_claimed(job, every, d, why)
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


def _judge_claimed(job: Job, every: list[str], d: Path, why: Callable[[int], str]) -> list[str]:
    """A claimed split run once every worker has exited: every block of the run must be on
    disk exactly once across the worker directories. A block that is missing was either
    claimed by a worker that never wrote it (the claim file names the worker) or never claimed
    at all (every worker stopped before reaching it); a block written twice means the exclusive
    create did not hold, which the platforms do not do, and is reported for what it is."""
    found: dict[str, list[int]] = {}
    for w in range(1, job.split + 1):
        for p in job.worker_dir(w).glob(BLOCK_GLOB):
            found.setdefault(p.name, []).append(w)
    claimed_by: dict[str, int] = {}
    for p in d.glob(CLAIM_GLOB):
        try:
            claimed_by[block_of_claim(p.name)] = int(p.read_text(encoding="ascii").split()[0])
        except (OSError, ValueError, IndexError):
            claimed_by[block_of_claim(p.name)] = 0
    problems = []
    unwritten: dict[int, list[str]] = {}
    unclaimed = []
    for n in every:
        if n in found:
            continue
        if n in claimed_by:
            unwritten.setdefault(claimed_by[n], []).append(n)
        else:
            unclaimed.append(n)
    for w, names in sorted(unwritten.items()):
        who = f"worker {w}" if w else "a worker"
        problems.append(f"{who}: {len(names)} claimed {'block' if len(names) == 1 else 'blocks'}"
                        f" not written, {names[0]} first ({why(w) if w else 'claim unreadable'})")
    if unclaimed:
        problems.append(f"{len(unclaimed)} {'block' if len(unclaimed) == 1 else 'blocks'} never "
                        f"claimed, {unclaimed[0]} first ({why(1)})")
    for n, ws in sorted(found.items()):
        if len(ws) > 1:
            problems.append(f"{n} written by workers {' and '.join(map(str, ws))}")
        elif n not in every:
            problems.append(f"{n} is not a block of this run")
    return problems


def _write_record(r: Result, command: list[str], staged: Staged, started: dt.datetime) -> Path:
    """Write ``record.json`` into the run's directory: what ran, on what, with which table, and
    what came of it. Its numbers are the ``Result``'s; the output file stays the evidence.

    The ``input`` block names the file the job was given, its SHA-256, the staged name and the
    size. For an ion file it adds ``format`` (``mobcal-ion``) and ``staged_sha256``, the hash of
    the ``.mfj`` written from it, which the table decides as much as the file does; a ``.mfj``
    is staged as it is and its block is what it always was."""
    j, mfj = r.job, staged.mfj
    inp = {"path": str(j.input), "staged_name": j.staged, "sha256": staged.sha256,
           "atoms": mfj.atoms, "coordinate_sets": mfj.coordinate_sets}
    if j.is_ion:
        inp |= {"format": ion.FORMAT, "staged_sha256": staged.staged_sha256}
    exe = Path(command[0])
    build = fortran.read_manifest(exe.parent).get("binaries", {}).get(exe.name)
    doc = {
        "mobcal_version": mobcal.__version__,
        "name": j.label,
        "binary": {"gas": j.gas, "path": str(exe), "command": list(command), "build": build},
        "input": inp,
        "mobcal_in": {"seed": j.seed, "generator": j.generator, "split": j.split,
                      "dealing": j.dealing if j.split else None},
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


def cores() -> int:
    """The physical processor cores, the default for every count of runs or processes: psutil's,
    or ``os.cpu_count()`` where psutil cannot tell."""
    return psutil.cpu_count(logical=False) or os.cpu_count() or 1


def processors() -> int:
    """The logical processors, hyperthreads counted: the most runs at once a user may set."""
    return os.cpu_count() or 1


Progress = Callable[[Result, int, int], None]
"""Called as each run lands, with the result, how many have landed and how many there are."""


def run_many(jobs: Iterable[Job], workers: int | None = None, progress: Progress | None = None,
             launcher: Launcher | None = None, blocks: BlocksProgress | None = None,
             stop: Stop | None = None,
             on_start: Callable[[Job], None] | None = None) -> Summary:
    """Run the jobs with at most ``workers`` in flight (default: ``cores()``).

    Each job runs in its own directory from a supervising thread; results are returned in the
    jobs' order whatever order they land in. ``on_start`` is called as each job's program is
    about to start, once its input and table have been read. A split job counts as one job in
    flight and starts its own W processes. ``stop`` ends the batch from another thread: every
    job still to start returns at once as stopped, and every running one is killed and reports
    stopped; ``stop.drain()`` lets the running ones finish and returns the rest as waiting. A
    KeyboardInterrupt stops every running binary and is re-raised.
    """
    jobs = list(jobs)
    workers = max(1, min(workers or cores(), len(jobs) or 1))
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
        return [r for r in self.results if not r.ok and not r.stopped and not r.waiting]

    @property
    def stopped(self) -> list[Result]:
        return [r for r in self.results if r.stopped]

    @property
    def waiting(self) -> list[Result]:
        """The jobs a drain left unstarted."""
        return [r for r in self.results if r.waiting]

    def write(self, out_dir: Path) -> tuple[Path, Path]:
        """Write ``summary.csv`` (one row per run) and ``summary.json`` (the same, with the
        per-set values and the provenance) into ``out_dir`` and return the two paths. They
        cover every run the folder holds, in name order: this batch's results, and every other
        run directory's ``record.json``; ``summary.json`` also names this batch's runs, its
        workers and its wall time. A waiting job ran nowhere and is left out of both, so a
        drained batch's summary is the folder as it stands, and an earlier run of the same name
        keeps its row."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path, json_path = out_dir / SUMMARY_CSV, out_dir / SUMMARY_JSON
        found = read_records(out_dir)
        ran = [r for r in self.results if not r.waiting]
        found.update((r.job.label, r.record()) for r in ran)
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
            "batch": [r.job.label for r in ran],
            "runs": runs,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return csv_path, json_path

    def __str__(self) -> str:
        n, bad, stopped = len(self.results), len(self.failed), len(self.stopped)
        waiting, w = len(self.waiting), self.workers
        return (f"{n} run{'s' if n != 1 else ''}, {len(self.ok)} ok, {bad} failed, "
                + (f"{stopped} stopped, " if stopped else "")
                + (f"{waiting} waiting, " if waiting else "")
                + f"{self.seconds:.0f} s wall on {w} worker{'s' if w != 1 else ''}")
