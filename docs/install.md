# Installing MOBCAL

MOBCAL is distributed as a program that runs without a Fortran compiler and without Python: an
installer for Windows, an archive for macOS on Apple silicon, and an archive for Linux on x86-64.
Each holds the window ([The window](window.md)), the `mobcal` command ([The command
line](command-line.md)), the helium and nitrogen programs compiled for that platform, the 2012
choline input with its two reference outputs, and these pages, which the window shows under
**Help ▸ MOBCAL Help**. To run MOBCAL from its source code instead, see [From
source](#from-source).

Released versions are on the
[Releases page](https://github.com/bushgroup/MOBCAL/releases) of the repository. Between releases,
every change to the repository builds all three packages in the
[`ci` workflow](https://github.com/bushgroup/MOBCAL/actions/workflows/ci.yml), which keeps them
as artifacts of each run (`package-Windows-X64`, `package-macOS-ARM64`, and `package-Linux-X64`)
for 30 days. A development build carries a version ending in `.dev0`.

## Windows

Run `mobcal-<version>-setup.exe`. The installer does not need administrator rights: it installs
for the current user, into `%LOCALAPPDATA%\Programs\MOBCAL` by default. The installer is not
signed, and Windows SmartScreen answers an unsigned installer it has not seen before with
"Windows protected your PC"; choose **More info**, then **Run anyway**.

The installer offers two options. **Add mobcal to my PATH, so that a new terminal can run it**,
checked by default, adds the installation folder to your `PATH`, so that `mobcal` runs in any
terminal opened after the installation. **Put MOBCAL on the desktop**, unchecked by default, adds
a shortcut to the window. On its last page the installer offers **Run the self-check**, checked
by default, which runs the check described below, and **Open MOBCAL**.

The Start menu gets four entries: **MOBCAL**, the window; **MOBCAL command prompt**, a command
prompt in which `mobcal` runs whether or not the first option was chosen; **MOBCAL self-check**,
which runs the same check; and **Uninstall MOBCAL**. Uninstalling removes the program and its
`PATH` entry, and leaves alone any calculation output written elsewhere.

## macOS (Apple silicon)

Unpack the archive into Applications:

```
tar -xzf mobcal-<version>-macos-arm64.tar.gz -C /Applications
```

This gives `MOBCAL.app`, which opens the window and holds the `mobcal` command in
`MOBCAL.app/Contents/MacOS`. The program is not signed with an Apple Developer ID, so macOS
refuses to open a copy that was downloaded with a web browser until the quarantine flag on the
download is removed:

```
xattr -dr com.apple.quarantine /Applications/MOBCAL.app
```

To run `mobcal` by name, add that folder to your `PATH`, e.g., by adding this line to
`~/.zprofile`:

```
export PATH="/Applications/MOBCAL.app/Contents/MacOS:$PATH"
```

The macOS package runs on Apple silicon (arm64) only. On an Intel Mac, build from source.

## Linux (x86-64)

Unpack the archive and add its folder to your `PATH` in the same way:

```
tar -xzf mobcal-<version>-linux-x86_64.tar.gz -C ~
export PATH="$HOME/mobcal-<version>:$PATH"
```

The helium and nitrogen programs are linked statically and depend on no library. The `mobcal`
command needs a glibc-based distribution; each build is tested in AlmaLinux 8, Ubuntu 20.04, and
Debian stable containers that have neither a compiler nor Python installed, and the oldest of
them has glibc 2.28. `mobcal gui` opens the window, which needs a newer system than the command
does: Ubuntu 22.04, Debian 12, RHEL 9, or later, because the Qt libraries it is built on need the
C++ runtime of GCC 11. The window also needs the X11 libraries of a desktop, which any desktop
installation has. The one a desktop may lack, `libxcb-cursor0`, is in the archive, and the window
is tested in Ubuntu 22.04 and Debian stable containers without it. On a machine without a
display, `mobcal run` does everything the window does.

## Checking an installation

To check that an installed copy can compute a cross section, run

```
mobcal self-check
```

The check takes about a second. It prints one line for each stage with the time the stage took,
marks a stage that fails with `FAIL`, and ends with `self-check passed` or with the number of
stages that failed. The stages are:

- the version, and where the copy is installed;
- the element tables and the five shipped methods, which must be the files this package shipped,
  by their checksums, and must pass the checks a run puts them through ([The element
  tables](parameters.md), [Methods](methods.md));
- the helium and nitrogen programs, which must be present, must be the files that were built for
  this package, and must have been built from the Fortran sources of this package with
  `-fno-automatic`, the flag without which an optimized build loses every trajectory;
- a start of each program on an input that names an element the program does not define, which
  the program must refuse. This exercises everything a calculation does except the trajectories.

The `fortran` folder of the installation holds the two programs and `build.json`, which records
the compiler, the flags, the commit, and a checksum of each file.

```
mobcal self-check --choline
```

also runs the 2012 choline input in helium at the 2012 seed under RANLUX, the generator of the
2012 release, which takes about three minutes, and compares the three cross sections with the
2012 output. The stage passes when each is within 0.1 % of its 2012 value: 61.075 Å² (projection
approximation), 63.473 Å² (exact hard spheres), and 55.402 Å² (trajectory method). Every package
is tested this way before it is kept, and each gives the three values to the last digit
([Reproducing MOBCAL 2012](mobcal-2012.md)).

## Running calculations

To open the window, choose **MOBCAL** in the Start menu on Windows, open `MOBCAL.app` on macOS,
or run `mobcal gui` in a terminal on any platform ([The window](window.md)). The same
calculations run from a terminal with `mobcal run` ([The command line](command-line.md)). The
`examples` folder of the installation, which on macOS is
`MOBCAL.app/Contents/Resources/examples`, holds the 2012 choline input, `Choline.mfj`, and an
ORCA output and a Gaussian output of the same ion, `choline_sp.out` and `choline_2012_mk.log`,
to try an import on ([Importing a structure and its charges](import.md)).

```
mobcal run <installation>/examples/Choline.mfj --out runs
```

runs choline in helium and writes its run directory, `summary.csv`, and `summary.json` under
`runs` in the current directory ([The results folder](results-folder.md)). Adding `--split 8`
divides that calculation among eight processes and reports the serial result exactly, and
`--split auto` chooses the number as the window does ([Divided
runs](large-ions.md#divided-runs)). The run draws its random numbers from Philox4x32-10, the
generator of the default method; `--method 2012-he` runs the calculation of the 2012 release
instead, which gives the 2012 choline values above ([Reproducing MOBCAL 2012](mobcal-2012.md)).
Run calculations from a folder of your own, not from inside the installation, which an upgrade
replaces.

## Files from earlier versions

A newer version installs in place of an older one. On Windows, run the new installer, which
replaces the program in the folder of the old one. On macOS, delete `MOBCAL.app` and unpack the
new archive. On Linux, unpack the new archive and put its folder, `mobcal-<version>`, on your
`PATH` in place of the old one.

This version treats what version 2.0 wrote as follows.

- A `.mfj` runs as it did. `mobcal import` of version 2.0 wrote a `.mfj` and, beside it, the
  record of the import, `X.import.json`. That `.mfj` still runs, but the record beside it is not
  read. Importing the source again writes an ion file, which carries the record inside it ([The
  record of how the file was made](ion-file.md#the-record-of-how-the-file-was-made)).
- A method file of version 2.0 was TOML, `NAME.toml`, and is refused with a message that a
  method file is now `NAME.method.json`. The window removes such a file from the Method list at
  the next launch, with that message. To make the method again, choose a shipped method of its
  gas, set the fields to the values in the TOML file, and choose **File ▸ Save method…**
  ([Method files](methods.md#method-files)). The element tables remain TOML files.
- The settings file of version 2.0, the six run settings alone in TOML, is gone, and so is the
  option that named it, `--settings`. A method file does what the settings file did ([The run
  settings](settings.md)).
- A run directory of version 2.0 holds a `record.json` and no result file, and MOBCAL does not
  add one. `mobcal methods-text` reads the record, so a results folder that holds runs of both
  versions gives one methods paragraph. The record of such a run also carries the path and
  SHA-256 of the settings file the run named, `null` when it named none.
- A divided run of version 2.0 kept the folder of each process and every block file.
  `mobcal clean` removes them, as a run of this version does itself when it succeeds
  ([`mobcal clean`](command-line.md#mobcal-clean)).
- A queue that the window of version 2.0 saved is offered back when the window opens. A batch
  in it that no longer reads, e.g., one under a TOML method file, is listed as not restored.

Development builds wrote files that no release wrote. Between versions 2.0 and 2.1.0 the three
JSON formats carried other names: `mobcal-ion`, `mobcal-method`, and `ims-result`. An ion file
under `mobcal-ion` is refused with a message to change `format` to `ccs-ion`, since nothing
else differs. A method file under `mobcal-method` named its element table by name or by path
instead of carrying the rows, and is refused with a message to load a shipped method, set the
fields again, and save it. A result file under `ims-result` is refused by that name, and the
`record.json` beside it remains the record of its run. Before version 2.0, a run recorded its
method as `current`, `2012`, or `2000`, without the gas. These are read as `2012-philox-he` or
`2012-philox-n2`, as `2012-he` or `2012-n2`, and as `2000-he`, by the gas of the run. A queue of
that time in which one batch ran both gases comes back as one batch for each gas.

## From source

MOBCAL also runs from a clone of its repository, on any platform with
[uv](https://docs.astral.sh/uv/) and gfortran. On Windows, the gfortran of MSYS2 is found in its
default folder, `C:\msys64\mingw64\bin`, whether or not that folder is on the `PATH`, and the
environment variable `FC` names a compiler anywhere else. uv provides Python and the packages
MOBCAL needs, and every command runs through it from the repository folder:

```
git clone https://github.com/bushgroup/MOBCAL.git
cd MOBCAL
uv run mobcal build
uv run mobcal gui
```

`mobcal build` compiles the helium and nitrogen programs into `build/fortran/`, and from then on
each `mobcal` command on these pages is `uv run mobcal` in that folder. The example input and the
2012 references are under `fortran/`, not `examples/`. The [README](../README.md) gives the
build, the tests, and the run in more detail.

## Source code

MOBCAL is free software under the GNU General Public License, version 3, which the installation
carries as `LICENSE`. `mobcal version` prints the version and the commit the package was built
from, which `fortran/build.json` also records, and the source code at that commit is in the
[repository](https://github.com/bushgroup/MOBCAL).
