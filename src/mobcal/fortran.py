"""Locate, verify and build the 2012 Fortran.

The six files under ``fortran/`` are the 2012 release of MOBCAL plus the changes that
``fortran/README.md`` lists, each counted line by line, and this module is where that claim is
made checkable: ``SHA256`` pins each file as committed and ``verify_sources`` compares. A change
to any of them is a decision taken in the lab record, lands with new pins in the same commit,
and counts its diff in the commit message. The 2012 numbers are untouched: no change alters a
value the program computes, and the regression gate reproduces both 2012 outputs byte for byte.

The build recipe is also stated here and nowhere else. ``-fno-automatic`` is mandatory: the code
relies on local variables keeping their values between calls, which g77 gave it by default. An
optimized gfortran build without the flag runs to completion and loses every trajectory, loudly
(zero completed), so this is not the kind of defect that quietly moves a published number. With
the flag, optimized builds reproduce the 2012 reference outputs byte for byte on Windows, macOS
and Linux. ``-std=legacy`` silences the Fortran 2018 deleted-feature diagnostics (DO loops ending
on a non-CONTINUE statement, arithmetic IF, and the like) and changes no generated code; the
warning count it leaves is expected to be zero, so a nonzero count is worth reading.

The link flags in ``LINK_FLAGS`` make a binary that runs on a machine with no gfortran runtime,
which is what the installers ship. ``-static`` on Windows, where a dynamically linked MSYS2
binary also dies silently when launched from PowerShell, and on Linux, where it removes the
dependence on the build machine's glibc as well. Apple's linker has no fully static mode, so on
macOS the three gfortran runtime libraries are linked statically and the binary needs only
``libSystem``. None of these flags changes the numbers: the regression gate runs under them.

``build`` captures what the compiler writes and counts its warnings; the self-check and CI fail on
any. Without ``-std=legacy`` each source draws 64. It also records what it built in
``build.json`` beside the binaries: the compiler, the flags, and the SHA-256 of each source and
binary, which the installed program's self-check compares against the binaries it finds.

    uv run mobcal build            # both gases into build/fortran/
    uv run mobcal build --gas he   # one
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from mobcal import ROOT, __version__

FORTRAN_DIR = ROOT / "fortran"

GASES = ("he", "n2")
SOURCE = {"he": "mobcal_He.f", "n2": "mobcal_N2.f"}

# The 2012 files, as committed at bushgroup/MOBCAL-2012 tag v1.0 (commit 4f3be72) and copied
# here from those blobs on 2026-10-21, LF line endings (see .gitattributes); the two sources
# with the changes fortran/README.md lists under Changes.
SHA256 = {
    "mobcal_He.f": "2ee87153cc405bf3fde37ac2408684e733450693a6007da32764888415ed1691",
    "mobcal_N2.f": "dc1b449ffad70246d8c466888f78c38ca9246f99b2bc9971f1549cac0f70d96a",
    "Choline.mfj": "a4cf1c4a14a2a84c49eb9b369df81070f6978c6d9ecd320ea521dc094499d8db",
    "mobcal.in": "5b7804c2fe64b28b1466f9d5df473014d8b623d44efb5674ca3ad78203bc3ecb",
    "sample-output/Choline_He.out":
        "9712d7065c477373c5ddffdb59fd6b5df5f4dc413b0d34af1322c9c9cb2cd427",
    "sample-output/Choline_N2.out":
        "1da0eddc492d95282c5707a3c7f83489b9dcac8f5048453e533216da54a58e99",
}

FFLAGS = ["-O3", "-fno-automatic", "-std=legacy"]
LINK_FLAGS = {
    "win32": ["-static"],
    "linux": ["-static"],
    "darwin": ["-static-libgfortran", "-static-libgcc", "-static-libquadmath"],
}

MANIFEST = "build.json"

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
            problems.append(f"{rel}: sha256 {got[:12]}... differs from the pinned {want[:12]}...")
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
    return FFLAGS + LINK_FLAGS.get(sys.platform, [])


def frozen() -> bool:
    """True in an installed (PyInstaller-built) program, False in a source checkout."""
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """The installed program's own directory: where the executable is. Frozen only."""
    return Path(sys.executable).resolve().parent


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
    if frozen():
        return install_dir() / "fortran"
    return ROOT / "build" / "fortran"


