"""Self-check for a fresh clone: no gfortran and no lab repo needed.

Every check here must pass in a bare public clone. Checks that need something a clone does not
ship -- a Fortran compiler, the lab repository -- are reported as SKIPPED when it is absent,
never as FAIL.

What it covers today: the package imports, the version declarations agree, the six files under
fortran/ are the 2012 release byte for byte, the lower layers stay free of Qt, nothing shipped
cites the development record by a path only a lab checkout resolves, and, when gfortran is
present, both sources compile with the recorded flags, the binaries exist, and the compiler
issued no warnings. Tasks add sections as they land code.

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
                if f.endswith((".py", ".md", ".toml", ".iss", ".spec", ".yml", ".yaml", ".txt")):
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
    check_true("license is GPL-3.0-or-later", proj.get("license") == "GPL-3.0-or-later")
    check_true("requires-python pins 3.12", proj.get("requires-python") == "==3.12.*")

    section("fortran/ is the 2012 code")
    from mobcal import fortran
    problems = fortran.verify_sources()
    for p in problems:
        print("     " + p)
    check_true("six pinned files present and byte-identical to the 2012 release", not problems)
    check_true("-fno-automatic is in FFLAGS", "-fno-automatic" in fortran.FFLAGS)
    check_true("-std=legacy is in FFLAGS", "-std=legacy" in fortran.FFLAGS)

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

    section("build")
    gf = fortran.find_gfortran()
    if gf is None:
        skip("compile both gases", "no gfortran found")
    else:
        print("     " + fortran.describe())
        with tempfile.TemporaryDirectory() as td:
            from pathlib import Path
            for gas in fortran.GASES:
                try:
                    b = fortran.build(gas, Path(td))
                except subprocess.CalledProcessError as e:
                    check_true(f"{gas}: compiled with recorded flags (exit {e.returncode})", False)
                    continue
                check_true(f"{gas}: compiled with recorded flags, binary exists",
                           b.binary.is_file())
                check_true(f"{gas}: zero compiler warnings ({b.warnings})", b.warnings == 0)

    print()
    print(f"{len(FAIL)} failed, {len(SKIPPED)} skipped")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
