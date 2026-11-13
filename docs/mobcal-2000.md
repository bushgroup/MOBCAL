# Reproducing MOBCAL 2000

The MOBCAL helium program descends from the 2000 release of MOBCAL by the Jarrold group (Mesleh et
al., *J. Phys. Chem.* 1996, 100, 16082; Shvartsburg and Jarrold, *Chem. Phys. Lett.* 1996, 261, 86),
kept as distributed at [bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000). The 2012
helium source differs from the `mobcal.f` of that release in what it computes in three ways: the
element table (the Lennard-Jones well depths and radii of hydrogen, carbon, nitrogen, and oxygen,
and a fluorine row), the temperature (298 K in 2000, 301 K in 2012), and `imp`, the trajectories
per block of the trajectory method (25 in 2000, 1,000 in 2012). The package ships the 2000 element
table as a named set and reads the temperature and `imp` as run settings, so the shipped helium
program calculates every number the 2000 program calculates. On the example that ships with the
release it prints the reference output of the release in every line but 42, and each of those 42
lines is a change in how a value is printed, not in the value. This page gives the command, says
what to compare, and lists the differences.

## The command

To calculate a cross section as the 2000 release would have, run the helium program with the
2000 table, the 2000 settings, and the 2012 random number generator:

```
mobcal run a10A1.mfj --parameters 2000 --temperature 298 --imp 25 --rng ranlux --seeds 5013486
```

