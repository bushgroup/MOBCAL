# The run settings

Six numbers set how much of a calculation a MOBCAL run does and at what temperature. The 2012
release compiled them into both programs: the temperature, 301 K, and five sampling counts of
the two methods. The trajectory method (MOBIL2 in the source) integrates `imp` trajectories per
block, one block for each of `inp` velocity points in each of `itn` cycles, 1,000 trajectories
in 400 blocks at the 2012 values; the projection and exact hard-sphere pass (MOBIL4, in the
helium program only) follows `inum` trajectories, each through at most `inor` reflections,
250,000 and 30 in 2012. Changing any of them meant editing the source and recompiling, which is
what the published users who ran more trajectories did.

The programs now read these values from a file in the directory they run in, `settings.tab`,
and take the 2012 values when there is no such file. The package renders that file into every
run directory, as it renders the element table, from the six values of the method and whatever
the user changed. A run that asks for nothing uses the 2012 values and prints the 2012 output,
byte for byte. This page describes where the values come from, the command-line options, the
bounds, what a split run does at other settings, and what the run record carries.

## Setting them

In the window, the temperature is a field under Basics and the five counts are fields under
Advanced, each filled by the method chosen; a value changed there makes the method *Custom*
([The window](window.md#method-basics-and-advanced)). From a terminal, `mobcal run` takes the
values of the method and any of the six given singly:

```
mobcal run choline.mfj --temperature 298 --imp 25
mobcal run choline.mfj --method mine.method.json --inp 20
```

A set of settings worth keeping is a method file ([Methods](methods.md#method-files)), which
holds the six values beside the gas, the element table and the generator they were chosen for;
a key it leaves out keeps the 2012 value. The six are `temperature` (K; a number greater than
zero), `imp`, `itn`, `inp`, `inum` and `inor` (integers). The precedence is the 2012 values, then
those of the method, then the single-value options, so `--method mine.method.json --imp 1000`
runs the settings of the file with `imp` put back. Version 2.0 also read a separate settings
file, the six values alone in TOML through `--settings`; a method file now does what it did, and
the option is gone.

The name of the run directory carries each value that differs from 2012, in the order above, so two
runs of one input and seed at different settings never share a directory:
`choline-he-5013489-ranlux-t298-imp25`, or, with the 2000 element table as well,
`choline-he-5013489-ranlux-lj2000-t298-imp25`.

## What the values are

The temperature enters the velocity grid of the trajectory method, through the reduced
temperature kT/ε, and the conversion of each cross section to a mobility, through the factor of
1/sqrt(T) in the Mason-Schamp equation. The element tables were fitted near room temperature,
and whether a table holds at another temperature is for the user to judge; the program accepts
any positive, finite temperature.

The five counts set the sampling. `imp` is the Monte Carlo sample over impact parameter and
orientation at each velocity point in each cycle; `itn` cycles give `itn` independent
estimates of the collision integral, whose standard deviation the program reports; `inp` is the
number of points in the integration over relative velocity. Their product is the number of
trajectories per coordinate set, 400,000 in 2012. `inum` and `inor` govern the hard-sphere pass
in helium alone: the nitrogen program does not call it, and reads and records the two values
without using them.

## The bounds

The programs refuse a `settings.tab` whose values the 2012 arrays or output formats cannot
hold, and the package refuses the same values, in a method file or given singly, before a run
starts:

| Setting | Allowed | Why |
|---|---|---|
| `temperature` | greater than 0, finite | the square root of T |
| `imp` | 1 to 999,999 | printed in six columns |
| `itn` | 1 to 100 | the per-cycle arrays hold 100 |
| `inp` | 1 to 100 | the velocity-point arrays hold 100 |
| `inum` | 1 to 9,999,999 | printed in seven columns |
| `inor` | 1 to 100 | the reflection arrays hold 100 |
| `itn` × `inp` × `imp` | at most 9,999,999 | `total number of points` is printed in seven columns |

The last bound is the field width of a 2012 output line, kept rather than widened so that the
2012 outputs stay the references the test suite compares with. Ten million trajectories per
coordinate set is 25 times the 2012 count, about 75 minutes in helium and a day in nitrogen on
one workstation core, so no use so far approaches it.

## How charged and how large an ion can be

Before its trajectories, each program finds at each velocity point the largest impact parameter,
b_max, at which a trajectory still deflects the gas. It integrates one trajectory at a time,
with b² rising in steps of ro² (ro = 3.043 Å), until five in a row give 1 − cos χ under the
cutoff of 5 × 10⁻⁴, and it refuses the ion with `ibst greater than 10000` if the walk passes
10,000 steps, b = 304 Å. The 2012 program stopped at 500 steps, b = 68 Å. The refusal comes
after the ion has been read, the projection and hard-sphere pass made and the potential scanned,
so for a large ion it arrives minutes to hours into the run.

b_max is largest at the slowest velocity point, and there it grows with the net charge of the
ion, through the attraction between the charge and the dipole it induces in the gas, and with
the size of the ion. For a compact charge, choline with every partial charge multiplied by z,
b_max² at the slowest point is z times a slope that falls as the inverse square root of the
temperature:

| Gas | Slope at 200 K | Slope at 301 K | Slope at 500 K | First charge the 2012 program refused, 200 / 301 / 500 K |
|---|---|---|---|---|
| nitrogen | 47.0 ro² | 38.3 ro² | 29.7 ro² | 11+ / 13+ / 17+ |
| helium | 16.2 ro² | 13.2 ro² | 10.3 ro² | 31+ / 38+ / 50+ |

At 10,000 ro² the cap is reached by a compact charge near 260+ in nitrogen and 750+ in helium at
301 K. An extended ion adds its size. At 1+, b_max at the slowest point lies about 11 Å beyond
the outer atoms of an ion of protein density in helium and about 18 Å in nitrogen, so the 2012
program refused such an ion beyond an outer radius of about 57 Å in helium and 50 Å in nitrogen,
about 39,000 and 26,000 atoms, whereas the cap now lies far beyond the radius of an ion of
200,000 atoms, about 98 Å. A charged protein ion sits above the line of its charge alone: a
5,220-atom protein ion of 12+ (the β-lactoglobulin A dimer, an IM-MS size calibrant, as an
in-vacuo MD endpoint from PDB 1BSY with OPLS-AA per-atom charges) needs b_max² = 563 ro² at 301
K in nitrogen, which the 2012 program refused, and 262 ro² in helium. The search costs about 700
trajectories plus one per ro² of the largest b_max², so an ion that needs no more than 500 costs
what it did.

In nitrogen a second limit arrives well before the cap. The program abandons a trajectory that
takes more than 30,000 integration steps, prints `trajectory lost`, and counts it with a
deflection of 90° rather than as a failure. For a compact charge at 301 K this begins near 30+,
with an occasional lost trajectory in the Monte Carlo, and from about 50+ the search itself runs
through lost trajectories, so that b_max at the slowest point is set by the step limit rather
than by the deflection. Note that the output of a run in nitrogen of an ion charged this highly
should be searched for `trajectory lost`. Helium lost no trajectory up to 100+ in the same
tests.

The walk lays b along the axis through the farthest atom of the ion, starts inside the ion, and
ends at the first five small deflections. An atom far beyond the rest along that axis is
therefore not reached: a 200-atom ion with one atom 40 to 100 Å out on that axis is given b_max
= 18 Å in helium and 25 Å in nitrogen at the slowest point, whatever the distance of that atom.
This is the 2012 convention, and both programs keep it.

## The rendered file

`settings.tab` is two lines, written for the list-directed reads of the program:

```
MOBCAL-SETTINGS 1
3.0100000000000000d+02 1000 10 40 250000 30
```

The first line names the format; the second holds the temperature and the five counts in the
order `t imp itn inp inum inor`. The temperature is written with seventeen significant digits
and a `d` exponent, which the program reads back as exactly the double-precision number the
package held: `temperature = 301` reaches the program as the `301.d0` the 2012 source compiled,
and the test suite reads a range of temperatures back through the reader in the program itself
and holds each to the same 64-bit pattern. Without the file the program assigns the 2012 values
itself. With a file that is not of this format, cannot be read to its end, or holds a value
outside the bounds, the program stops with status 1 and says which, before the element table or
the input is read; the refusal is the only line of the output file and is echoed to the screen. The
six values a run read are printed to the screen, never to the output file, so an output at the
2012 values is the 2012 output.

To prepare a directory for running a program by hand, render the settings of a method there
along with its element table:

```
mobcal render-parameters he path/to/run --method mine.method.json
```

Without `--method` the command writes the 2012 settings and the default table of the gas, and
`--parameters` replaces the table either way.

## Split runs

A calculation split across processes (by the choice the window makes,
[The window](window.md#how-a-batch-uses-the-processors-and-the-estimate), or by `--split`) deals
`itn` × `inp` blocks per coordinate set among its workers, 400 at the 2012 values and up to
10,000 at the bounds, so `--split` takes any worker count up to that product. Each block file
carries the settings its block was integrated under, after the seed and the generator, and the
combining run refuses a block from other settings as it refuses one from another seed or
generator. The test suite runs choline in helium at 3 cycles of 7 velocity points split four
ways, under both generators, and holds the combined output to the serial one line for line.

The blocks are shared among the workers in one of two ways, `--dealing claimed`, the default,
or `--dealing static`. Claimed lets each worker take the next block that no worker has taken
yet, so a worker that finishes its blocks early keeps working until none is left, and a worker
slowed by other work on the computer does not set the time the run takes. Static gives each worker a
fixed share of the blocks, every W-th one over an index that mixes the velocity points. The result is the same
under both: the trajectories of a block depend only on its place in the random stream, not on which
process computes them, so the combined output is the serial output either way. Under Philox a
claiming worker takes the slowest blocks first, which is what keeps the workers finishing
together; under RANLUX it can only take them in the order of the stream.

## Equal to a compiled build

At the 2012 values, with or without `settings.tab`, the outputs are the 2012 outputs; the regression
test runs every choline comparison through the rendered file. At other values an output equals
what a program with those constants compiled in prints: the test suite builds a copy of the
sources with 298 K and `imp = 25` written into the defaults of the reader, runs choline in helium
through it with no `settings.tab` and through the shipped program with those settings rendered,
and requires the two outputs to be byte-identical; nitrogen is held the same way at 350 K,
`imp = 10`, `itn = 5` and `inp = 20`.

## The 2000 reference

The settings reach back past 2012. The 2000 helium release of the Jarrold group, kept as distributed
at [bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000), ran at 298 K with `imp = 25`
and shipped an example, a sodiated alanine decamer over 50 coordinate sets, with its reference
output at seed 5013486. The shipped helium program, given the 2000 element table, which the package
ships as the helium set `2000` ([The element tables](parameters.md)), and run with `--parameters
2000 --temperature 298 --imp 25 --rng ranlux` at that seed, prints that reference output line for
line (gfortran 16.2.0, Windows, 2026-10-24), apart from the three lines whose format changed after
2012: the `mass of ion` exponent letter, the width of the atom count, and the q1st column. The same
holds split 40 ways. Reproducing a number calculated with the 2000 release is therefore a table and
two settings, not a different program; [Reproducing MOBCAL 2000](mobcal-2000.md) gives the command
and the comparison.

## The record

`record.json` in each run directory and the per-run entries of `summary.json` carry a
`settings` block: the six values, whether they are the 2012 ones, the values given singly over
those of the method, and the name of the rendered file. A record written by version 2.0 also has the
path and SHA-256 of the settings file the run named, `null` when it named none.
`summary.csv` carries the six values as columns after the generator.
