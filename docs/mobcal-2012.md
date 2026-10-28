# Reproducing MOBCAL 2012

The two programs MOBCAL runs, helium and nitrogen, are the 2012 release of MOBCAL
(Campuzano et al., *Anal. Chem.* 2012, 84, 1026), kept as published at
[bushgroup/MOBCAL-2012](https://github.com/bushgroup/MOBCAL-2012) with its choline input and the
two reference outputs, choline in helium and in nitrogen. The 2012 element tables, the 2012
temperature and sampling counts, and the 2012 seed are what `mobcal run` uses when it is given
nothing else, so the calculation of the release differs from the default run in one choice
only, the random number generator. On the release's own example, choline (the 2012 paper's
21-atom test ion), the shipped programs print each reference output in every line but 41, and
each of those 41 lines is a change in how a value is printed, not in the value. One computed
value has moved since 2012, on purpose, and it applies to nitrogen calculations of ions that
contain silicon. This page gives the commands, says what to compare and what the test suite
holds, lists the differences, and states that limit.

## The commands

To calculate a cross section as the 2012 release would have, run the program for the gas under
the 2012 random number generator. In the window that is the method MOBCAL 2012 (He) or MOBCAL
2012 (N2), whose first seed is the 2012 seed; from a terminal,

```
mobcal run Choline_pop.mfj --method 2012-he
mobcal run Choline_pop.mfj --method 2012-n2
```

and `--rng ranlux` alone is the same as the first command ([Methods](methods.md)). Everything
else a calculation depends on is already the 2012 value:

| What it sets | The 2012 release | A run without options |
|---|---|---|
| Element table | the 2012 table of the gas, 9 rows in helium and 10 in nitrogen | the same (`--parameters 2012`) |
| Temperature | 301 K | the same |
| Sampling counts | `imp = 1,000`, `itn = 10`, `inp = 40`, `inum = 250,000`, `inor = 30` | the same |
| Seed | 5013489 | the same |
| Random number generator | RANLUX, luxury level 3 | Philox4x32-10, unless `--rng ranlux` |

A run under Philox is a 2012 calculation in every respect but its random numbers: its cross
sections differ from the 2012 ones in their last digits, as a run at another seed would, and
over many seeds the two generators give the same distribution
([Random numbers](random-numbers.md)). The seed belongs to the calculation rather than to
the release, so for an ion of one's own any seed under either generator gives a 2012
calculation, whereas a number published from the 2012 program reproduces only under RANLUX at
the seed it was computed with. The runs write their outputs to
`runs/Choline_pop-he-5013489-ranlux/mobcal.out` and `runs/Choline_pop-n2-5013489-ranlux/mobcal.out`,
and each `record.json` names the table, `MOBCAL 2012 helium` or `MOBCAL 2012 nitrogen`, with its
SHA-256 ([The element tables](parameters.md)), and records the settings as the 2012 ones
([The run settings](settings.md)).

