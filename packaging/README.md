# packaging/

How the installable program is built. The user-facing side, what a person downloads and how to
check it, is [`docs/install.md`](../docs/install.md).

## What is built

One layout on every platform, PyInstaller's onedir folder plus two folders the build adds:

```
mobcal/
  mobcal(.exe)        the command, frozen with its own Python
  _internal/          PyInstaller's runtime and the mobcal package, with the element tables
                      in mobcal/parameters/
  fortran/            mobcal_he(.exe), mobcal_n2(.exe), build.json
  examples/           Choline.mfj, sample-output/Choline_He.out, sample-output/Choline_N2.out
  LICENSE
```

`mobcal.fortran.binary_dir()` and `examples_dir()` look in `fortran/` and `examples/` beside the
executable when the program is frozen, so the frozen program and a source checkout run the same
code. On Windows, Inno Setup (`mobcal.iss`) installs the folder per user. On macOS and Linux the
folder is shipped as `mobcal-<version>-<os>-<arch>.tar.gz`, whose top folder is
`mobcal-<version>/`. Onedir rather than onefile, because a onefile program unpacks itself into
a temporary directory on every start.

## The Fortran inside is built in CI

The two binaries are the ones the `build` job of the `ci` workflow compiled and ran the
regression gate with, carried to the `package` job as that job's artifact; nothing in the
package job compiles. `mobcal build` writes `build.json` beside the binaries (compiler, flags,
platform, commit, and the SHA-256 of each source and binary; the commit ends in `-dirty` when
the checkout had changes or untracked files that no commit holds), and `tools/build_bundle.py`
refuses binaries that do not match it, that were built from anything but the pinned sources, or
that need a gfortran runtime: a program interpreter on Linux, a library outside `/usr/lib` and
`/System` on macOS, a MinGW runtime DLL on Windows. The link flags that make that true are in
`mobcal.fortran.LINK_FLAGS` and are part of the recipe the gate tests: `-static` on Windows and
Linux, and `-static-libgfortran -static-libgcc -static-libquadmath` on macOS, where Apple's
linker has no fully static mode.

## Building locally

To try the chain on a workstation, build the binaries first, or download a `ci` run's
`mobcal-<os>-<arch>` artifact into `build/fortran/`:

```
uv run mobcal build
```

then, on Windows,

```
powershell -ExecutionPolicy Bypass -File tools/build_exe.ps1
```

and on macOS or Linux,

```
uv run tools/build_bundle.py --archive
```

`build_bundle.py` checks the binaries, runs PyInstaller on `mobcal.spec`, adds `fortran/`,
`examples/` and `LICENSE`, and runs the built program's `self-check` with `PATH` cut to the
operating system's own directories, so a program that works only because something on the
build machine's `PATH` helps it fails here. The report is also written to
`build/self-check.log`. It then times two starts of `mobcal version`.

`build_exe.ps1` runs the same with `PATH` cut to the Windows directories and uv's for the whole
build, then compiles the installer with Inno Setup 6's `ISCC.exe` into `dist\installer\`
(`winget install JRSoftware.InnoSetup --scope user` puts it under
`%LOCALAPPDATA%\Programs\Inno Setup 6\`, where the script looks first). PyInstaller resolves DLL
dependencies through `PATH` as a last resort, and a `PATH` carrying another toolchain or Python
distribution substitutes its DLLs quietly; `mobcal.spec` refuses to build on Windows if any
collected file comes from outside the virtual environment, its base interpreter and this
repository, which on a typical workstation `PATH` it does. `build_bundle.py` also drops
`PYTHONPATH` for the PyInstaller run.

## In CI

The `package` job of the `ci` workflow runs on each platform after `build`: it downloads that
platform's binaries, builds the folder and the installer or archive as above, and then tests the
result where no compiler and no Python are visible. The Linux archive is unpacked into
AlmaLinux 8 (glibc 2.28), Ubuntu 20.04 and Debian stable containers; the macOS archive is run
with an empty environment and `PATH=/usr/bin:/bin`; the Windows installer is run silently, its
`PATH` entry checked, the installed program run with `PATH` cut to `System32`, and the
uninstaller run and checked to remove both the program and the `PATH` entry. Each runs
`mobcal self-check --choline`, which compares the 2012 choline input in helium with the 2012
output. The packages are kept as the run's `package-<os>-<arch>` artifacts.

## Releasing

The version is declared in three places, `pyproject.toml`, `mobcal.__version__` and
`MyAppVersion` in `mobcal.iss`, in PEP 440's normalized spelling (`2.0.0rc1`, not
`2.0.0-rc.1`), and `tools/check_public.py` fails unless the three agree.

1. One commit that changes the version and nothing else, in the three places, then `uv lock`.
   `uv run tools/check_public.py` and `uv run pytest` pass before it is pushed.
2. Once `ci` is green on that commit, an annotated tag on it, pushed:
   `git tag -a v<version> <commit> -m "MOBCAL <version>"`, `git push origin v<version>`.
3. The tag runs `ci` again, and its `release` job checks that the tag names the version in
   `pyproject.toml` and drafts a GitHub release holding the three packages; a version with
   `a`, `b`, `rc` or `dev` in it is marked as a pre-release. Install the Windows package on a
   machine with no development tools on it, run `mobcal self-check --choline`, and
   publish the draft by hand.
4. A second version-only commit moves `main` to the next development version (`2.0.1.dev0`
   after `2.0.0`), so that no later build carries the released number.

A pushed tag is never moved or deleted; a mistake in a release is fixed by the next version.

## Not done

- **Signing.** Neither the Windows installer nor the macOS program is signed, so SmartScreen
  warns about the first and Gatekeeper refuses a browser-downloaded copy of the second until its
  quarantine flag is removed (`docs/install.md`). Signing needs a code-signing certificate and
  an Apple Developer ID.
- **Intel Macs.** The macOS package is built on an Apple silicon runner and is arm64 only.
- **A window.** The program is a console executable; `mobcal.app` and its PySide6 dependencies
  join the spec when the window does.
