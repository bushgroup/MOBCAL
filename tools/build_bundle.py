"""Build the installable mobcal folder: PyInstaller, then the Fortran binaries beside it.

    uv run tools/build_bundle.py [--bin-dir DIR] [--archive] [--skip-pyinstaller]

1. Checks the binaries in ``--bin-dir`` (default ``build/fortran/``, where ``mobcal build`` writes
   and where CI downloads its build artifact) against their ``build.json`` and the 2012 pins,
   and checks that each one needs no gfortran runtime: no program interpreter on Linux (a
   static binary), nothing outside ``/usr/lib`` and ``/System`` on macOS, no MinGW runtime DLL
   on Windows.
2. Runs PyInstaller on ``packaging/mobcal.spec``, giving ``dist/mobcal/`` with the console
   ``mobcal`` and the windowed ``mobcal-gui`` in it, and on macOS ``dist/MOBCAL.app``, whose
   ``Contents/MacOS/`` holds both.
3. Copies the binaries and ``build.json`` to ``fortran/`` beside the executables (executable,
   since an artifact download loses the mode), ``Choline.mfj``, the two 2012 outputs and one
   ORCA output of the choline cation (``tests/data/qm/``) to ``examples/``, and ``LICENSE``; on
   macOS into the ``.app``, which is then signed again, ad hoc, since adding files breaks the
   seal PyInstaller's ad-hoc signature put on it.
4. Runs the built program's ``self-check`` with ``PATH`` cut to the operating system's own
   directories and no ``MOBCAL_BIN_DIR``, writing ``build/self-check.log``, times two
   ``mobcal version`` starts, has the built program import the ORCA example's CHELPG
   charges, which must give the file the source tree's import gives (cclib and everything
   under it are in the bundle and work), and opens and closes the window with ``mobcal gui
   --check`` on Qt's offscreen platform (Qt and its plugins are in the bundle and start).
5. With ``--archive`` (macOS and Linux), writes ``dist/mobcal-<version>-<os>-<arch>.tar.gz``,
   whose top folder is ``mobcal-<version>/`` on Linux and ``MOBCAL.app`` on macOS. Windows
   packages the folder with Inno Setup instead (``tools/build_exe.ps1``).

The binaries are built in CI, not on the machine that runs this; a local ``mobcal build`` is
for trying the chain, and its ``build.json`` says where it came from either way.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import mobcal  # noqa: E402
from mobcal import fortran  # noqa: E402

DIST = ROOT / "dist"
APP = DIST / "MOBCAL.app"  # macOS only
# Where the executables are, and fortran/ and examples/ go beside them.
BUNDLE = APP / "Contents" / "MacOS" if sys.platform == "darwin" else DIST / "mobcal"
EXE = "mobcal.exe" if sys.platform == "win32" else "mobcal"
GUI_EXE = "mobcal-gui.exe" if sys.platform == "win32" else "mobcal-gui"
WORK = ROOT / "build" / "pyinstaller"
SELF_CHECK_LOG = ROOT / "build" / "self-check.log"

# The ORCA output the bundle carries as an example, and the charges the import check takes.
ORCA_EXAMPLE = ROOT / "tests" / "data" / "qm" / "orca" / "choline_sp" / "choline_sp.out"
ORCA_CHARGES = "chelpg"

# MinGW's runtime, which a dynamically linked MSYS2 binary imports and a clean Windows lacks.
_MINGW_DLL = re.compile(rb"(?i)(libgfortran|libgcc_s|libquadmath|libwinpthread)[\w.-]*\.dll")


def _elf_interpreter(path: Path) -> bool:
    """True if a 64-bit little-endian ELF file asks for a program interpreter (is dynamic)."""
    data = path.read_bytes()
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise ValueError(f"{path.name} is not a 64-bit little-endian ELF file")
    phoff, = struct.unpack_from("<Q", data, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", data, 0x36)
    return any(struct.unpack_from("<I", data, phoff + i * phentsize)[0] == 3  # PT_INTERP
               for i in range(phnum))


def runtime_problems(binary: Path) -> list[str]:
    """What a machine without gfortran would be missing to run this binary; empty if nothing."""
    if sys.platform == "linux":
        return [f"{binary.name} is dynamically linked"] if _elf_interpreter(binary) else []
    if sys.platform == "darwin":
        out = subprocess.run(["otool", "-L", str(binary)], capture_output=True, text=True,
                             check=True).stdout.splitlines()[1:]
        libs = [line.split()[0] for line in out if line.strip()]
        return [f"{binary.name} links {lib}" for lib in libs
                if not lib.startswith(("/usr/lib/", "/System/"))]
    if sys.platform == "win32":
        found = sorted({m.group(0).decode() for m in _MINGW_DLL.finditer(binary.read_bytes())})
        return [f"{binary.name} imports {dll}" for dll in found]
    return []


def check_binaries(bin_dir: Path) -> None:
    for gas in fortran.GASES:
        p = bin_dir / fortran.binary_name(gas)
        if p.is_file():
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    problems = fortran.verify_binaries(bin_dir)
    for gas in fortran.GASES:
        p = bin_dir / fortran.binary_name(gas)
        if p.is_file():
            problems += runtime_problems(p)
    if problems:
        raise SystemExit("refusing to bundle the binaries in {}:\n  {}".format(
            bin_dir, "\n  ".join(problems)))
    rec = fortran.read_manifest(bin_dir)["binaries"][fortran.binary_name("he")]
    print(f"binaries: {bin_dir}, {rec.get('compiler')}, {' '.join(rec.get('flags', []))}, "
          f"commit {fortran.short_commit(rec.get('commit', '')) or 'unrecorded'}")


def pyinstaller() -> None:
    cmd = [sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "mobcal.spec"),
           "--distpath", str(DIST), "--workpath", str(WORK), "--noconfirm", "--clean"]
    print("+ " + " ".join(cmd), flush=True)
    # A PYTHONPATH left by some other software puts its directory on the Analysis's search path.
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "PYTHONHOME")}
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)


def assemble(bin_dir: Path) -> None:
    for name in (EXE, GUI_EXE):
        if not (BUNDLE / name).is_file():
            raise SystemExit(f"no {BUNDLE / name}: run without --skip-pyinstaller first")
    for sub in ("fortran", "examples"):
        shutil.rmtree(BUNDLE / sub, ignore_errors=True)
    (BUNDLE / "fortran").mkdir()
    for name in [fortran.binary_name(g) for g in fortran.GASES] + [fortran.MANIFEST]:
        shutil.copy2(bin_dir / name, BUNDLE / "fortran" / name)
        if name != fortran.MANIFEST:
            (BUNDLE / "fortran" / name).chmod(0o755)
    (BUNDLE / "examples" / "sample-output").mkdir(parents=True)
    for rel in ("Choline.mfj", "sample-output/Choline_He.out", "sample-output/Choline_N2.out"):
        shutil.copy2(fortran.FORTRAN_DIR / rel, BUNDLE / "examples" / rel)
    shutil.copy2(ORCA_EXAMPLE, BUNDLE / "examples" / ORCA_EXAMPLE.name)
    shutil.copy2(ROOT / "LICENSE", BUNDLE / "LICENSE")
    if sys.platform == "darwin":
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(APP)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(APP)], check=True)


def clean_env() -> dict[str, str]:
    """The environment of a machine with nothing installed: the OS's own PATH and no hints."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("PATH", "MOBCAL_BIN_DIR", "FC", "PYTHONPATH", "PYTHONHOME",
                                "VIRTUAL_ENV")}
    if sys.platform == "win32":
        sr = os.environ.get("SystemRoot", r"C:\Windows")
        env["PATH"] = os.pathsep.join([rf"{sr}\System32", sr, rf"{sr}\System32\Wbem"])
    else:
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    return env


