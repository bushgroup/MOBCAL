# MOBCAL

MOBCAL calculates the collision cross sections of ions in helium and in nitrogen by the
trajectory method. The Fortran at its core is the 2012 release of MOBCAL described in
Campuzano et al., *Anal. Chem.* 2012, 84, 1026, kept here byte for byte. Around it this
repository is building a Python package that compiles the Fortran, runs many calculations at
once on separate cores, collects the results, and will ship as an installer for people who do
not manage compilers or Python environments.

## Status

Founded 2026-10-21. The Fortran is in place and builds on Windows, macOS and Linux in
continuous integration, which also runs the self-check and the tests on every change. The tests
include a regression test that runs the 2012 choline input through each build and compares the
result with the 2012 outputs. The Python package has a version, a build command, a self-check
and a reader for the output file. The driver that runs calculations in parallel and the
installers follow, in that order. A graphical interface is planned once the driver exists.

The 2012 code itself, including its Lennard-Jones parameters, is not being changed. Questions
about the parameters are being taken up separately, and no change to them will land without a
stated decision and a stated reason.

## What is here

- `fortran/`: the 2012 sources, the choline input, the run file and the two reference outputs,
  unchanged. [`fortran/README.md`](fortran/README.md) records their hashes and what the 2012
  release said about compiling them.
- `src/mobcal/`: the Python package.
- `tools/check_public.py`: the self-check a fresh clone runs.

## Building the Fortran

The sources are Fortran 77 and build with gfortran:

```
uv run mobcal build
```

That compiles `mobcal_He.f` and `mobcal_N2.f` into `build/fortran/` with the flags the package
records in `mobcal.fortran`. One of those flags is not optional. The code keeps state in local
variables across calls, which was the default of the g77 compiler it was written for, and
gfortran must be told to do the same with `-fno-automatic`. Without that flag an optimized build
runs to completion and loses every trajectory. With it, optimized gfortran builds reproduce the
2012 reference outputs byte for byte on Windows, macOS and Linux.

To see whether the current code builds, look at the [`ci` workflow](.github/workflows/ci.yml).
Each change to the repository compiles both sources with these flags on all three platforms,
fails if gfortran issues a single warning, and keeps the two binaries from each platform as
artifacts of the run.

## Running from source

Requires [uv](https://docs.astral.sh/uv/) and gfortran. On Windows, gfortran from MSYS2 with
`C:\msys64\mingw64\bin` on `PATH`.

```
uv run tools/check_public.py
uv run pytest
```

## Testing against the 2012 outputs

To check that a build still computes the 2012 numbers, the test suite runs `Choline.mfj`
through each binary at seed 5013489, the seed the references were produced with, and compares
the output with `fortran/sample-output/` in three tiers. The first compares every line that does
not depend on the random number stream character for character. `tests/stochastic-lines.txt`
lists the lines that do, so a line that is not listed has to match, and a line the 2012 code
never wrote fails the test. The second compares the reported cross sections within 0.1 %: the
projection-approximation, exact hard-sphere and trajectory-method values in helium, and the
trajectory-method value in nitrogen. The third requires the whole file to be byte-identical to
the reference on the platforms listed in `tests/strict-platforms.txt`, which are all three.

The helium comparison takes about 3 minutes and runs with every `uv run pytest`. The nitrogen
comparison takes about an hour and runs only when asked for:

```
uv run pytest -m nitrogen
```

Continuous integration runs the nitrogen comparison every Monday, and on a manual run of the
`ci` workflow with its nitrogen option selected.

## Citation

Any research that uses this code or the included Lennard-Jones parameters should reference [1].

1. Campuzano, I. D. G.; Bush, M. F.; Robinson, C. V.; Beaumont, C.; Richardson, K.; Kim, H.;
   Kim, H. I. Structural Characterization of Drug-like Compounds by Ion Mobility Mass
   Spectrometry: Comparison of Theoretical and Experimentally Derived Nitrogen Collision
   Cross-sections. *Anal. Chem.* 2012, 84, 1026-1033. https://doi.org/10.1021/ac202625t
2. Mesleh, M. F.; Hunter, J. M.; Shvartsburg, A. A.; Schatz, G. C.; Jarrold, M. F. Structural
   Information from Ion Mobility Measurements: Effects of the Long Range Potential. *J. Phys.
   Chem.* 1996, 100, 16082-16086.
3. Kim, H.; Kim, H. I.; Johnson, P. V.; Beegle, L. W.; Beauchamp, J. L.; Goddard, W. A.; Kanik,
   I. Experimental and theoretical investigation into the correlation between mass and ion
   mobility for choline and other ammonium cations in N2. *Anal. Chem.* 2008, 80, 1928-1936.

The 2012 release is also kept, exactly as published, at
[bushgroup/MOBCAL-2012](https://github.com/bushgroup/MOBCAL-2012).

## License

GNU General Public License v3.0. See [`LICENSE`](LICENSE).
