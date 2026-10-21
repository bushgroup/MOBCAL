"""Locate, verify and build the 2012 Fortran.

The six files under ``fortran/`` are the 2012 release of MOBCAL, byte for byte, and this module
is where that claim is made checkable: ``SHA256`` pins each one and ``verify_sources`` compares.
A change to any of them is a decision taken in the lab record, lands with new pins in the same
commit, and counts its diff in the commit message.

The build recipe is also stated here and nowhere else. ``-fno-automatic`` is mandatory: the code
relies on local variables keeping their values between calls, which g77 gave it by default. An
optimized gfortran build without the flag runs to completion and loses every trajectory, loudly
(zero completed), so this is not the kind of defect that quietly moves a published number. With
the flag, optimized builds reproduce the 2012 reference outputs byte for byte on Windows, macOS
and Linux. ``-std=legacy`` silences the Fortran 2018 deleted-feature diagnostics (DO loops ending
on a non-CONTINUE statement, arithmetic IF, and the like) and changes no generated code; the
warning count it leaves is expected to be zero, so a nonzero count is worth reading. ``-static``
is passed on Windows only: a dynamically linked MSYS2 binary dies silently when launched from
PowerShell, Apple's linker has no fully static mode, and it buys nothing on Linux.

``build`` captures what the compiler writes and counts its warnings; the self-check and CI fail on
any. Without ``-std=legacy`` each source draws 64.

    uv run mobcal build            # both gases into build/fortran/
    uv run mobcal build --gas he   # one
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from mobcal import ROOT

FORTRAN_DIR = ROOT / "fortran"

GASES = ("he", "n2")
SOURCE = {"he": "mobcal_He.f", "n2": "mobcal_N2.f"}

# The 2012 files, as committed at bushgroup/MOBCAL-2012 tag v1.0 (commit 4f3be72) and copied
# here from those blobs on 2026-10-21. LF line endings; see .gitattributes.
SHA256 = {
    "mobcal_He.f": "0a9e6bdc490343283780d26a8db8d12af5bcac55241d63f7887a27a23cb69e42",
    "mobcal_N2.f": "bbe692fe328ef8d9b102ee868d6fd64494f1fe81c579e902a3916f7e3b2525ed",
    "Choline.mfj": "a4cf1c4a14a2a84c49eb9b369df81070f6978c6d9ecd320ea521dc094499d8db",
    "mobcal.in": "b171aed86d9bcf6ad4a1daeb8ad43608268d8ce02e67b54366459970605e2da6",
    "sample-output/Choline_He.out":
        "9712d7065c477373c5ddffdb59fd6b5df5f4dc413b0d34af1322c9c9cb2cd427",
    "sample-output/Choline_N2.out":
        "1da0eddc492d95282c5707a3c7f83489b9dcac8f5048453e533216da54a58e99",
}

FFLAGS = ["-O3", "-fno-automatic", "-std=legacy"]
WINDOWS_FLAGS = ["-static"]

# Where MSYS2 puts gfortran on Windows. Without this directory on PATH, gfortran
# invocations fail with exit 1 and no output at all, which reads like a source
# error rather than a missing compiler.
MSYS2_BIN = Path(r"C:\msys64\mingw64\bin")

# A diagnostic gfortran classes as a warning ("Warning: ..." on a line of its own, after the
# source excerpt), or one the linker passes back through it ("ld: warning: ...").
_WARNING = re.compile(r"^(?:Warning: |\S*\bld(?:\.exe)?: warning: )", re.M)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sources(fortran_dir: Path = FORTRAN_DIR) -> list[str]:
    """Return one line per pinned file that is missing or differs. Empty means byte-identical."""
    problems = []
    for rel, want in SHA256.items():
        p = fortran_dir / rel
        if not p.is_file():
            problems.append(f"{rel}: missing")
            continue
        got = _sha256(p)
        if got != want:
            problems.append(f"{rel}: sha256 {got[:12]}... differs from 2012's {want[:12]}...")
    return problems


def find_gfortran() -> str | None:
    """The gfortran to use, or None. Honours ``$FC`` first, then PATH, then MSYS2's directory."""
    fc = os.environ.get("FC")
    if fc and shutil.which(fc):
        return shutil.which(fc)
    found = shutil.which("gfortran")
    if found:
        return found
    if sys.platform == "win32" and (MSYS2_BIN / "gfortran.exe").is_file():
        return str(MSYS2_BIN / "gfortran.exe")
    return None


def flags() -> list[str]:
    return FFLAGS + (WINDOWS_FLAGS if sys.platform == "win32" else [])


def binary_name(gas: str) -> str:
    return f"mobcal_{gas}" + (".exe" if sys.platform == "win32" else "")


def binary_dir() -> Path:
    """Where the built binaries are looked for, and never on PATH.

    ``$MOBCAL_BIN_DIR`` first; then, in a frozen (installed) program, the ``fortran`` directory
    beside the executable, where the installer puts the binaries built in CI; otherwise
    ``build/fortran/`` under this checkout, where ``mobcal build`` writes them.
    """
    env = os.environ.get("MOBCAL_BIN_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "fortran"
    return ROOT / "build" / "fortran"


def find_binary(gas: str) -> Path:
    """The built binary for one gas. Raises FileNotFoundError, naming where it looked."""
    if gas not in GASES:
        raise ValueError(f"gas must be one of {GASES}, not {gas!r}")
    p = binary_dir() / binary_name(gas)
    if not p.is_file():
        raise FileNotFoundError(f"no {p.name} in {p.parent}: run `mobcal build`, or point "
                                f"MOBCAL_BIN_DIR at a directory that holds it")
    return p


def count_warnings(log: str) -> int:
    """The number of warnings in what gfortran wrote to stdout and stderr."""
    return len(_WARNING.findall(log))


@dataclass(frozen=True)
class Build:
    binary: Path
    log: str  # the compiler's stdout and stderr, interleaved as it wrote them

    @property
    def warnings(self) -> int:
        return count_warnings(self.log)


def build(gas: str, out_dir: Path, gfortran: str | None = None) -> Build:
    """Compile one gas's source into ``out_dir``; return the binary's path and the compiler's log.

    Raises FileNotFoundError when no gfortran is found and CalledProcessError when the compile
    fails. The compiler's output is captured, so that its warnings can be counted, and echoed to
    stderr unchanged; ``LC_ALL=C`` keeps it in the language the count expects.
    """
    if gas not in GASES:
        raise ValueError(f"gas must be one of {GASES}, not {gas!r}")
    gfortran = gfortran or find_gfortran()
    if gfortran is None:
        raise FileNotFoundError("no gfortran found ($FC, PATH, or C:\\msys64\\mingw64\\bin)")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / binary_name(gas)
    src = FORTRAN_DIR / SOURCE[gas]
    cmd = [gfortran, *flags(), "-o", str(out), str(src)]
    env = dict(os.environ, LC_ALL="C")
    if sys.platform == "win32":
        env["PATH"] = str(Path(gfortran).parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors="replace")
    sys.stderr.write(proc.stdout)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout)
    return Build(out, proc.stdout)


def describe() -> str:
    """One line for a banner or a log: compiler, flags, platform."""
    gf = find_gfortran() or "no gfortran"
    return f"{gf} {' '.join(flags())} on {platform.platform()}"