def self_check() -> None:
    exe = BUNDLE / EXE
    SELF_CHECK_LOG.unlink(missing_ok=True)
    env = clean_env()
    rc = subprocess.run([str(exe), "self-check", "--report", str(SELF_CHECK_LOG)], env=env,
                        cwd=DIST).returncode
    if rc != 0:
        raise SystemExit(f"the built program's self-check failed (exit {rc}); "
                         f"report in {SELF_CHECK_LOG}")
    for label in ("cold", "warm"):
        t0 = time.perf_counter()
        out = subprocess.run([str(exe), "version"], env=env, capture_output=True, text=True,
                             check=True).stdout.strip()
        print(f"{label} start: mobcal version -> {out} in {time.perf_counter() - t0:.2f} s")
        if out != mobcal.__version__:
            raise SystemExit(f"the built program says {out!r}, the source {mobcal.__version__!r}")


def import_check() -> None:
    from mobcal.io import structure
    exe = BUNDLE / EXE
    out = ROOT / "build" / "import-check" / "choline_sp.mfj"
    shutil.rmtree(out.parent, ignore_errors=True)
    out.parent.mkdir(parents=True)
    t0 = time.perf_counter()
    proc = subprocess.run([str(exe), "import", str(BUNDLE / "examples" / ORCA_EXAMPLE.name),
                           "--charges", ORCA_CHARGES, "-o", str(out)], env=clean_env(),
                          capture_output=True, text=True)
    seconds = time.perf_counter() - t0
    if proc.returncode != 0:
        raise SystemExit(f"the built program's import failed (exit {proc.returncode}):\n"
                         f"{proc.stdout}{proc.stderr}")
    want = structure.convert(structure.read(ORCA_EXAMPLE), ORCA_CHARGES).mfj.text()
    if out.read_text(encoding="latin-1") != want:
        raise SystemExit(f"the built program's import wrote {out}, which differs from the "
                         "source tree's")
    print(f"import: {ORCA_EXAMPLE.name} --charges {ORCA_CHARGES} in {seconds:.2f} s, the "
          "source tree's file")


