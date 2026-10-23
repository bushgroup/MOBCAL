"""Session plumbing: the one build-and-run pool the real-binary tests share, and the choline
runs' wall times, printed at the end of the session.

The pool builds each gas the session's tests ask for, then runs every real choline calculation
they need in one ``run_many`` batch: the serial run per gas for the regression gate, and the
split runs in helium for the exactness tests, each on its own processes. The one-cycle nitrogen
check's worker, for which ``mobcal.run`` has no mode (a split job runs all W workers and the
combining run), is started directly before the batch and waited for after it. Everything that
needs gfortran waits for the longest of them, not for their sum. Without gfortran the pool
skips, unless ``MOBCAL_REQUIRE_GFORTRAN`` is set, as CI sets it, in which case it fails.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import gate
from mobcal import fortran, parameters
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile
from mobcal.run import LOG_NAME, OUTPUT_NAME, Job, run_many

_RUN_TIMES = pytest.StashKey[dict[str, float]]()


@pytest.fixture(scope="session")
def run_times(pytestconfig) -> dict[str, float]:
    return pytestconfig.stash.setdefault(_RUN_TIMES, {})


def pytest_terminal_summary(terminalreporter, config):
    times = config.stash.get(_RUN_TIMES, {})
    if not times:
        return
    terminalreporter.section("choline run times")
    terminalreporter.write_line(fortran.describe())
    for name, s in times.items():
        terminalreporter.write_line(f"{name}: {s:.1f} s wall, binary alone")


@pytest.fixture(scope="session")
def gfortran():
    gf = fortran.find_gfortran()
    if gf is None:
        msg = "no gfortran found ($FC, PATH, or MSYS2)"
        if os.environ.get("MOBCAL_REQUIRE_GFORTRAN"):
            pytest.fail(msg + " and MOBCAL_REQUIRE_GFORTRAN is set")
        pytest.skip(msg)
    return gf


def _params(session, name: str) -> set:
    return {item.callspec.params[name] for item in session.items
            if getattr(item, "callspec", None) is not None and name in item.callspec.params}


def selected_gases(session) -> list[str]:
    """The gases the collected (not deselected) tests ask for, so a deselected gas never runs."""
    gases = _params(session, "choline")
    return [g for g in fortran.GASES if g in gases] or ["he"]


def selected_splits(session) -> list[int]:
    """The worker counts the collected split tests ask for (helium only)."""
    return sorted(_params(session, "W"))


def selected_cycles(session) -> list[str]:
    """The gases whose one-cycle check a collected test asks for (the ``n2_cycle`` fixture)."""
    names = {n for item in session.items for n in getattr(item, "fixturenames", ())}
    return [g for g in fortran.GASES if f"{g}_cycle" in names]


class _Worker:
    """Choline as worker ``gate.CYCLE`` of a split run, started alone in ``d`` and prepared as
    ``mobcal.run`` prepares a worker: the input staged under the reference's name, ``mobcal.in``
    at the reference's seed with the fourth record, the shipped table rendered."""

    def __init__(self, binary: Path, gas: str, ref: OutFile, d: Path):
        self.gas, self.ref, self.d = gas, ref, d
        shutil.copyfile(gate.CHOLINE, d / ref.input_name)
        InFile(ref.input_name, OUTPUT_NAME, ref.seed, gate.CYCLE).write(d)
        parameters.shipped(gas).render(d)
        with open(d / LOG_NAME, "wb") as log:
            self.proc = subprocess.Popen([str(binary)], cwd=d, stdout=log,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        self.started = time.perf_counter()

    def wait(self) -> gate.WorkerRun:
        rc = self.proc.wait()
        seconds = time.perf_counter() - self.started
        out = self.d / OUTPUT_NAME
        log = (self.d / LOG_NAME).read_text(errors="replace")[-2000:]
        return gate.WorkerRun(self.gas, self.ref, rc, seconds,
                              OutFile.read(out) if out.is_file() else None, log)

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture(scope="session")
def pool(request, gfortran, tmp_path_factory, run_times) -> gate.Pool:
    """Build each selected gas, then run every real choline calculation at once."""
    gases = selected_gases(request.session)
    splits = selected_splits(request.session)
    cycles = selected_cycles(request.session)
    if splits and "he" not in gases:
        gases = ["he", *gases]
    built = [g for g in fortran.GASES if g in gases or g in cycles]
    binaries = {g: fortran.build(g, tmp_path_factory.mktemp(f"bin-{g}"), gfortran).binary
                for g in built}
    p = gate.Pool(binaries)
    refs = {g: OutFile.read(gate.REFS / gate.REFERENCE[g]) for g in built}
    for g, ref in refs.items():
        assert ref.input_name and ref.seed is not None, f"{g}: reference has no SUMMARY"
    out = tmp_path_factory.mktemp("gate")
    jobs = [Job(gate.CHOLINE, g, refs[g].seed, out, name=g, staged_name=refs[g].input_name)
            for g in gases]
    jobs += [Job(gate.CHOLINE, "he", refs["he"].seed, out, name=f"split-{w}",
                 staged_name=refs["he"].input_name, split=w) for w in splits]
    # Nitrogen's one cycle is the longest run of a default session, so it starts first.
    workers = [_Worker(binaries[g], g, refs[g], tmp_path_factory.mktemp(f"cycle-{g}"))
               for g in cycles]
    try:
        summary = run_many(jobs, workers=len(jobs), launcher=p.launcher)
        for r in summary.results:
            run_times[r.job.label] = r.seconds
            log = (r.job.run_dir / LOG_NAME).read_text(errors="replace")[-2000:]
            assert r.ok, f"{r.job.label}: {r.message}\n{log}"
            if r.job.split:
                p.splits[r.job.split] = r
            else:
                p.runs[r.job.gas] = gate.GateRun(r.job.gas, refs[r.job.gas],
                                                 OutFile.read(r.output))
        for w in workers:
            p.cycles[w.gas] = w.wait()
            W, me = gate.CYCLE
            run_times[f"{w.gas} worker {me} of {W}"] = p.cycles[w.gas].seconds
    finally:
        for w in workers:
            w.stop()
    return p
