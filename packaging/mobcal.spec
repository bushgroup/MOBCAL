# PyInstaller build spec for the mobcal command (Windows, macOS, Linux).
#
# Run through `tools/build_bundle.py` (on Windows, through `tools/build_exe.ps1`, which cuts PATH
# first), not `pyinstaller` directly: the tool also puts the Fortran binaries, their build.json
# and the examples beside the executable, and runs the self-check on the result.
#
# Onedir, not onefile: a onefile executable extracts itself to a temporary directory on every
# start, and Inno Setup wants a folder to copy. The result is dist/mobcal/, holding the mobcal
# executable and PyInstaller's _internal/; build_bundle.py adds fortran/ and examples/ beside it,
# where mobcal.fortran.binary_dir() and examples_dir() look in a frozen program.
#
# A console executable: until the window exists, the command line is the program. The package
# has no third-party runtime dependencies, so there is nothing to exclude and no hook to write.

import os
import sys

ROOT = os.path.dirname(SPECPATH)  # SPECPATH is injected by PyInstaller: packaging/

a = Analysis(
    [os.path.join(SPECPATH, "entrypoint.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "_tkinter"],
    noarchive=False,
)

if not any(name == "mobcal.selfcheck" for name, *_ in a.pure):
    raise RuntimeError("Refusing to build: mobcal.selfcheck is not in the bundle, so the "
                       "installed program could not check itself. The Analysis did not follow "
                       "cli.py's import of it.")

# --- Provenance guard (Windows) -------------------------------------------------------------
# PyInstaller resolves a collected binary's DLL dependencies through the binary's own directory,
# then sys.path, then PATH. A PATH carrying another Python distribution substitutes its DLLs
# quietly (a sibling project once shipped a build that died on start this way).
# tools/build_exe.ps1 cuts PATH down to the Windows directories and uv's; this refuses to ship
# anything that still gets through. Legitimate sources are the venv, the interpreter it was
# made from, and this repo. Not applied on macOS and Linux, where the interpreter's own system
# libraries are legitimately outside all three.
if sys.platform == "win32":
    def _real(path):
        # realpath through uv's junctioned interpreter directory returns a file with the \\?\
        # prefix and the directory without it.
        p = os.path.realpath(path)
        return os.path.normcase(p[4:] if p.startswith("\\\\?\\") else p)

    allowed = tuple(_real(p).rstrip(os.sep) + os.sep for p in (sys.prefix, sys.base_prefix, ROOT))
    foreign = [e for e in list(a.binaries) + list(a.datas) if not _real(e[1]).startswith(allowed)]
    if foreign:
        raise RuntimeError(
            "Refusing to build: these files come from outside the venv, its base interpreter "
            "and this repo (a foreign directory on PATH, most likely another Python "
            "distribution):\n" + "\n".join(f"  {dest}  <-  {src}" for dest, src, *_ in foreign))

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mobcal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name="mobcal")