`--method 2000-he --seeds 5013486` is the same command in fewer words, and the run records its
method as `2000-he` whichever way it was asked for ([Methods](methods.md)). In the window, the
method **MOBCAL 2000 (He)** is the same calculation at the seeds the window uses, the 2012 seed
and those after it, so it reproduces the 2000 method on an ion other than the example. The example
of the release, run at 5013486, needs the command line, or in the window a method file that
carries that seed ([The seed](random-numbers.md#the-seed)).

Each option sets one thing to its value in the example run of the release, where the default run
would use the 2012 value:

| Option | The 2000 release | Without the option |
|---|---|---|
| `--parameters 2000` | the 2000 helium table, eight rows | the 2012 helium table, nine rows |
| `--temperature 298` | 298 K | 301 K |
| `--imp 25` | 25 trajectories per block | 1,000 |
| `--rng ranlux` | RANLUX, luxury level 3 | Philox4x32-10 |
| `--seeds 5013486` | the seed of the example in the release | 5013489, the 2012 seed |

The other four sampling counts are the same in 2000 and 2012 (`itn = 10` cycles, `inp = 40` velocity
points, `inum = 250,000` hard-sphere trajectories, `inor = 30` reflections), so they need no option.
Helium is the default gas. The seed is the one choice that belongs to the calculation, not to the
release: for an ion other than the example, any seed gives a 2000-release calculation, and the
seed the 2000 run used gives the numbers of that run. The run writes its output to
`runs/a10A1-he-5013486-ranlux-lj2000-t298-imp25/mobcal.out`, and its `record.json` names the table
as `MOBCAL 2000 helium` with its SHA-256 ([The 2000 helium set](parameters.md#the-2000-helium-set))
and records the two settings set over the 2012 ones ([The record of a
run](results-folder.md#the-record-of-a-run)).

The 2000 table covers eight elements: hydrogen, carbon, nitrogen, oxygen, sodium, silicon,
sulfur, and iron. An ion with any other element, fluorine included, is refused: the program
writes `type not defined for atom number N`, the line the 2000 program wrote, and stops with
status 1. The set is for helium only: the 2000 release had no nitrogen program, and the 2012
nitrogen program, though it descends from the 2000 source, has its own table.

The example in the release, `a10A1.mfj` (a sodiated alanine decamer, the test ion it ships: 104
atoms, 50 coordinate sets, calculated partial charges), takes about 20 minutes as one process on
a workstation. About a third of that is the projection and hard-sphere pass of the 50 coordinate
sets, since `imp = 25` makes the trajectory method only 10,000 trajectories per coordinate set.
`--split` divides only the trajectory method, every process repeats the projection and
hard-sphere pass, and the combining run repeats it once more, so dividing this calculation saves
little ([How a batch uses the cores](large-ions.md#how-a-batch-uses-the-cores)).

## Comparing with the reference

To check the reproduction on the example of the release, take `a10A1.mfj` and `a10A1.out.orig` from
[bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000) at tag `v1.0`, run the command
above in the folder that holds them, and compare the two outputs line by line after stripping
end-of-line carriage returns, which a build on Windows writes and the reference does not carry:

```bash
diff <(tr -d '\r' < a10A1.out.orig) <(tr -d '\r' < runs/a10A1-he-5013486-ranlux-lj2000-t298-imp25/mobcal.out)
```

Keep the name of the input. The output echoes it twice, in its first line and in the SUMMARY, and
the reference echoes `a10A1.mfj`.

The diff shows the 42 lines of [The differences in the output](#the-differences-in-the-output)
and nothing else. Every cross section and mobility of the 50 coordinate sets, by the projection
approximation, the exact hard-sphere method, and the trajectory method, every standard deviation,
the four failed trajectories with their diagnostics, and the SUMMARY are the 2000 lines: the
averages over the 50 sets are 183.74 Å² by the projection approximation, 206.03 Å² by the exact
hard-sphere method, and 196.31 Å² by the trajectory method, as the reference prints them. This was
measured with MSYS2 gfortran 16.2.0 on Windows on 24 October 2026, as one process and divided
among 40 ([Divided runs](#divided-runs)), and again as one process on 13 November 2026. The
comparison is not part of the test suite, which holds the program to the 2012 outputs on every
change ([What the tests hold](mobcal-2012.md#what-the-tests-hold)).

## The differences in the output

Three print changes made since 2012 account for all 42 lines:

| Line | 2000 reference | The shipped program | Why it changed |
|---|---|---|---|
| `number of atoms =` (1 line) | the count in four columns | the count in seven columns | The atom bound is 200,000, and a count of that size needs seven columns. |
| `mass of ion =` (1 line) | `7.5181D+02` | `7.5181E+02` | Format 604 was `1pd11.4`, the only `D` edit descriptor in the source, and printed a `D` exponent under the 2000 compiler and under gfortran, whereas g77 printed `E` for it, as the 2012 references show. It is `1pe11.4`, which prints `E` everywhere. |
| `average values for q1st`, third column (40 lines) | e.g., `2.4708E+00` | e.g., `9.8831E+00` | The column is a sum over the `itn` cycles and was divided by `inp`, the number of velocity points, 40, where it should be divided by `itn`, 10. It is divided by `itn`, so it prints four times the 2000 value. |

The first and third changes are the two of the 2012 comparison, which explains the q1st column
([The differences in the output](mobcal-2012.md#the-differences-in-the-output)): the column is a
printed diagnostic that nothing reads back, and each 2000 value times four equals the value the
shipped program prints to within the last printed digit (`2.4708E+00` × 4 is `9.8832`, printed
`9.8831E+00`). [`fortran/README.md`](../fortran/README.md) in the source code records each
change, with the lines it touched, under Changes since 2012.

## Divided runs

A run divided among processes with `--split` adds one line per coordinate set to the output and
moves the diagnostics of failed trajectories out of it, as it does for any ion ([The output of a
divided run](large-ions.md#the-output-of-a-divided-run)). With those lines set aside, a run of
the example divided among 40 processes differs from the reference in the same 42 lines as the
run as one process.

## The 2000 program itself

The 2000 source builds and runs today without a change. Built with the gfortran line in the
[MOBCAL-2000 README](https://github.com/bushgroup/MOBCAL-2000#building-and-running-it-today), which
asks for the static storage of local variables that the build recipe of MOBCAL
(`mobcal.fortran`) also asks for, it prints `a10A1.out.orig` byte for byte once carriage returns
are stripped, `D` exponent included (gfortran 16.2.0, Windows, 23 October 2026). That program is
the reference for any question the 42 lines leave open. For a calculation, the shipped helium
program with the five options above gives the same numbers with the input checks, run records,
and parallel runs of this package.
