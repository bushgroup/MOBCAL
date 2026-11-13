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
byte for byte. This page describes where the values come from, what each one is, the bounds,
the rendered file, and the test that holds a run at other values to a program compiled with
them. [Large ions and long runs](large-ions.md) gives the limits on the charge and the size of
an ion and what a divided run does at other settings.

## Setting them

In the window, the temperature is a field under Basics and the five counts are fields under
Advanced, each filled by the method chosen; a value changed there shows the method as Custom
([The window](window.md#method-basics-and-advanced)). From a terminal, `mobcal run` takes the
values of the method and any of the six given singly:

```
mobcal run choline.mfj --temperature 298 --imp 25
mobcal run choline.mfj --method mine.method.json --inp 20
```

A set of settings worth keeping is a method file ([Method files](methods.md#method-files)),
which holds all six values beside the gas, the element table, and the generator they were chosen
for. The six are `temperature` (K; a number greater than zero), `imp`, `itn`, `inp`, `inum`, and
`inor` (integers). The precedence is the 2012 values, then those of the method, then the
single-value options, so `--method mine.method.json --imp 1000` runs the settings of the file
with `imp` put back. The 2000 helium release ran at 298 K with `imp` 25, and the method
**MOBCAL 2000 (He)**, `--method 2000-he`, sets both beside the 2000 element table ([Reproducing
MOBCAL 2000](mobcal-2000.md)).

The name of the run directory carries each value that differs from 2012, so two runs of one
input and seed at different settings never share a directory ([The name of a run
directory](results-folder.md#the-name-of-a-run-directory)).

## What the values are

The temperature enters the velocity grid of the trajectory method, through the reduced
temperature kT/ε, and the conversion of each cross section to a mobility, through the factor of
1/sqrt(T) in the Mason-Schamp equation. The element tables were fitted near room temperature,
and whether a table holds at another temperature is for the user to judge; the program accepts
any temperature greater than zero and below 10^300 K.

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
| `temperature` | greater than 0 and below 10^300 | a positive, finite number under the square root |
| `imp` | 1 to 999,999 | printed in six columns |
| `itn` | 1 to 100 | the per-cycle arrays hold 100 |
| `inp` | 1 to 100 | the velocity-point arrays hold 100 |
| `inum` | 1 to 9,999,999 | printed in seven columns |
| `inor` | 1 to 100 | the reflection arrays hold 100 |
| `itn` × `inp` × `imp` | at most 9,999,999 | `total number of points` is printed in seven columns |

The last bound is the field width of a 2012 output line, kept rather than widened so that the
2012 outputs stay the references the test suite compares with. Ten million trajectories per
coordinate set is 25 times the 2012 count, which for choline as one process is 77 min in helium
and 29 h in nitrogen, i.e., 25 times the 185 s and the 70 min that the 2012 settings took on
one 40-core workstation (Windows 11, MSYS2 gfortran 16.2.0, October 2026), so no use so far
approaches it.

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
the input is read; the refusal is the only line of the output file and is echoed to the screen.
The six values a run read are printed to the screen, never to the output file, so an output at
the 2012 values is the 2012 output.

To prepare a directory for running a program by hand, render the settings of a method there
along with its element table:

```
mobcal render-parameters he path/to/run --method mine.method.json
```

Without `--method` the command writes the 2012 settings and the default table of the gas, and
`--parameters` replaces the table either way.

## Equal to a compiled build

At the 2012 values, with or without `settings.tab`, the outputs are the 2012 outputs; the
regression test runs every choline comparison through the rendered file. At other values an
output equals what a program with those constants compiled in prints: the test suite builds a
copy of the sources with 298 K and `imp = 25` written into the defaults of the reader, runs
choline in helium through it with no `settings.tab` and through the shipped program with those
settings rendered, and requires the two outputs to be byte-identical; nitrogen is held the same
way at 350 K, `imp = 10`, `itn = 5`, and `inp = 20`.

## The record

`record.json` in each run directory carries a `settings` block, and `summary.csv` and
`summary.json` carry the six values of every run ([The record of a
run](results-folder.md#the-record-of-a-run)).
