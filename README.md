# MOBCAL

MOBCAL calculates the collision cross sections of ions in helium and in nitrogen by the
trajectory method. The Fortran at its core is the 2012 release of MOBCAL described in
Campuzano et al., *Anal. Chem.* 2012, 84, 1026, kept here with two additions: the program can
run one calculation as several processes and report the serial result exactly, and it can draw
its random numbers from a second generator, Philox4x32-10, in place of the 2012 generator,
RANLUX. Around it this
repository is building a Python package that compiles the Fortran, runs many calculations at
once on separate cores or one calculation across them, collects the results, and will ship as
an installer for people who do not manage compilers or Python environments.

## Status

Founded 2026-10-21. The Fortran is in place and builds on Windows, macOS and Linux in
continuous integration, which also runs the self-check and the tests on every change. The tests
include a regression test that runs the 2012 choline input through each build and compares the
result with the 2012 outputs. The Python package has a version, a build command, a self-check,
readers and writers for the file formats, and `mobcal run`, which runs many calculations at
once on separate processors, or one calculation across them with `--split`, and collects the
results. Each change also builds an installer
for Windows and archives for macOS and Linux, which run without a compiler or Python. A
graphical interface is planned once the command line has been used.

The physics of the 2012 code, including its Lennard-Jones parameters, is not being changed.
Questions about the parameters are being taken up separately, and no change to them will land
without a stated decision and a stated reason. The element tables are kept as one data file per
gas, every number the literal the 2012 source spelled, which the package checks and renders into
every run directory, and the programs read them from there
([docs/parameters.md](docs/parameters.md)); the test suite reads every row back through the
programs' own reader and holds it to the 2012 number to the last bit. The changes to the Fortran
so far are listed with their line counts in [fortran/README.md](fortran/README.md). Two add the
statements that let one calculation run as several processes, one replaces the element
tables in the source with the reading of that file, one adds the second random number
generator ([docs/random-numbers.md](docs/random-numbers.md)), and one makes the temperature and
the five sampling counts run settings read from a file
([docs/settings.md](docs/settings.md)). The others correct defects in how the
program reports: a refused input now exits with status 1, an input larger than the arrays is
refused instead of overrunning them, two output formats print what they were meant to, and the
shipped run file names a neutral output. None of them changes a number the program computes for
the 2012 choline input under the 2012 generator, and the regression test holds every line of
its output to the 2012 outputs on every change, byte for byte apart from the lines those two formats print. One copy error is corrected: the nitrogen program gave silicon iron's parameters
from the second coordinate set of an input on.

## Installing

[`docs/install.md`](docs/install.md) describes the Windows installer and the macOS and Linux
archives, which carry the `mobcal` command and the Fortran compiled for each platform, and how
to check an installation with `mobcal self-check`.

## What is here

- `fortran/`: the 2012 sources, the choline input, the run file and the two reference outputs.
  [`fortran/README.md`](fortran/README.md) lists every change since 2012, records the hashes,
  and says what the 2012 release said about compiling them. The reference outputs are unchanged.
- `src/mobcal/`: the Python package, with the two 2012 element tables and the 2000 helium table
  in `src/mobcal/parameters/`.