def examples_dir() -> Path:
    """Where ``Choline.mfj`` and ``sample-output/`` are: ``examples/`` beside an installed
    program, which carries copies of them, and ``fortran/`` in a source checkout."""
    return install_dir() / "examples" if frozen() else FORTRAN_DIR


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
    _record(out_dir, gas, out, gfortran)
    return Build(out, proc.stdout)


def compiler_version(gfortran: str) -> str:
    """The first line of ``gfortran --version``, or an empty string if it will not say."""
    env = dict(os.environ, LC_ALL="C")
    if sys.platform == "win32":
        env["PATH"] = str(Path(gfortran).parent) + os.pathsep + env.get("PATH", "")
    try:
        proc = subprocess.run([gfortran, "--version"], env=env, capture_output=True, text=True,
                              errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.splitlines()[0].strip() if proc.stdout else ""


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _commit(root: Path = ROOT) -> str:
    """The commit being built: the checkout's HEAD, with ``-dirty`` appended when the tree has
    changes or untracked files that HEAD does not (as ``git describe --dirty`` marks it), since
    the binaries then came from code no commit holds. Without git, CI's ``$GITHUB_SHA``; else
    empty."""
    head = _git(root, "rev-parse", "HEAD")
    if head is None:
        return os.environ.get("GITHUB_SHA", "")
    status = _git(root, "status", "--porcelain")
    return head.strip() + ("-dirty" if status is None or status.strip() else "")


def short_commit(commit: str) -> str:
    """A recorded commit for a report: twelve hex digits, keeping a ``-dirty`` mark."""
    sha, dirty, _ = commit.partition("-dirty")
    return sha[:12] + dirty


def read_manifest(bin_dir: Path) -> dict:
    """``build.json`` in ``bin_dir``, or an empty record if there is none or it does not parse."""
    try:
        m = json.loads((bin_dir / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return m if isinstance(m, dict) and isinstance(m.get("binaries"), dict) else {}


def _record(out_dir: Path, gas: str, binary: Path, gfortran: str) -> None:
    """Add (or replace) one binary's entry in ``out_dir/build.json``."""
    m = read_manifest(out_dir) or {"binaries": {}}
    m["binaries"][binary.name] = {
        "gas": gas,
        "source": SOURCE[gas],
        "source_sha256": _sha256(FORTRAN_DIR / SOURCE[gas]),
        "sha256": _sha256(binary),
        "compiler": compiler_version(gfortran),
        "flags": flags(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "mobcal": __version__,
        "commit": _commit(),
        "built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out_dir / MANIFEST).write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")


def verify_binaries(bin_dir: Path | None = None) -> list[str]:
    """One line per problem with the binaries in ``bin_dir`` (default ``binary_dir()``), checked
    against the ``build.json`` written when they were built. Empty means both binaries are
    there, are the files that were built, were built from the pinned sources, and were
    built with ``-fno-automatic``."""
    d = bin_dir or binary_dir()
    m = read_manifest(d)
    if not m:
        return [f"no readable {MANIFEST} in {d}"]
    problems = []
    for gas in GASES:
        name = binary_name(gas)
        rec = m["binaries"].get(name)
        if not (d / name).is_file():
            problems.append(f"{name}: missing from {d}")
        elif not isinstance(rec, dict):
            problems.append(f"{name}: not recorded in {MANIFEST}")
        elif _sha256(d / name) != rec.get("sha256"):
            problems.append(f"{name}: sha256 differs from the one recorded when it was built")
        elif rec.get("source_sha256") != SHA256[SOURCE[gas]]:
            problems.append(f"{name}: built from a {SOURCE[gas]} that is not the pinned file")
        elif "-fno-automatic" not in rec.get("flags", []):
            problems.append(f"{name}: built without -fno-automatic")
    return problems


def describe() -> str:
    """One line for a banner or a log: compiler, flags, platform."""
    gf = find_gfortran() or "no gfortran"
    return f"{gf} {' '.join(flags())} on {platform.platform()}"