Choline takes about 3 minutes in helium and about an hour in nitrogen on one workstation core.
`--split` divides the trajectory method among processes and reports the serial result exactly,
and the README records choline in nitrogen running 15.8 times faster split 20 ways than serially
([README](../README.md#running-calculations)).

## Comparing with the references

For helium, `mobcal self-check --choline` runs this calculation and compares its three cross
sections with the reference in about three minutes
([Installing MOBCAL](install.md#checking-an-installation)). To compare whole outputs, take the
references, `Choline_He.out` and `Choline_N2.out`, the files of the release's `sample-output/`
at tag `v1.0`, which the installation carries in `examples/sample-output/` beside the input,
`examples/Choline.mfj` (in the source code, they are
[`fortran/sample-output/`](../fortran/sample-output/) and `fortran/Choline.mfj`).
They were written by g77 builds in 2012 from an input then named `Choline_pop.mfj`, and each
output echoes its input's name twice, in its first lines and in the SUMMARY. `Choline.mfj` holds
the same coordinates, so copy it to the echoed name before running, rather than editing either
side:

```
cp <installation>/examples/Choline.mfj Choline_pop.mfj
```

Then run the commands above in that directory and compare each output with its reference line by
line, after stripping end-of-line carriage returns, which a build on Windows writes and the
references do not carry. In a POSIX shell (on Windows, Git Bash):

```bash
diff <(tr -d '\r' < <installation>/examples/sample-output/Choline_He.out) <(tr -d '\r' < runs/Choline_pop-he-5013489-ranlux/mobcal.out)
diff <(tr -d '\r' < <installation>/examples/sample-output/Choline_N2.out) <(tr -d '\r' < runs/Choline_pop-n2-5013489-ranlux/mobcal.out)
```

Each diff shows the 41 lines of the next section and nothing else. Every cross section and
mobility, every standard deviation, the three trajectories in helium that failed energy
conservation with their diagnostics, and the SUMMARY are the 2012 lines: 61.075 Å² by the
projection approximation, 63.473 Å² by the exact hard-sphere method and 55.402 Å² by the
trajectory method in helium, and 115.92 Å² by the trajectory method in nitrogen, as the
references print them. This was measured with MSYS2 gfortran 16.2.0 on Windows on 24 October
2026, serial and split 20 ways (below).

## What the tests hold

Unlike the [2000 comparison](mobcal-2000.md), this one is part of the source code's test suite,
which runs on Windows, macOS and Linux in continuous integration for every change. The suite
compares with [`tests/reference/`](../tests/reference/README.md), which holds what the current
programs print for choline in both gases, and a test ties those two files to the 2012 originals line
by line: each differs from its original in exactly the 41 lines below, the atom count changed only
in width and each q1st value equal to four times the 2012 value within its rounding. Against those
references every run of the suite holds the helium output in three tiers, the lines that do not
depend on the random numbers character for character, the cross sections within 0.1 %, and the whole
file byte for byte, carriage returns aside, on all three platforms, and holds nitrogen through one
of its ten cycles. The full nitrogen comparison takes about an hour, so it runs every Monday in
continuous integration and otherwise only when asked for. The
[README](../README.md#testing-against-the-2012-outputs) describes each test and how to run it.

## The differences in the output

Two print changes made since 2012 account for all 41 lines in each gas:

| Line | 2012 reference | This program | Why it changed |
|---|---|---|---|
| `number of atoms =` (1 line) | `21` in four columns | `21` in seven columns | The atom bound is now 200,000, and a count of that size needs seven columns. |
| `average values for q1st`, third column (40 lines) | e.g. `1.0661E+00` | e.g. `4.2644E+00` | The column is a sum over the `itn` cycles and was divided by `inp`, the number of velocity points, 40, rather than by `itn`, 10. It is now divided by `itn`, so it prints four times the 2012 value. |

The q1st column is a printed diagnostic: nothing reads it back, and the collision integrals, the
cross sections and the standard deviation are accumulated separately. Each 2012 value times four
equals the value this program prints to within the last printed digit, since both are rounded
to five significant figures. The `gst2` and `wgst` columns of that table are the 2012 lines, and
with the division corrected the `wgst`-weighted sum of the q1st column equals the printed
`mean OMEGA*(1,1)`, 1.9045 in helium and 3.9847 in nitrogen, where before it was a quarter of
it. [`fortran/README.md`](../fortran/README.md) in the source code records each change, with
the lines it touched, under Changes since 2012.

The `mass of ion` line, which the 2000 comparison counts among its differences, is not one here.
Format 604 was `1pd11.4`, which g77 printed with an `E` exponent, as the 2012 references show,
and gfortran with a `D`. It is now `1pe11.4`, and the shipped programs print the `E` of the
references.

## Silicon in nitrogen

One number the 2012 nitrogen program computed is not reproduced, on purpose. The 2012 sources
assigned each atom its parameters twice, in one routine for an input's first coordinate set and
in another for each later set, and in the nitrogen program the second copy gave silicon iron's
Lennard-Jones well depth and radius (0.0130 kcal/mol and 2.9120 Å, where the first copy gave
silicon's, 0.4020 kcal/mol and 4.2950 Å). A 2012 nitrogen calculation of an ion that contains
silicon therefore treated silicon as silicon in the first coordinate set and as iron in every
later one. That was a copy error, and since 22 October 2026 both readers take the one row of
the table, silicon's. So the trajectory-method cross section of the second and later coordinate
sets of such an input, and the averages over its sets, differ from the 2012 numbers, whereas a
single coordinate set, an ion without silicon, and every helium calculation are unaffected.
Choline contains no silicon, and both choline references are reproduced. The test suite holds
this boundary on a two-set test ion with one atom of each element: its nitrogen output equals
the 2012 program's but for the second set's results, and without silicon equals it entirely.

No input to the shipped programs reproduces the 2012 numbers for such an ion. The table has one
row per element and both readers look the same row up, so a table of one's own that gave silicon
iron's numbers would give them to the first coordinate set as well. A 2012 number for a
multi-set nitrogen calculation of an ion containing silicon reproduces only with the 2012
program itself (below).

## Split runs

A run with `--split W` adds differences of its own, the same ones it adds to any output: the
combined output carries one line per coordinate set recording the blocks it read, such as

```
 blocks of imp trajectories: integrated    0, read from files  400, empty    0 (worker  0 of 20)
```

followed by a blank line, and the diagnostic of a failed trajectory (`energy not conserved`, two
lines and the blank line before them) is printed by the worker that integrated it, in that
worker's `w01` to `wW` directory, instead of in the combined output. The count of failed
trajectories in the SUMMARY, and every number, are those of the serial run. With those lines set
aside, a run of choline split 20 ways differs from its reference in the same 41 lines as the
serial run, in both gases.

## The 2012 program itself

The 2012 sources build and run today without a change. The release's README
([Compiling](https://github.com/bushgroup/MOBCAL-2012#compiling)) gives a gfortran line that asks
for the static storage of local variables, as MOBCAL's own build recipe (`mobcal.fortran`)
does, and explains why the 2012 README found that optimized and gfortran builds failed. Built
from the sources at tag `v1.0` with that recipe and run on `Choline_pop.mfj` at seed 5013489,
each program prints its reference byte for byte once carriage returns are stripped, but for the
`mass of ion` line, which it prints with the `D` exponent of format 604 (gfortran 16.2.0,
Windows, 24 October 2026). That program is the reference for any question the 41 lines leave
open, and the only route to a 2012 nitrogen number for a multi-set ion containing silicon; for
any other calculation, the shipped programs under `--rng ranlux` give the same numbers with this
package's input checks, run records and parallel runs.
