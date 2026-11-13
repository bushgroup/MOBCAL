# Reproducing MOBCAL 2012

The two programs MOBCAL runs, helium and nitrogen, are the 2012 release of MOBCAL (Campuzano et al.,
*Anal. Chem.* 2012, 84, 1026), kept as published at
[bushgroup/MOBCAL-2012](https://github.com/bushgroup/MOBCAL-2012) with its choline input and the two
reference outputs, choline in helium and in nitrogen. The 2012 element tables, the 2012 temperature
and sampling counts, and the 2012 seed are what `mobcal run` uses when it is given nothing else, so
the calculation of the release differs from the default run in one choice only, the random number
generator. On the example that ships with the release, choline (the 21-atom test ion of the 2012
paper), the shipped programs print each reference output in every line but 41, and each of those 41
lines is a change in how a value is printed, not in the value. One computed value has moved since
2012, on purpose, and it applies to nitrogen calculations of ions that contain silicon. This page
gives the commands, says what to compare and what the test suite holds, lists the differences, and
states that limit.

## The commands

To calculate a cross section as the 2012 release would have, run the program for the gas under
the 2012 random number generator. In the window, choose the method **MOBCAL 2012 (He)** or
**MOBCAL 2012 (N2)**, whose first seed is the 2012 seed. From a terminal, run

```
mobcal run Choline_pop.mfj --method 2012-he
mobcal run Choline_pop.mfj --method 2012-n2
```

`--rng ranlux` alone is the same as the first command, and the run records its method as
`2012-he` either way ([Methods](methods.md)). Everything else a calculation depends on is already
the 2012 value:

| What it sets | The 2012 release | A run without options |
|---|---|---|
| Element table | the 2012 table of the gas, 9 rows in helium and 10 in nitrogen | the same (`--parameters 2012`) |
| Temperature | 301 K | the same |
| Sampling counts | `imp = 1,000`, `itn = 10`, `inp = 40`, `inum = 250,000`, `inor = 30` | the same |
| Seed | 5013489 | the same |
| Random number generator | RANLUX, luxury level 3 | Philox4x32-10, unless `--rng ranlux` |

A run under Philox is a 2012 calculation in every respect but its random numbers: its cross
sections differ from the 2012 ones by a few tenths of a percent, as a run at another seed would,
and over many seeds the two generators give the same distribution ([How the two
compare](random-numbers.md#how-the-two-compare)). The seed belongs to the calculation, not to the
release ([The seed](random-numbers.md#the-seed)). For an ion other than the example, any seed under
either generator therefore gives a 2012 calculation, whereas a number published from the 2012
program reproduces only under RANLUX at the seed it was computed with.

The two runs write their outputs to `runs/Choline_pop-he-5013489-ranlux/mobcal.out` and
`runs/Choline_pop-n2-5013489-ranlux/mobcal.out`. The `record.json` beside each names the element
table, `MOBCAL 2012 helium` or `MOBCAL 2012 nitrogen`, with its SHA-256, and records the settings
as the 2012 ones ([The record of a run](results-folder.md#the-record-of-a-run)).

As one process, choline took 2.8 min in helium and 67 min in nitrogen on a 36-core workstation
(Windows 11, MSYS2 gfortran 16.2.0, November 2026). `--split 20` divides the calculation among
twenty processes and reports the result of one process exactly ([Divided
runs](large-ions.md#divided-runs)).

## Comparing with the references

For helium, `mobcal self-check --choline` runs this calculation and compares its three cross
sections with the reference in about three minutes ([Checking an
installation](install.md#checking-an-installation)). To compare whole outputs, take the
references, `Choline_He.out` and `Choline_N2.out`, the files in `sample-output/` of the release at
tag `v1.0`. An installation carries them in `examples/sample-output/` beside the input,
`examples/Choline.mfj`, and in the source code they are
[`fortran/sample-output/`](../fortran/sample-output/) and `fortran/Choline.mfj`. They were written
by g77 builds in 2012 from an input then named `Choline_pop.mfj`, and each output echoes the name
of its input twice, in its first line and in the SUMMARY. `Choline.mfj` holds the same
coordinates, so copy it to the echoed name before running, and edit neither side:

```
cp <installation>/examples/Choline.mfj Choline_pop.mfj
```

Then run the two commands in that folder and compare each output with its reference line by
line, after stripping end-of-line carriage returns, which a build on Windows writes and the
references do not carry. In a POSIX shell (Git Bash on Windows):

```bash
diff <(tr -d '\r' < <installation>/examples/sample-output/Choline_He.out) <(tr -d '\r' < runs/Choline_pop-he-5013489-ranlux/mobcal.out)
diff <(tr -d '\r' < <installation>/examples/sample-output/Choline_N2.out) <(tr -d '\r' < runs/Choline_pop-n2-5013489-ranlux/mobcal.out)
```

Each diff shows the 41 lines of [The differences in the output](#the-differences-in-the-output)
and nothing else. Every cross section and mobility, every standard deviation, the three
trajectories in helium that failed energy conservation with their diagnostics, and the SUMMARY
are the 2012 lines: 61.075 Å² by the projection approximation, 63.473 Å² by the exact hard-sphere
method, and 55.402 Å² by the trajectory method in helium, and 115.92 Å² by the trajectory method
in nitrogen, as the references print them. This was measured with MSYS2 gfortran 16.2.0 on
Windows on 24 October 2026, as one process and divided among 20 ([Divided runs](#divided-runs)),
and again on 13 November 2026, in helium as one process and in both gases divided among 20.

## What the tests hold

Unlike the [2000 comparison](mobcal-2000.md), this one is part of the test suite of the source
code, which continuous integration runs on Windows, macOS, and Linux for every change. To check
that a build still computes the 2012 numbers, the suite runs `Choline.mfj` through each program
under RANLUX at seed 5013489, staged under the name the references echo, and compares the output
with [`tests/reference/`](../tests/reference/README.md). Those two files hold what the shipped
programs print for choline in the two gases, and a test ties them to the 2012 originals line by
line: each differs from its original in exactly the 41 lines of the next section, the atom count
changed only in width and each q1st value equal to four times the 2012 value within its rounding.
A build that passes against them therefore reproduces every number of the 2012 outputs.

The comparison has three tiers:

1. Every line that does not depend on the random numbers matches character for character.
   `tests/stochastic-lines.txt` lists the lines that do depend on them, so a line that is not
   listed has to match, and a line the 2012 program never wrote fails the test.
2. Each reported cross section is within 0.1 % of the reference: the projection-approximation,
   exact hard-sphere, and trajectory-method values in helium, and the trajectory-method value in
   nitrogen.
3. The whole file is the reference byte for byte, carriage returns aside, on the platforms
   listed in `tests/strict-platforms.txt`, which are all three.

Helium goes through the three tiers in every run of the suite. The full nitrogen comparison
takes about an hour, so every run of the suite checks one tenth of it. The 2012 calculation is
ten cycles of 40,000 trajectories, and a calculation divided among ten processes gives the tenth
process exactly the trajectories of cycle 10, drawn from the random number stream where the nine
cycles before it leave off. The test runs that one process on choline in nitrogen and requires
its lines of the first tier, and the cross section and inverse mobility it prints for cycle 10,
to match the nitrogen reference character for character. The full nitrogen comparison runs every
Monday in continuous integration, on a manual run of the `ci` workflow with its nitrogen option
selected, and from the source code with

```
uv run pytest -m nitrogen
```

The suite also holds a divided run to the run as one process. Choline in helium runs under
RANLUX divided among one process and among three, and under Philox as one process and divided
among 10 and among 40. Each combined output must match the output of one process under the same
generator line for line, with no tolerance, apart from the lines a divided run adds or moves
([The output of a divided run](large-ions.md#the-output-of-a-divided-run)), and the
energy-conservation diagnostics of the processes together must be those of the one process.

## The differences in the output

Two print changes made since 2012 account for all 41 lines in each gas:

| Line | 2012 reference | The shipped program | Why it changed |
|---|---|---|---|
| `number of atoms =` (1 line) | `21` in four columns | `21` in seven columns | The atom bound is 200,000, and a count of that size needs seven columns. |
| `average values for q1st`, third column (40 lines) | e.g., `1.0661E+00` | e.g., `4.2644E+00` | The column is a sum over the `itn` cycles and was divided by `inp`, the number of velocity points, 40, where it should be divided by `itn`, 10. It is divided by `itn`, so it prints four times the 2012 value. |

The q1st column is a printed diagnostic: nothing reads it back, and the collision integrals, the
cross sections, and the standard deviation are accumulated separately. Each 2012 value times four
equals the value the shipped program prints to within the last printed digit, since both are
rounded to five significant figures. The `gst2` and `wgst` columns of that table are the 2012
lines, and with the division corrected the `wgst`-weighted sum of the q1st column equals the
printed `mean OMEGA*(1,1)`, 1.9045 in helium and 3.9847 in nitrogen, where before it was a quarter
of it. [`fortran/README.md`](../fortran/README.md) in the source code records each change, with
the lines it touched, under Changes since 2012.

The `mass of ion` line, which the 2000 comparison counts among its differences, is not one here.
Format 604 was `1pd11.4`, which g77 printed with an `E` exponent, as the 2012 references show,
and gfortran with a `D`. It is `1pe11.4`, and the shipped programs print the `E` of the
references.

## Silicon in nitrogen

One number the 2012 nitrogen program computed is not reproduced, on purpose. The 2012 sources
assigned each atom its parameters twice, in one routine for the first coordinate set of an input and
in another for each later set, and in the nitrogen program the second copy gave silicon the
Lennard-Jones well depth and radius of iron (0.0130 kcal/mol and 2.9120 Å, where the first copy gave
those of silicon, 0.4020 kcal/mol and 4.2950 Å). A 2012 nitrogen calculation of an ion that contains
silicon therefore treated silicon as silicon in the first coordinate set and as iron in every later
one. That was a copy error, and since 22 October 2026 both readers take the one row of the table for
silicon. So the trajectory-method cross section of the second and later coordinate sets of such an
input, and the averages over its sets, differ from the 2012 numbers, whereas a single coordinate
set, an ion without silicon, and every helium calculation are unaffected. Choline contains no
silicon, and both choline references are reproduced. The test suite holds this boundary on a two-set
test ion with one atom of each element: its nitrogen output equals that of the 2012 program but for
the results of the second set, and without silicon equals it entirely.

No input to the shipped programs reproduces the 2012 numbers for such an ion. The table has one
row per element and both readers look the same row up, so a table made to give silicon the
numbers of iron would give them to the first coordinate set as well. A 2012 number for a
nitrogen calculation of several coordinate sets of an ion containing silicon reproduces only with
[the 2012 program itself](#the-2012-program-itself).

## Divided runs

A run divided among processes with `--split` adds one line per coordinate set to the output and
moves the diagnostics of failed trajectories out of it, as it does for any ion ([The output of a
divided run](large-ions.md#the-output-of-a-divided-run)). With those lines set aside, a run of
choline divided among 20 processes differs from its reference in the same 41 lines as the run as
one process, in both gases, and the count of failed trajectories in the SUMMARY and every number
are the 2012 ones.

## The 2012 program itself

The 2012 sources build and run today without a change. The README of the release
([Compiling](https://github.com/bushgroup/MOBCAL-2012#compiling)) gives a gfortran line that asks
for the static storage of local variables, as the build recipe of MOBCAL (`mobcal.fortran`) does,
and explains why the README of 2012 found that optimized builds and gfortran builds failed. Built
from the sources at tag `v1.0` with that recipe and run on `Choline_pop.mfj` at seed 5013489, each
program prints its reference byte for byte once carriage returns are stripped, but for the `mass
of ion` line, which it prints with the `D` exponent of format 604 (gfortran 16.2.0, Windows, 24
October 2026). That program is the reference for any question the 41 lines leave open, and the
only route to a 2012 nitrogen number for several coordinate sets of an ion containing silicon. For
any other calculation, the shipped programs under the methods `2012-he` and `2012-n2` give the
same numbers with the input checks, run records, and parallel runs of this package.
