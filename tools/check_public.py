"""Self-check for a fresh clone: no gfortran and no lab repo needed.

Every check here must pass in a bare public clone. Checks that need something a clone does not
ship -- a Fortran compiler, the lab repository -- are reported as SKIPPED when it is absent,
never as FAIL.

What it covers today: the package imports, the three version declarations agree (pyproject.toml,
mobcal.__version__, packaging/mobcal.iss), the files under fortran/ are the pinned files
(the 2012 release plus the counted changes fortran/README.md lists), every element table
under src/mobcal/parameters/ (each gas's default set and the named alternates) is its pinned
file and loads and renders, the settings file under
src/mobcal/settings/ is the pinned file and holds the 2012 values, the bounds and defaults
fortran/mobcal_settings.inc declares are the ones mobcal.settings mirrors, the lower layers stay
free of Qt, nothing shipped cites the development record by a path only a lab checkout resolves,
the atom bound fortran/mobcal_arrays.inc declares is the one mobcal.io.mfj.MAX_ATOMS mirrors, the
ORCA outputs under tests/data/qm/ are the files tests/data/qm/SHA256SUMS pins and one of them
imports through cclib to an .mfj that reads back as written, and,
when gfortran is present, both sources compile with the recorded flags, the binaries
exist, the compiler issued no warnings, and `mobcal self-check` passes against them. Tasks add
sections as they land code.

Run:  uv run tools/check_public.py
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

FAIL: list[str] = []
SKIPPED: list[str] = []


def check_true(name: str, cond: object) -> None:
    print("{:4s} {}".format("OK" if cond else "FAIL", name))
    if not cond:
        FAIL.append(name)


def skip(name: str, why: str) -> None:
    print(f"SKIP {name} ({why})")
    SKIPPED.append(name)


def section(title: str) -> None:
    print()
    print("--- " + title + " " + "-" * max(3, 72 - len(title)))


def shipped_text_files() -> list[str]:
    out = []
    for top in ("src", "tools", "tests", "docs", "packaging", "fortran"):
        for dirpath, _, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if f.endswith((".py", ".md", ".toml", ".iss", ".spec", ".ps1", ".yml",
                              ".yaml", ".txt")):
                    out.append(os.path.join(dirpath, f))
    out += [os.path.join(ROOT, f) for f in ("README.md", "CLAUDE.md", "pyproject.toml")]
    return [p for p in out if os.path.isfile(p)]


def main() -> int:
    section("package")
    mobcal = importlib.import_module("mobcal")
    check_true("mobcal imports", True)
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        proj = tomllib.load(f)["project"]
    check_true(f"pyproject version {proj['version']} == mobcal.__version__ {mobcal.__version__}",
               proj["version"] == mobcal.__version__)
    with open(os.path.join(ROOT, "packaging", "mobcal.iss"), encoding="utf-8") as f:
        iss = re.search(r'^#define MyAppVersion "([^"]*)"', f.read(), re.M)
    iss_version = iss.group(1) if iss else None
    check_true(f"packaging/mobcal.iss version {iss_version} == {proj['version']}",
               iss_version == proj["version"])
    check_true("license is GPL-3.0-or-later", proj.get("license") == "GPL-3.0-or-later")
    check_true("requires-python pins 3.12", proj.get("requires-python") == "==3.12.*")

    section("fortran/ is the pinned code")
    from mobcal import fortran
    problems = fortran.verify_sources()
    for p in problems:
        print("     " + p)
    check_true(f"{len(fortran.SHA256)} pinned files present and byte-identical to their pins",
               not problems)
    check_true("-fno-automatic is in FFLAGS", "-fno-automatic" in fortran.FFLAGS)
    check_true("-std=legacy is in FFLAGS", "-std=legacy" in fortran.FFLAGS)

    section("the atom bound")
    from mobcal.io.mfj import MAX_ATOMS
    with open(fortran.FORTRAN_DIR / "mobcal_arrays.inc", encoding="ascii") as f:
        bound = [int(m) for m in re.findall(r"^      parameter \(len=(\d+)\)$", f.read(), re.M)]
    check_true(f"mobcal_arrays.inc declares len={bound} once, and mobcal.io.mfj.MAX_ATOMS "
               f"{MAX_ATOMS} mirrors it", bound == [MAX_ATOMS])

    section("the element tables are the pinned files")
    from mobcal import parameters
    problems = parameters.verify()
    for p in problems:
        print("     " + p)
    sets = [(gas, name) for gas in fortran.GASES for name in parameters.names(gas)]
    check_true(f"all {len(parameters.SHA256)} TOML files present and byte-identical to their "
               "pins, one per shipped set",
               not problems and sorted(parameters.SHA256) == sorted(
                   parameters.SETS[g][n] for g, n in sets))
    with tempfile.TemporaryDirectory() as td:
        for gas, name in sets:
            try:
                ps = parameters.shipped(gas, name)
                text = ps.render(td).read_text(encoding="ascii")
            except parameters.ParameterError as e:
                check_true(f"{gas} {name}: the shipped table loads ({e})", False)
                continue
            check_true(f"{gas} {name}: {ps.name!r} loads and renders, {len(ps.elements)} "
                       "elements, no '/' or ',' in the rendered table",
                       not set("/,") & set(text) and text.startswith(parameters.MAGIC))

    section("the run settings")
    from mobcal import settings
    problems = settings.verify()
    for p in problems:
        print("     " + p)
    check_true(f"{settings.FILE} present, byte-identical to its pin, and the 2012 values",
               not problems)
    with open(fortran.FORTRAN_DIR / "mobcal_settings.inc", encoding="ascii") as f:
        inc = f.read()
    declared = {m[1]: int(m[2]) for m in re.finditer(r"parameter \((mx\w+)=(\d+)\)", inc)}
    mirrored = {"imp": "mximp", "itn": "mxitn", "inp": "mxinp", "inum": "mxinum",
                "inor": "mxinor"}
    check_true(f"mobcal_settings.inc declares the bounds {declared}, and mobcal.settings.BOUNDS "
               f"mirrors them",
               all(settings.BOUNDS[k] == (1, declared.get(v)) for k, v in mirrored.items())
               and settings.MAX_POINTS == declared.get("mxtot"))
    defaults = dict(re.findall(r"^      (t|imp|itn|inp|inum|inor)=(\S+)$", inc, re.M))
    check_true(f"mobcal_settings.inc's defaults {defaults} are mobcal.settings.DEFAULTS",
               defaults == {"t": "301.d0", "imp": "1000", "itn": "10", "inp": "40",
                            "inum": "250000", "inor": "30"}
               and settings.DEFAULTS.values() == {"temperature": 301.0, "imp": 1000, "itn": 10,
                                                  "inp": 40, "inum": 250000, "inor": 30})

    section("layers")
    lower = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, "src", "mobcal")):
        if os.path.basename(dirpath) == "app" or f"{os.sep}app{os.sep}" in dirpath + os.sep:
            continue
        lower += [os.path.join(dirpath, f) for f in files if f.endswith(".py")]
    qt = []
    for p in lower:
        with open(p, encoding="utf-8") as f:
            if re.search(r"^\s*(import|from)\s+(PySide6|PyQt\d|qtpy)", f.read(), re.M):
                qt.append(os.path.relpath(p, ROOT))
    check_true("no Qt import below mobcal.app" + (f": {qt}" if qt else ""), not qt)

    section("public hygiene")
    bad = []
    pat = re.compile(r"MOBCAL-2012-notes|skedasis|aphixis|MOBCAL-lab[/\\](?:tasks|notes|digests)",
                     re.I)
    for p in shipped_text_files():
        with open(p, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if pat.search(line) and "check_public.py" not in p:
                    bad.append(f"{os.path.relpath(p, ROOT)}:{i}")
    check_true("nothing shipped names lab material by path" + (f": {bad}" if bad else ""), not bad)
    lab = mobcal.lab_dir()
    print(f"     lab_dir() -> {lab}")
    check_true("lab_dir() returns a Path or None", lab is None or hasattr(lab, "is_dir"))

    section("formats")
    from mobcal.io.infile import InFile
    from mobcal.io.mfj import Mfj
    from mobcal.io.outfile import OutFile
    choline = Mfj.read(fortran.FORTRAN_DIR / "Choline.mfj")
    check_true("Choline.mfj reads: 1 coordinate set, 21 atoms, ang, calc",
               (choline.coordinate_sets, choline.atoms, choline.units, choline.charge_mode)
               == (1, 21, "ang", "calc"))
    shipped = InFile.read(fortran.FORTRAN_DIR / "mobcal.in")
    check_true("mobcal.in reads: Choline.mfj at seed 5013489",
               (shipped.input_name, shipped.seed) == ("Choline.mfj", 5013489))
    refs = {g: OutFile.read(fortran.FORTRAN_DIR / "sample-output" / f"Choline_{g}.out")
            for g in ("He", "N2")}
    check_true("both references hold a SUMMARY block with a TM cross section",
               all(o.ok and "TM" in o.cross_sections for o in refs.values()))

    section("the import")
    import hashlib
    from pathlib import Path

    from mobcal.io import structure
    qm = Path(ROOT) / "tests" / "data" / "qm"
    pins = dict(reversed(line.split("  ", 1)) for line in
                (qm / "SHA256SUMS").read_text(encoding="ascii").splitlines())
    bad = [n for n, h in pins.items() if not (qm / n).is_file()
           or hashlib.sha256((qm / n).read_bytes()).hexdigest() != h]
    check_true(f"{len(pins)} files under tests/data/qm/ are their pins" +
               (f": {bad}" if bad else ""), not bad)
    try:
        imp = structure.convert(structure.read(qm / "orca" / "choline_sp" / "choline_sp.out"),
                                "chelpg")
        ok = Mfj.parse(imp.mfj.text()) == imp.mfj and imp.mfj.atoms == 21
        why = imp.record["source"]["reader"]
    except structure.StructureError as e:
        ok, why = False, str(e)
    check_true(f"choline_sp.out imports with its CHELPG charges and reads back ({why})", ok)

    section("build")
    gf = fortran.find_gfortran()
    if gf is None:
        skip("compile both gases", "no gfortran found")
        skip("the driver reports a refused input as failed", "no gfortran found")
        skip("mobcal self-check passes against them", "no gfortran found")
    else:
        print("     " + fortran.describe())
        with tempfile.TemporaryDirectory() as td:
            from pathlib import Path

            from mobcal.run import Job, run_one
            binaries = {}
            for gas in fortran.GASES:
                try:
                    b = fortran.build(gas, Path(td))
                except subprocess.CalledProcessError as e:
                    check_true(f"{gas}: compiled with recorded flags (exit {e.returncode})", False)
                    continue
                check_true(f"{gas}: compiled with recorded flags, binary exists",
                           b.binary.is_file())
                check_true(f"{gas}: zero compiler warnings ({b.warnings})", b.warnings == 0)
                binaries[gas] = b.binary
            # An element neither table defines (bromine, key 35): the program writes its
            # refusal and exits 1 in well under a second, and the driver must call that failed.
            hbr = Path(td) / "hbr.mfj"
            hbr.write_text("HBr+\n1\n2\nang\ncalc\n1.0000\n 0 0 0 35 0.5\n 1.41 0 0 1 0.5\n",
                           encoding="latin-1", newline="\n")
            for gas, binary in binaries.items():
                r = run_one(Job(hbr, gas, 1, Path(td) / "runs"), lambda _job, b=binary: [str(b)])
                check_true(f"{gas}: the driver reports the refused input as failed "
                           f"({r.message!r})",
                           not r.ok and r.returncode == 1 and "type not defined" in r.message)
            # The installed program's self-check, against these binaries and their build.json.
            import contextlib
            import io

            from mobcal import selfcheck
            saved = os.environ.get("MOBCAL_BIN_DIR")
            os.environ["MOBCAL_BIN_DIR"] = td
            try:
                with contextlib.redirect_stdout(io.StringIO()) as report:
                    rc = selfcheck.run()
            finally:
                if saved is None:
                    del os.environ["MOBCAL_BIN_DIR"]
                else:
                    os.environ["MOBCAL_BIN_DIR"] = saved
            if rc:
                print(report.getvalue())
            check_true("mobcal self-check passes against them", rc == 0)

    print()
    print(f"{len(FAIL)} failed, {len(SKIPPED)} skipped")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
