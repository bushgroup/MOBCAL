"""``mobcal self-check``: is this copy of MOBCAL able to compute a cross section?

Written for the installed program, where there is no compiler, no tests and no checkout to fall
back on, and run the same way from a source checkout. Each stage prints one timed row, so a
failure names the stage that failed:

    version     the package version, and whether this is an installed copy or a checkout
    parameters  the two element tables (``mobcal.parameters``) and the 2012 settings file
                (``mobcal.settings``) are the files pinned by their SHA-256, and each loads
                and passes the checks a run puts it through
    binaries   both binaries are in ``fortran.binary_dir()``, are the files recorded in its
                ``build.json`` when they were built, were built from the pinned sources (by their
                SHA-256 pins) and with ``-fno-automatic``
    start       each binary starts, reads its ``mobcal.in``, and refuses an input naming an
                element its tables do not define; the driver reads the refusal as a failure.
                Under a second, and it exercises everything a calculation does except the
                trajectories
    choline     with ``--choline`` only: the 2012 choline input in helium at the 2012 seed
                and the 2012 generator, RANLUX (the driver's default is Philox, which gives
                other digits), with the three cross sections compared with the 2012 output
                within 0.1 %, the regression gate's second tier. About three minutes

``--report PATH`` writes the same lines to a file as well. The exit status is 1 if any stage
failed. No Qt here.
"""

from __future__ import annotations

import platform
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import mobcal
from mobcal import fortran, parameters, settings
from mobcal.io.outfile import OutFile
from mobcal.run import Job, run_one

CHOLINE_SEED = 5013489
CHOLINE_RNG = "ranlux"  # the generator the 2012 output was produced with
TOLERANCE = 1e-3  # relative, the regression gate's second tier

# Bromine (key 35) is in neither gas's element table, so the program writes its header, then
# "type not defined for atom number", and exits 1.
_UNDEFINED_ELEMENT = "HBr+\n1\n2\nang\ncalc\n1.0000\n 0 0 0 35 0.5\n 1.41 0 0 1 0.5\n"


class _Report:
    def __init__(self, path: Path | None) -> None:
        self.lines: list[str] = []
        self.path = path
        self.failed = 0
        self.stages = 0

    def line(self, text: str) -> None:
        print(text, flush=True)
        self.lines.append(text)
        if self.path is not None:
            self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

    def stage(self, fn: Callable[[], tuple[bool, str, list[str]]]) -> bool:
        """Run one stage; it returns (passed, its row's text, detail lines)."""
        t0 = time.perf_counter()
        try:
            ok, text, detail = fn()
        except Exception as e:  # a stage that raises is a failed stage, reported as one
            ok, text, detail = False, f"{fn.__name__.lstrip('_')}: {type(e).__name__}", [str(e)]
        self.stages += 1
        self.failed += not ok
        self.line(f"{'OK' if ok else 'FAIL':4s} {time.perf_counter() - t0:7.2f} s  {text}")
        for d in detail:
            self.line(f"{'':16s}{d}")
        return ok


def _version() -> tuple[bool, str, list[str]]:
    where = (f"installed at {fortran.install_dir()}" if fortran.frozen()
             else f"source checkout at {mobcal.ROOT}")
    return True, f"mobcal {mobcal.__version__}", [
        where, f"Python {platform.python_version()} on {platform.platform()}"]


def _parameters() -> tuple[bool, str, list[str]]:
    d = parameters.PARAMETERS_DIR
    problems = parameters.verify(d)
    if problems:
        return False, f"element tables in {d}", problems
    problems = settings.verify(settings.SETTINGS_DIR)
    if problems:
        return False, f"settings file in {settings.SETTINGS_DIR}", problems
    detail = []
    for gas in fortran.GASES:
        for name in parameters.names(gas):
            ps = parameters.shipped(gas, name)
            default = " (default)" if name == parameters.DEFAULT else ""
            detail.append(f"{ps.path.name}: set {name}{default}, {ps.name}, "
                          f"{len(ps.elements)} elements, sha256 {ps.sha256[:12]}")
    st = settings.shipped()
    detail.append(f"{settings.FILE}: the 2012 settings, sha256 {st.source.sha256[:12]}")
    return True, (f"{', '.join(parameters.SHA256)} in {d} and {settings.FILE} in "
                  f"{settings.SETTINGS_DIR}, as pinned"), detail