- `tools/check_public.py`: the self-check a fresh clone runs.
- `packaging/`: how the installers are built ([`packaging/README.md`](packaging/README.md)).
- `docs/`: the installation guide, every command and option
  ([`docs/command-line.md`](docs/command-line.md)), the element-table format
  ([`docs/parameters.md`](docs/parameters.md)), the two random number generators
  ([`docs/random-numbers.md`](docs/random-numbers.md)), the run settings
  ([`docs/settings.md`](docs/settings.md)), writing an input from an ORCA output or an `.xyz`
  file ([`docs/import.md`](docs/import.md)), and how to reproduce a calculation of the 2012
  release ([`docs/mobcal-2012.md`](docs/mobcal-2012.md)) and of the 2000 helium release
  ([`docs/mobcal-2000.md`](docs/mobcal-2000.md)).

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
2012 reference outputs on Windows, macOS and Linux, byte for byte apart from two print changes
made since ([Testing against the 2012 outputs](#testing-against-the-2012-outputs)).

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

## Running calculations

An input file can be written by hand ([`fortran/Choline.mfj`](fortran/Choline.mfj) is the 2012
example) or from an ORCA output or an `.xyz` file with the charges you name
([`docs/import.md`](docs/import.md)):

```
uv run mobcal import choline_sp.out --charges chelpg -o choline.mfj
```

`mobcal run` runs the built binaries on one or more input files, one process per calculation
and several at once ([`docs/command-line.md`](docs/command-line.md) lists every command and
option):

```
uv run mobcal run choline.mfj --gas both --seeds 5013489,1234567 --workers 4 --out runs
```

A calculation is one input file, one gas, one seed and one random number generator. The
command makes one job for every combination of the inputs given (paths or globs), the gas
(`he`, `n2` or `both`; helium by default) and the seeds (the 2012 seed, 5013489, by default),
under the generator `--rng` names (Philox4x32-10 by default, or `ranlux`), prints how the runs
will use the processors and about how long they will take, runs them `--workers` at a time (by
default, as many as the machine has processors), and prints each result as it lands. Each run
gets a directory of its own under `--out`, named for the input, the gas and the seed, with
`-ranlux` appended under RANLUX, the element table when it is not the gas's default (`-lj2000`,
or `-lj` and the start of a file's SHA-256), and each setting that differs from 2012, and
holding a copy of the input, the `mobcal.in` the program read, the element table rendered as
`parameters.tab`, the run settings rendered as `settings.tab`, the output it wrote as
`mobcal.out`, whatever it printed to the console as `stdout.log`, and `record.json`, which
records the program and its build, the input and its hash, the seed and the generator, the
element table and its hash, the settings and where they came from, the method they make
(`current`, `2012`, `2000` or `custom`), the times and the result.
The directory is a
complete record of the run: the program started again in that directory repeats the
calculation. When every run has landed, `summary.csv` and `summary.json` are written beside the
run directories, one row per run with its seed, generator and method, its status, its cross
sections in Å², and the time the program took. For an input with several coordinate sets the
row carries the mean over sets, as the program reports it, and `summary.json` the value for
each set. The summaries cover every run the folder holds, not only the last command's, so one
results folder can hold a study: a later command adds its runs beside the earlier ones, with
`--skip-done` leaves out the runs the folder already holds complete, and refuses to run an input
whose name another input's run directory already carries. `mobcal methods-text runs` prints a
methods paragraph for the runs in a folder, with the program, version, method, gas, element
table, temperature, trajectory counts, generator and seeds, and the papers to cite.

`--method` names a calculation as a whole. `--method 2012` is the calculation of the 2012
release ([`docs/mobcal-2012.md`](docs/mobcal-2012.md)) and `--method 2000` that of the 2000
helium release ([`docs/mobcal-2000.md`](docs/mobcal-2000.md)), each equal to the command lines
those pages give, and the default, `current`, is the 2012 tables and settings under Philox. An
option given beside a method overrides that one value, and the run records the method as
`custom`. The seed is not part of a method. The window, `mobcal gui`, offers the same three
methods ([`docs/window.md`](docs/window.md)).

A number published from MOBCAL 2012 reproduces only under the generator it was computed with,
RANLUX, and at its seed:

```
uv run mobcal run choline.mfj --rng ranlux
```

reports the 2012 choline cross sections in helium to every printed digit, whereas the default,
Philox, reports cross sections from a different random number stream, which differ in their
last digits as a run at another seed would. [`docs/random-numbers.md`](docs/random-numbers.md)
describes the two generators and why the default is the newer one, and
[`docs/mobcal-2012.md`](docs/mobcal-2012.md) gives the commands for both gases and how their
outputs compare with the 2012 references.

The temperature and the five sampling counts that the 2012 programs compiled in (301 K; 1,000
trajectories per block, 10 cycles and 40 velocity points in the trajectory method; 250,000
trajectories and 30 reflections in the hard-sphere pass) are run settings:

```
uv run mobcal run choline.mfj --temperature 298 --imp 25
uv run mobcal run choline.mfj --settings mine.toml
```

A run that sets nothing uses the 2012 values and prints the 2012 output. The package renders
the settings into each run directory as `settings.tab`, the programs read the file when it is
there, and an output at other settings equals what a program with those constants compiled in
prints. [`docs/settings.md`](docs/settings.md) describes the file, the options, the bounds and
the record.

A run that did not finish is reported as failed, never as a number. The program exits with
status 1 when it refuses its input (the 2012 program exited with status 0 either way), and the
command also reads the output file: a completed calculation ends in a SUMMARY block. A nonzero
exit or an output without that block is a failure whose message is the last line the program
wrote, for example `type not defined for atom number      1` for an element its tables do not
define. An input the
program would stop on, such as more than 200,000 atoms, more than 100 coordinate sets, or a units
line that is not exactly `ang` or `au`, is refused before the program starts. The command exits
with status 1 if any run failed.

The Fortran is single-threaded, so the speedup above comes from running independent calculations
on separate processors. One calculation can also run across them:

```
uv run mobcal run choline.mfj --gas n2 --split 8 --out runs
```

runs the choline calculation in nitrogen as eight processes and reports the serial result
exactly: the same cross section, standard deviation and failure count to every printed digit,
because the random number stream is partitioned rather than re-drawn and the sums are made by
the serial program's own statements. The trajectory method integrates 400 blocks of 1,000
trajectories per coordinate set at the 2012 settings, one per cycle and velocity point (the
block count is the number of cycles times the number of velocity points, so other settings
give other counts), and each of the eight
processes integrates every eighth block in velocity-major order, so that its share mixes the
slow collisions with the fast, reaches each of its own blocks with the random number stream in
the state the serial run would have had, by moving the draw count past the other blocks under
Philox or by drawing through them under RANLUX, and writes a 76-byte file per block it
integrated, which carries the seed, the generator and the settings along with the block's
sums. When all eight
have landed, the program runs once more in the run directory as the combining run, which
integrates nothing, reads the 400 files back and makes the sums, the averages and the SUMMARY
with the same statements the serial run uses. That output is the run's output, read as any
other; the eight workers' directories, `w01` to `w08`, are kept beside it as records. A worker
that did not write every block it owed fails the run, and the combining run never starts. Any
`--split` from 1 to 400 balances, since the blocks are dealt round robin, and `--workers` then
counts split calculations in flight, each of them `--split` processes. Without the fourth record
that `--split` writes to `mobcal.in`, the program runs as one process, and without a generator
word on the seed record as well, it runs the 2012 calculation.

Every process repeats the part of the calculation that precedes the trajectories (the
projection and hard-sphere cross sections and the search for the largest impact parameter at
each velocity), and the combining run repeats it once more, so the speedup falls short of the
process count by that fixed cost: a few seconds per process for choline in helium, about
fifteen in nitrogen. Measured on one workstation (Windows 11, 80 threads, shared with other
work, MSYS2 gfortran 16.2.0), choline in helium ran 1.8, 4.0, 6.6 and 9.5 times faster than
serial across 2, 5, 10 and 20 processes, and choline in nitrogen 8.8 times faster across 10
and 15.8 times across 20, with every combined output equal to the 2012 output in every digit;
those runs were made under RANLUX, before the second generator existed.
The split pays best on the long calculations, which is what it is for.

## Testing against the 2012 outputs

To check that a build still computes the 2012 numbers, the test suite runs `Choline.mfj`
through each binary under RANLUX at seed 5013489, the generator and seed the references were
produced with, and compares
the output with `tests/reference/` in three tiers. Those two files are what the current programs
print for choline, and they differ from the 2012 originals in `fortran/sample-output/` in 41
lines each, the width of the atom count and the q1st column, which now prints four times the
2012 value (two print changes, [`fortran/README.md`](fortran/README.md)); a test holds them to
the originals line by line, allowing those two changes and nothing else, so a build that passes
against them reproduces every number of the 2012 outputs. The first tier compares every line that does
not depend on the random number stream character for character. `tests/stochastic-lines.txt`
lists the lines that do, so a line that is not listed has to match, and a line the 2012 code
never wrote fails the test. The second compares the reported cross sections within 0.1 %: the
projection-approximation, exact hard-sphere and trajectory-method values in helium, and the
trajectory-method value in nitrogen. The third requires the whole file to be byte-identical to
the reference on the platforms listed in `tests/strict-platforms.txt`, which are all three. A
fourth test runs the same helium calculation split across one process and across three, and
requires each combined output to match the serial run's line for line, with no tolerance, apart
from the energy-conservation diagnostics, which the process that integrated the failing
trajectory prints, and the one line that marks a combined output as combined; the diagnostics
themselves must be conserved across the workers. The same helium calculation runs under
Philox as well, serially and split across 10 and 40 processes, and each split output must
match the serial Philox output by the same rule.

To check the nitrogen program in every run of the suite without the hour its full comparison
takes, a fifth test runs a tenth of it. The 2012 calculation is ten cycles of 40,000
trajectories, and a calculation split across ten processes gives the tenth process exactly the
trajectories of cycle 10, drawn from the random number stream where the nine cycles before it
leave off. The test runs that one process on the choline input in nitrogen and requires its
deterministic lines, and the cross section and inverse mobility it prints for cycle 10, to
match the nitrogen reference character for character.

The helium and full nitrogen comparisons go through the same driver as `mobcal run`, and the
runs a session needs, the one-cycle nitrogen process included, run at the same time. The helium comparison takes
about 3 minutes and the nitrogen cycle about 8, and both run with every `uv run pytest`. The
full nitrogen comparison takes about an hour and runs only when asked for:

```
uv run pytest -m nitrogen
```

Continuous integration runs the nitrogen comparison every Monday, and on a manual run of the
`ci` workflow with its nitrogen option selected. To make the same comparison by hand, and for
the lines in which the current outputs differ from the 2012 ones, see
[`docs/mobcal-2012.md`](docs/mobcal-2012.md).

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
[bushgroup/MOBCAL-2012](https://github.com/bushgroup/MOBCAL-2012), and the Jarrold group's 2000
helium release, from which the 2012 helium program was made, as distributed at
[bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000).

## License

GNU General Public License v3.0. See [`LICENSE`](LICENSE).
