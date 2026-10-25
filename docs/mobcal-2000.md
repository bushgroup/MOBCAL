# Reproducing MOBCAL 2000

The helium program in this repository descends from the Jarrold group's 2000 release of MOBCAL
(Mesleh et al., *J. Phys. Chem.* 1996, 100, 16082; Shvartsburg and Jarrold, *Chem. Phys. Lett.*
1996, 261, 86), kept as distributed at
[bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000). The 2012 helium source
differs from that release's `mobcal.f` in what it computes in three ways: the element table (the
Lennard-Jones well depths and radii of hydrogen, carbon, nitrogen and oxygen, and a fluorine
row), the temperature (298 K in 2000, 301 K in 2012), and `imp`, the trajectories per block of
the trajectory method (25 in 2000, 1,000 in 2012). The package now ships the 2000 element
table as a named set and reads the temperature and `imp` as run settings, so the shipped helium
program calculates every number the 2000 program calculates. On the release's own example it
prints the release's reference output in every line but 42, and each of those 42 lines is a
change in how a value is printed, not in the value. This page gives the command, says what to
compare, and lists the differences.

## The command

To calculate a cross section as the 2000 release would have, run the helium program with the
2000 table, the 2000 settings and the 2012 random number generator:

```
uv run mobcal run a10A1.mfj --parameters 2000 --temperature 298 --imp 25 --rng ranlux --seeds 5013486
```

Each option sets one thing to its value in the release's example run, where the default run
would use the 2012 value:

| Option | The 2000 release | Without the option |
|---|---|---|
| `--parameters 2000` | the 2000 helium table, eight rows | the 2012 helium table, nine rows |
| `--temperature 298` | 298 K | 301 K |
| `--imp 25` | 25 trajectories per block | 1,000 |
| `--rng ranlux` | RANLUX, luxury level 3 | Philox4x32-10 |
| `--seeds 5013486` | the seed of the release's example | 5013489, the 2012 seed |

The other four sampling counts are the same in 2000 and 2012 (`itn = 10` cycles, `inp = 40`
velocity points, `inum = 250,000` hard-sphere trajectories, `inor = 30` reflections), so they
need no option. Helium is the default gas. The seed is the one choice that belongs to the
calculation rather than to the release: for an ion of one's own, any seed gives a 2000-release
calculation, and the seed the 2000 run used gives that run's numbers. The run writes its output
to `runs/a10A1-he-5013486-ranlux-t298-imp25/mobcal.out`, and its `record.json` names the table
as `MOBCAL 2000 helium` with its SHA-256 ([parameters.md](parameters.md)) and records the two
settings ([settings.md](settings.md)).

The 2000 table covers eight elements, hydrogen, carbon, nitrogen, oxygen, sodium, silicon,
sulfur and iron. An ion with any other element, fluorine included, is refused: the program stops
with status 1 and writes `type not defined for atom number N`, as the 2000 program did. The set
is for helium only; the nitrogen program has no 2000 ancestor and no 2000 table.

The release's example, `a10A1.mfj` (a sodiated alanine decamer, the release's test ion: 104
atoms, 50 coordinate sets, calculated partial charges), takes about 20 minutes on one
workstation core, most of it the projection and hard-sphere pass, since `imp = 25` makes the
trajectory method only 10,000 trajectories per coordinate set. `--split` divides only the
trajectory method, and every process repeats the hard-sphere pass, so splitting this
calculation saves little.

## Comparing with the reference

To check the reproduction on the release's example, take `a10A1.mfj` and `a10A1.out.orig` from
[bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000) at tag `v1.0`, run the command
above in the directory that holds them, and compare the two outputs line by line after stripping
end-of-line carriage returns, which a build on Windows writes and the reference does not carry:

```bash
diff <(tr -d '\r' < a10A1.out.orig) <(tr -d '\r' < runs/a10A1-he-5013486-ranlux-t298-imp25/mobcal.out)
```

Keep the input's name. The output echoes it twice, in its first line and in the SUMMARY, and the
reference echoes `a10A1.mfj`.

The diff shows the 42 lines of the next section and nothing else. Every cross section and
mobility of the 50 coordinate sets, by the projection approximation, the exact hard-sphere
method and the trajectory method, every standard deviation, the four failed trajectories with
their diagnostics, and the SUMMARY are the 2000 lines: the averages over the 50 sets are 183.74
Å² by the projection approximation, 206.03 Å² by the exact hard-sphere method and 196.31 Å² by
the trajectory method, as the reference prints them. This was measured with MSYS2 gfortran
16.2.0 on Windows on 24 October 2026, serial and split 40 ways (below). The comparison is not
part of the test suite, which holds the program to the 2012 outputs on every push
([mobcal-2012.md](mobcal-2012.md)).

## The differences in the output

Three print changes made since 2012 account for all 42 lines:

| Line | 2000 reference | This program | Why it changed |
|---|---|---|---|
| `number of atoms =` (1 line) | the count in four columns | the count in seven columns | The atom bound is now 200,000, and a count of that size needs seven columns. |
| `mass of ion =` (1 line) | `7.5181D+02` | `7.5181E+02` | Format 604 was `1pd11.4`, the only `D` edit descriptor in the source, and printed a `D` exponent under the 2000 compiler and under gfortran, whereas g77 printed `E` for it, as the 2012 references show. It is now `1pe11.4`, which prints `E` everywhere. |
| `average values for q1st`, third column (40 lines) | e.g. `2.4708E+00` | e.g. `9.8831E+00` | The column is a sum over the `itn` cycles and was divided by `inp`, the number of velocity points, 40, rather than by `itn`, 10. It is now divided by `itn`, so it prints four times the 2000 value. |

The q1st column is a printed diagnostic: nothing reads it back, and the collision integrals, the
cross sections and the standard deviation are accumulated separately. Each 2000 value times four
equals the value this program prints to within the last printed digit, since both are rounded
to five significant figures (`2.4708E+00` × 4 is `9.8832`, printed `9.8831E+00`). The `gst2` and
`wgst` columns of that table are the 2000 lines, and with the division corrected the
`wgst`-weighted sum of the q1st column equals the printed `mean OMEGA*(1,1)`, where before it was a
quarter of it. [fortran/README.md](../fortran/README.md) records each change, with the lines it
touched, under Changes since 2012.

## Split runs

A run with `--split W` adds differences of its own, the same ones it adds to any output: the
combined output carries one line per coordinate set recording the blocks it read, such as

```
 blocks of imp trajectories: integrated    0, read from files  400, empty    0 (worker  0 of 40)
```

followed by a blank line, and the diagnostic of a failed trajectory (`energy not conserved`, two
lines and the blank line before them) is printed by the worker that integrated it, in that
worker's `w01` to `wW` directory, instead of in the combined output. The count of failed
trajectories in the SUMMARY, and every number, are those of the serial run. With those lines set
aside, a run of the example split 40 ways differs from the reference in the same 42 lines as the
serial run.

## The 2000 program itself

The 2000 source builds and runs today without a change. Built with the gfortran line in the
[MOBCAL-2000 README](https://github.com/bushgroup/MOBCAL-2000#building-and-running-it-today),
which asks for the static storage of local variables that this repository's recipe in
`mobcal.fortran` also asks for, it prints `a10A1.out.orig` byte for byte once carriage returns are stripped, `D` exponent included
(gfortran 16.2.0, Windows, 23 October 2026). That program is the reference for any question the
42 lines leave open; for a calculation, the shipped helium program with the five options above
gives the same numbers with this package's input checks, run records and parallel runs.