def _binaries() -> tuple[bool, str, list[str]]:
    d = fortran.binary_dir()
    problems = fortran.verify_binaries(d)
    if problems:
        return False, f"binaries in {d}", problems
    recs = fortran.read_manifest(d)["binaries"]
    rec = recs[fortran.binary_name(fortran.GASES[0])]
    detail = [f"built by {rec.get('compiler') or 'an unrecorded compiler'} with "
              f"{' '.join(rec.get('flags', []))}"]
    if rec.get("commit"):
        detail.append(f"from commit {fortran.short_commit(rec['commit'])}, "
                      f"{rec.get('built', '')}")
    return True, (f"{', '.join(fortran.binary_name(g) for g in fortran.GASES)} in {d}, as built, "
                  "from the pinned sources"), detail


def _start(gas: str) -> Callable[[], tuple[bool, str, list[str]]]:
    def start() -> tuple[bool, str, list[str]]:
        binary = fortran.find_binary(gas)
        with tempfile.TemporaryDirectory(prefix="mobcal-self-check-") as td:
            inp = Path(td) / "hbr.mfj"
            inp.write_text(_UNDEFINED_ELEMENT, encoding="latin-1", newline="\n")
            r = run_one(Job(inp, gas, 1, Path(td) / "runs"), lambda _job: [str(binary)])
        ok = not r.ok and r.returncode == 1 and "type not defined" in r.message
        return ok, f"{gas}: the binary starts and refuses an undefined element", (
            [] if ok else [f"expected the refusal, got: {r.message or 'a completed run'}"])
    start.__name__ = f"start_{gas}"
    return start


def _choline() -> tuple[bool, str, list[str]]:
    ex = fortran.examples_dir()
    ref = OutFile.read(ex / "sample-output" / "Choline_He.out").cross_sections
    with tempfile.TemporaryDirectory(prefix="mobcal-self-check-") as td:
        r = run_one(Job(ex / "Choline.mfj", "he", CHOLINE_SEED, Path(td),
                        generator=CHOLINE_RNG))
    if not r.ok:
        return False, "choline in helium", [r.message]
    detail, ok = [], True
    for k in ("PA", "EHS", "TM"):
        got, want = r.cross_sections.get(k), ref.get(k)
        within = got is not None and want is not None and abs(got / want - 1) <= TOLERANCE
        ok &= within
        detail.append(f"{k:3s} {got if got is not None else 'missing'} A^2 against 2012's "
                      f"{want}" + ("" if within else f"  (outside {TOLERANCE:.1%})"))
    return ok, (f"choline in helium at seed {CHOLINE_SEED} under RANLUX, against the 2012 "
                "output"), detail


def run(choline: bool = False, report: Path | None = None) -> int:
    """Run the stages, print the report, and return the exit status: 0 if all passed."""
    rep = _Report(report)
    rep.line(f"mobcal self-check, {time.strftime('%Y-%m-%d %H:%M:%S')}")
    t0 = time.perf_counter()
    rep.stage(_version)
    rep.stage(_parameters)
    if rep.stage(_binaries):
        for gas in fortran.GASES:
            rep.stage(_start(gas))
        if choline:
            rep.stage(_choline)
    verdict = "passed" if not rep.failed else f"FAILED ({rep.failed} of {rep.stages} stages)"
    rep.line(f"self-check {verdict} in {time.perf_counter() - t0:.1f} s")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(run())
