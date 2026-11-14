![MOBCAL: three helium trajectories past a choline ion](packaging/banner/mobcal-banner-2560x1280.png)

# MOBCAL

MOBCAL calculates the collision cross section of an ion in helium or in nitrogen by the
trajectory method, and in helium by the projection approximation and the exact hard-sphere method
as well. Its two Fortran programs are the 2012 release of MOBCAL (Campuzano et al., *Anal. Chem.*
2012, 84, 1026), and every change to them since is counted line by line in
[`fortran/README.md`](fortran/README.md). The Python package around them gives the programs a
window and a command line, and is distributed for Windows, macOS, and Linux as a program that runs
without a Fortran compiler and without Python. It runs many calculations at once on the cores of
a workstation, or divides one calculation among them and reports the result of one process
exactly. The ion, the method, and the result of a calculation are each a JSON file with a schema,
so that a cross section can be traced to the calculation that gave it.

## Installing

Released versions are on the [Releases page](https://github.com/bushgroup/MOBCAL/releases): an
installer for Windows, an archive for macOS on Apple silicon, and an archive for Linux on x86-64.
[Installing MOBCAL](docs/install.md) describes each of them. To check that an installed copy can
compute a cross section, run

```
mobcal self-check
```

which takes about a second.

## A first calculation

To open the window, choose **MOBCAL** in the Start menu on Windows, open `MOBCAL.app` on macOS,
or from a terminal on any platform, run `mobcal gui` ([The window](docs/window.md)). Everything
the window does, the `mobcal` command does too ([The command line](docs/command-line.md)):

```
mobcal run <installation>/examples/Choline.mfj --out runs
```

runs choline, the 21-atom example of the 2012 release, in helium, and prints its three cross
sections. The results folder, `runs`, then holds a run directory with the input, the output of
the program, the record of the run, and the result file, and two summary files that cover every
run in the folder ([The results folder](docs/results-folder.md)). Adding `--split 8` divides the
calculation among eight processes and reports the same result ([Divided
runs](docs/large-ions.md#divided-runs)).

A tutorial for each platform, [Windows](docs/tutorial-windows.md), [macOS](docs/tutorial-macos.md),
and [Linux](docs/tutorial-linux.md), takes a new user from the package to two calculations in the
window in about half an hour: choline in helium, and an ORCA output of the same ion in nitrogen.

## The guide

The guide is the pages of [`docs/`](docs/), which the window shows under **Help ▸ MOBCAL Help**.

- [A first calculation on Windows](docs/tutorial-windows.md), [on
  macOS](docs/tutorial-macos.md), and [on Linux](docs/tutorial-linux.md): from the package to two
  calculations in the window, the help, and the self-check.
- [The window](docs/window.md): the form, the queue, and the table of results.
- [Installing MOBCAL](docs/install.md): the three packages and the self-check.
- [The command line](docs/command-line.md): every command and option.
- [The ion file](docs/ion-file.md): the input, `X.ion.json`.
- [Importing a structure and its charges](docs/import.md): an ion file from an ORCA output, a
  Gaussian output, an `.xyz` file, or a `.mfj`.
- [Running the quantum chemistry for an import](docs/qm.md): ORCA and Gaussian inputs, and how
  much the choice of charges moves the cross section.
- [Methods](docs/methods.md): the five shipped methods and the method file, `NAME.method.json`.
- [The element tables](docs/parameters.md): the parameters of each element in each gas.
- [The run settings](docs/settings.md): the temperature and the five sampling counts.
- [Random numbers](docs/random-numbers.md): the two generators and the seed.
- [The results folder](docs/results-folder.md): the run directory, the record of a run, and the
  summary files.
- [The result file](docs/result-file.md): `NAME.result.json`, written to be read without MOBCAL.
- [Large ions and long runs](docs/large-ions.md): the limits, what a run costs, and the divided
  run.
- [Reproducing MOBCAL 2012](docs/mobcal-2012.md) and [Reproducing MOBCAL
  2000](docs/mobcal-2000.md): the commands, and the comparison with the outputs of each release.
- [`fortran/README.md`](fortran/README.md): every change to the Fortran since 2012.

## MOBCAL 2012 and this version

A run under the default method, `2012-philox-he`, or under its counterpart in nitrogen,
`2012-philox-n2`, uses the 2012 element table of the gas, the 2012 temperature and sampling
counts, and, unless it is given another, the 2012 seed. It differs from the calculation of the
2012 release in one choice, the random number generator, which is Philox4x32-10 where the release
drew from RANLUX ([Random numbers](docs/random-numbers.md)). A number published from MOBCAL 2012
reproduces only under RANLUX at its seed, so the calculation of the release is a method of its
own in each gas:

```
mobcal run Choline.mfj --method 2012-he
mobcal run Choline.mfj --method 2012-n2
```

These report the 2012 choline values: 61.075 Å² by the projection approximation, 63.473 Å² by the
exact hard-sphere method, and 55.402 Å² by the trajectory method in helium, and 115.92 Å² by the
trajectory method in nitrogen. Compared as [Reproducing MOBCAL 2012](docs/mobcal-2012.md)
describes, each output is the 2012 output in every line but 41, and each of those 41 lines is a
change in how a value is printed, not in the value. The test suite makes this comparison on
Windows, macOS, and Linux ([What the tests hold](docs/mobcal-2012.md#what-the-tests-hold)).

The element table of each gas is the 2012 table, and the test suite holds every row of it to the
2012 number to the last bit ([The element tables](docs/parameters.md)). One value has moved since
2012, on purpose: the 2012 nitrogen program gave silicon the parameters of iron from the second
coordinate set of an input on, which was a copy error ([Silicon in
nitrogen](docs/mobcal-2012.md#silicon-in-nitrogen)). No change to a parameter will land without a
stated decision and a stated reason.

The 2012 release is kept as published at
[bushgroup/MOBCAL-2012](https://github.com/bushgroup/MOBCAL-2012). The 2000 helium release of the
Jarrold group, from which the 2012 helium program was made and whose calculation the method
`2000-he` runs, is kept as distributed at
[bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000), and the test suite holds the
shipped program to the output of its example, five of the 50 coordinate sets on every change and
all of them weekly ([What the tests hold](docs/mobcal-2012.md#what-the-tests-hold)). The
MMFF94/exp-6 programs of 2017 and 2018, a branch of the same lineage, are kept as distributed at
[bushgroup/MOBCAL-2018](https://github.com/bushgroup/MOBCAL-2018).

## From source

MOBCAL also runs from a clone of this repository, on any platform with
[uv](https://docs.astral.sh/uv/) and gfortran ([From source](docs/install.md#from-source)):

```
git clone https://github.com/bushgroup/MOBCAL.git
cd MOBCAL
uv run mobcal build
uv run tools/check_public.py
uv run pytest
```

`mobcal build` compiles the helium and nitrogen programs into `build/fortran/` with the flags
that `mobcal.fortran` records. One of those flags, `-fno-automatic`, is not optional: without it
an optimized build runs to completion and loses every trajectory ([What the 2012 release said
about building](fortran/README.md#what-the-2012-release-said-about-building)).
`tools/check_public.py` checks that the files under `fortran/`, the element tables, and the
shipped methods are the files this repository pins, and that both sources compile without a
warning. `uv run pytest` runs the tests, the comparison of choline in helium with the 2012 output
among them. The [`ci` workflow](.github/workflows/ci.yml) runs all three on Windows, macOS, and
Linux for every change, builds the three packages, and runs each package through
`mobcal self-check --choline` before it is kept.

The repository holds:

- `fortran/`: the sources, the choline input, the run file, and the two 2012 reference outputs.
- `src/mobcal/`: the Python package, with the element tables, the shipped methods, and the window.
- `tests/`: the test suite and its references.
- `tools/`: `check_public.py`, and the scripts that build the packages and the command-line page.
- `packaging/`: how the packages are built ([`packaging/README.md`](packaging/README.md)).
- `docs/`: the guide.

## Citation

Any research that uses this code or the included Lennard-Jones parameters should reference [1].

1. Campuzano, I.; Bush, M. F.; Robinson, C. V.; Beaumont, C.; Richardson, K.; Kim, H.; Kim, H. I.
   Structural Characterization of Drug-like Compounds by Ion Mobility Mass Spectrometry:
   Comparison of Theoretical and Experimentally Derived Nitrogen Collision Cross Sections. *Anal.
   Chem.* 2012, 84, 1026-1033. https://doi.org/10.1021/ac202625t
2. Mesleh, M. F.; Hunter, J. M.; Shvartsburg, A. A.; Schatz, G. C.; Jarrold, M. F. Structural
   Information from Ion Mobility Measurements: Effects of the Long Range Potential. *J. Phys.
   Chem.* 1996, 100, 16082-16086.
3. Kim, H.; Kim, H. I.; Johnson, P. V.; Beegle, L. W.; Beauchamp, J. L.; Goddard, W. A.; Kanik,
   I. Experimental and Theoretical Investigation into the Correlation between Mass and Ion
   Mobility for Choline and Other Ammonium Cations in N2. *Anal. Chem.* 2008, 80, 1928-1936.

Calculations made with the MMFF94/exp-6 programs of 2017 and 2018 should reference the two papers
that their repository, [bushgroup/MOBCAL-2018](https://github.com/bushgroup/MOBCAL-2018), lists.

## License

GNU General Public License v3.0. See [`LICENSE`](LICENSE).
