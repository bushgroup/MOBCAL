# Installing MOBCAL

MOBCAL is distributed as a program that runs without a Fortran compiler and without Python: an
installer for Windows, and an archive for macOS on Apple silicon and for Linux on x86-64. Each
holds the window ([window.md](window.md)), the `mobcal` command, the two 2012 Fortran programs
(helium and nitrogen) compiled for that platform, and the 2012 choline input with its two
reference outputs. To build from source
instead, see the [README](../README.md).

Released versions are on the repository's
[Releases page](https://github.com/bushgroup/MOBCAL/releases). Between releases, every change to
the repository builds all three packages in the
[`ci` workflow](https://github.com/bushgroup/MOBCAL/actions/workflows/ci.yml), which keeps them
as artifacts of each run (`package-Windows-X64`, `package-macOS-ARM64`, `package-Linux-X64`) for
30 days. A development build carries a version ending in `.dev0`.

## Windows

Run `mobcal-<version>-setup.exe`. The installer does not need administrator rights: it installs
for the current user, into `%LOCALAPPDATA%\Programs\MOBCAL` by default. The installer is not
signed, and Windows SmartScreen answers an unsigned installer it has not seen before with
"Windows protected your PC"; choose **More info**, then **Run anyway**.

One option, checked by default, adds the installation directory to your `PATH`, so that `mobcal`
runs in any terminal opened after the installation, and another, unchecked, puts the window on
the desktop. The Start menu gets four entries: **MOBCAL**, the window; **MOBCAL command
prompt**, a command prompt in which `mobcal` runs whether or not the first option was chosen;
**MOBCAL self-check**, which runs the check described below; and **Uninstall MOBCAL**.
Uninstalling removes the program and its `PATH` entry, and leaves alone any calculation output
written elsewhere.

## macOS (Apple silicon)

Unpack the archive into Applications:

```
tar -xzf mobcal-<version>-macos-arm64.tar.gz -C /Applications
```

This gives `MOBCAL.app`, which opens the window, and holds the `mobcal` command in
`MOBCAL.app/Contents/MacOS`. The program is not signed by Apple, so macOS refuses to open a copy
that was downloaded with a web browser until the download's quarantine flag is removed:

```
xattr -dr com.apple.quarantine /Applications/MOBCAL.app
```

To run `mobcal` by name, add that folder to your `PATH`, for example by adding this line to
`~/.zprofile`:

```
export PATH="/Applications/MOBCAL.app/Contents/MacOS:$PATH"
```

The macOS package runs on Apple silicon (arm64) only. On an Intel Mac, build from source.

## Linux (x86-64)

Unpack the archive and add the folder to your `PATH` in the same way:

```
tar -xzf mobcal-<version>-linux-x86_64.tar.gz -C ~
export PATH="$HOME/mobcal-<version>:$PATH"
```

The Fortran programs are linked statically and depend on no library. The `mobcal` command needs
a glibc-based distribution; each build is tested in AlmaLinux 8, Ubuntu 20.04 and Debian stable
containers that have neither a compiler nor Python installed. `mobcal gui` opens the window. It
needs a desktop's X11 libraries, which any desktop installation has; the one a desktop may lack,
`libxcb-cursor0`, is in the archive, and the window is tested in a Debian container without it.
On a machine without a display, `mobcal run` does everything the window does.

## Checking an installation

```
mobcal self-check
```

checks, in under a second, that the installed copy can compute a cross section. It prints one
line per stage, with the time each took: the version; that the two element tables and the
settings file are the files this package shipped, by their checksums, and pass the checks a
run puts them through ([parameters.md](parameters.md), [settings.md](settings.md)); that both
Fortran programs are present,
are the files that were built for this package, and were built from this package's Fortran sources with the
recorded compiler flags (the folder `fortran` beside `mobcal` holds the programs and a
`build.json` that records the compiler, the flags, the commit and a checksum of each file); and
that each program starts and refuses an input naming an element it does not define, which
exercises everything a calculation does except the trajectories. It ends with
`self-check passed`, or names the stage that failed.

```
mobcal self-check --choline
```

also runs the 2012 choline input in helium at the 2012 random seed, under RANLUX, the random
number generator the 2012 output was computed with, and compares the three cross sections with
the 2012 output, which takes about three minutes. A correct installation
reproduces the 2012 values, 61.075 Å² (projection approximation), 63.473 Å² (exact hard
spheres) and 55.402 Å² (trajectory method), and every package is tested this way before it is
kept.

## Running calculations

The installed command is the same `mobcal run` that the [README](../README.md#running-calculations)
describes, without the `uv run` in front of it. The choline input is in the `examples` folder
of the installation, which on macOS is `MOBCAL.app/Contents/Resources/examples`:

```
mobcal run <installation>/examples/Choline.mfj --gas he --out runs
```

writes its run directory and `summary.csv` under `runs` in the current directory. Adding
`--split 8` runs that one calculation as eight processes and reports the serial result exactly,
which is how a long nitrogen calculation is made short on a machine with cores to spare: on
one 80-thread workstation choline in nitrogen took 70 minutes serial, 8 minutes across ten
processes and 4.5 minutes across twenty. The run draws its random numbers from Philox4x32-10
unless `--rng ranlux` is added, which selects the generator of the 2012 release and, at the
default seed, reproduces the 2012 choline values above ([random-numbers.md](random-numbers.md)).
Run calculations from a folder of your own, not from inside the installation, which an upgrade
replaces.

## Source code

MOBCAL is free software under the GNU General Public License, version 3, which the installation
carries as `LICENSE`. The commit each package was built from is recorded in its
`fortran/build.json`, and the source code at that commit is in this repository.