def window_check() -> None:
    env = {**clean_env(), "QT_QPA_PLATFORM": "offscreen"}
    t0 = time.perf_counter()
    proc = subprocess.run([str(BUNDLE / EXE), "gui", "--check"], env=env, capture_output=True,
                          text=True, timeout=300)
    if proc.returncode != 0:
        raise SystemExit(f"the built program's window did not open (exit {proc.returncode}):\n"
                         f"{proc.stdout}{proc.stderr}")
    print(f"window: {proc.stdout.strip()} in {time.perf_counter() - t0:.2f} s")


def archive_name() -> str:
    os_name = {"darwin": "macos", "linux": "linux", "win32": "windows"}.get(sys.platform,
                                                                         sys.platform)
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(),
                                                        platform.machine().lower())
    return f"mobcal-{mobcal.__version__}-{os_name}-{arch}.tar.gz"


def archive() -> Path:
    out = DIST / archive_name()
    with tarfile.open(out, "w:gz") as tf:
        if sys.platform == "darwin":
            tf.add(APP, arcname=APP.name)
        else:
            tf.add(BUNDLE, arcname=f"mobcal-{mobcal.__version__}")
    return out


def size(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 2**20


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bin-dir", type=Path, default=ROOT / "build" / "fortran",
                    help="where the built binaries and their build.json are")
    ap.add_argument("--archive", action="store_true", help="also write the .tar.gz")
    ap.add_argument("--skip-pyinstaller", action="store_true",
                    help="reuse dist/mobcal/ and only redo the binaries, examples and checks")
    args = ap.parse_args()

    t0 = time.perf_counter()
    check_binaries(args.bin_dir.resolve())
    if not args.skip_pyinstaller:
        pyinstaller()
    assemble(args.bin_dir.resolve())
    top = APP if sys.platform == "darwin" else BUNDLE
    print(f"bundle: {top}, {size(top):.1f} MB")
    self_check()
    import_check()
    window_check()
    if args.archive:
        out = archive()
        print(f"archive: {out}, {out.stat().st_size / 2**20:.1f} MB")
    print(f"done in {time.perf_counter() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
