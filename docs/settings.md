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
run directory, as it renders the element table, from the shipped settings file and whatever the
user asked for. A run that asks for nothing uses the 2012 values and prints the 2012 output,
byte for byte. This page describes the settings file a user writes, the command-line options,
the bounds, what a split run does at other settings, and what the run's record carries.

## Setting them

`mobcal run` takes a settings file and single values:

```
uv run mobcal run choline.mfj --temperature 298 --imp 25
uv run mobcal run choline.mfj --settings mine.toml --inp 20
```

A settings file is TOML with `format = 1` and any of the six keys. A key left out keeps the 2012
value, so a file that changes one thing says one thing:

```toml
format = 1
imp = 25
```

The six keys are `temperature` (K; an integer or a float greater than zero), `imp`, `itn`,
`inp`, `inum` and `inor` (integers). The shipped file, `src/mobcal/settings/mobcal_2012.toml`,
holds all six at their 2012 values with a line on what each one is. The precedence is the 2012
values, then the file named by `--settings`, then the single-value options, so
`--settings mine.toml --imp 1000` runs the file's settings with `imp` put back.

The run directory's name carries each value that differs from 2012, in the order above, so two
runs of one input and seed at different settings never share a directory:
`choline-he-5013489-ranlux-t298-imp25`, or, with the 2000 element table as well,
`choline-he-5013489-ranlux-lj2000-t298-imp25`.

## What the values are

The temperature enters the velocity grid of the trajectory method, through the reduced
temperature kT/ε, and the conversion of each cross section to a mobility, through the factor of
1/sqrt(T) in the Mason-Schamp equation. The element tables were fitted near room temperature,
and whether a table holds at another temperature is the user's judgement; the program accepts
any positive, finite temperature.

The five counts set the sampling. `imp` is the Monte Carlo sample over impact parameter and
orientation at each velocity point in each cycle; `itn` cycles give `itn` independent
estimates of the collision integral, whose standard deviation the program reports; `inp` is the
number of points in the integration over relative velocity. Their product is the number of
trajectories per coordinate set, 400,000 in 2012. `inum` and `inor` govern the hard-sphere pass
in helium alone: the nitrogen program does not call it, and reads and records the two values
without using them.

## The bounds

The programs refuse a settings file whose values the 2012 arrays or output formats cannot hold,
and the package refuses the same values before a run starts:

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

## The rendered file

`settings.tab` is two lines, written for the program's list-directed reads:

```
MOBCAL-SETTINGS 1
3.0100000000000000d+02 1000 10 40 250000 30
```

The first line names the format; the second holds the temperature and the five counts in the
order `t imp itn inp inum inor`. The temperature is written with seventeen significant digits
and a `d` exponent, which the program reads back as exactly the double-precision number the
package held: `temperature = 301` reaches the program as the `301.d0` the 2012 source compiled,
and the test suite reads a range of temperatures back through the program's own reader and
holds each to the same 64-bit pattern. Without the file the program assigns the 2012 values
itself. With a file that is not of this format, cannot be read to its end, or holds a value
outside the bounds, the program stops with status 1 and says which, before the element table or
the input is read; the refusal is the output file's only line and is echoed to the screen. The
six values a run read are printed to the screen, never to the output file, so an output at the
2012 values is the 2012 output.

To prepare a directory for running a program by hand, render the settings there along with the
element table:

```
uv run mobcal render-parameters he path/to/run --settings mine.toml
```

## Split runs

A calculation split across processes ([the README](../README.md#running-calculations)) deals
`itn` × `inp` blocks per coordinate set among its workers, 400 at the 2012 values and up to
10,000 at the bounds, so `--split` takes any worker count up to that product. Each block file
carries the settings its block was integrated under, after the seed and the generator, and the
combining run refuses a block from other settings as it refuses one from another seed or
generator. The test suite runs choline in helium at 3 cycles of 7 velocity points split four
ways, under both generators, and holds the combined output to the serial one line for line.

## Equal to a compiled build

At the 2012 values, with or without the file, the outputs are the 2012 outputs; the regression
test runs every choline comparison through the rendered file. At other values an output equals
what a program with those constants compiled in prints: the test suite builds a copy of the
sources with 298 K and `imp = 25` written into the reader's defaults, runs choline in helium
through it with no settings file and through the shipped program with those settings rendered,
and requires the two outputs to be byte-identical; nitrogen is held the same way at 350 K,
`imp = 10`, `itn = 5` and `inp = 20`.

## The 2000 reference

The settings reach back past 2012. The Jarrold group's 2000 helium release, kept as distributed
at [bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000), ran at 298 K with
`imp = 25` and shipped an example, a sodiated alanine decamer over 50 coordinate sets, with its
reference output at seed 5013486. The shipped helium program, given that release's element
table, which the package ships as the helium set `2000` ([parameters.md](parameters.md)), and
run with `--parameters 2000 --temperature 298 --imp 25 --rng ranlux` at that seed, prints that reference output line for line (gfortran 16.2.0, Windows, 2026-10-24),
apart from the three lines whose format changed after 2012: the `mass of ion` exponent letter,
the width of the atom count, and the q1st column. The same holds split 40 ways. Reproducing a
number calculated with the 2000 release is therefore a table and two settings, not a
different program; [mobcal-2000.md](mobcal-2000.md) gives the command and the comparison.

## The record

`record.json` in each run directory and the per-run entries of `summary.json` carry a
`settings` block: the six values, whether they are the 2012 ones, the settings file's path and
SHA-256 if one was named, the values given singly, and the name of the rendered file.
`summary.csv` carries the six values as columns after the generator.
