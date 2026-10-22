# fortran/

The 2012 release of MOBCAL, with one addition. These six files are the content of
[bushgroup/MOBCAL-2012](https://github.com/bushgroup/MOBCAL-2012) at its tag `v1.0`, copied from
those blobs on 2026-10-21 with LF line endings, plus the statements listed under Changes below,
which let one calculation run as several processes. `mobcal.fortran.SHA256` pins each file as it
is committed, and `tools/check_public.py` and the test suite compare. They are not edited
casually: a change to any of them is a decision recorded elsewhere, lands with new pins and a
new row below in the same commit, and counts its diff line by line in the commit message.

| File | What it is |
|---|---|
| `mobcal_He.f` | Fortran 77 source, helium |
| `mobcal_N2.f` | Fortran 77 source, nitrogen |
| `mobcal.in` | Run file: input file name, output file name, random seed, one per line |
| `Choline.mfj` | The choline input used in the 2012 paper |
| `sample-output/Choline_He.out` | The 2012 output for choline in helium |
| `sample-output/Choline_N2.out` | The 2012 output for choline in nitrogen |

## Changes since 2012

Each row is one commit. A change adds statements and alters none, so that a run file without
the records a change reads leaves the program the 2012 program, statement for statement, and
the regression test holds it to the 2012 outputs byte for byte.

| Date | Lines added, removed | What |
|---|---|---|
| 2026-10-21 | `mobcal_He.f` +80, −0; `mobcal_N2.f` +74, −0 | **One calculation as several processes.** An optional fourth record of `mobcal.in`, `W w`, makes the run worker `w` of `W`. In `mobil2` the Monte Carlo is 400 blocks of `imp` trajectories per coordinate set, one per cycle and velocity point; a worker integrates the blocks with `(k - 1) mod W = w - 1`, draws the random stream through the others (the four draws per trajectory, with no trajectory), and writes each block it integrated as one unformatted record, `block-<set>-<k>.dat`: set, cycle, point, seed, the block's two sums `temp1` and `temp2`, and its energy-conservation failures. A run with `w = 0` integrates nothing, reads every block back, checks the four integers, adds the failures to `ifailc`, and makes the sums, the averages and the SUMMARY with the 2012 statements. Helium's reader also stops, as helium's `gsang` does, when the failures reach `ifail`. One output line, `blocks of imp trajectories: ...`, is printed when the record is present. The He file has six more lines than the N2 file: that stop. Nothing is read from a block file without its set, cycle, point and seed matching. |

## What the 2012 release said about building

The 2012 README compiled with g77 and reported two things: compiler optimization such as `-O2`
produced binaries that did not execute correctly, and gfortran had not worked. Both observations
were correct and both have the same cause. The code relies on local variables keeping their
values between calls, which g77 gave it by default. gfortran gives locals automatic storage
under optimization unless told otherwise with `-fno-automatic`. With that flag, an optimized
gfortran build reproduces both reference outputs byte for byte on Windows, macOS and Linux; the
flags the package uses are recorded in `mobcal.fortran` and nowhere else.

## Two things to know before comparing an output with the references

The references were produced with g77, and a gfortran build differs from them in two ways that
are formatting, not physics. On Windows the program writes CRLF line endings, because gfortran's
runtime opens the output unit in text mode. And the `mass of ion` line is printed with a `1pd`
edit descriptor, which gfortran renders with a `D` exponent where g77 wrote `E`. A comparison
strips end-of-line carriage returns and rewrites the exponent letter on that one line, and
should do nothing else.

The references also echo the name of the input file they were run on, twice, and that name is
`Choline_pop.mfj`. This repository ships the same coordinates as `Choline.mfj`, so a comparison
copies the input to the echoed name before running rather than editing either side.

## The run file

`mobcal.in` as shipped names `Choline.mfj` as input, `temp.choline.n2.out` as output, and seed
`5013489`, which is the seed the references were run at. The output name is the same for both
gases. A fourth record, `W w`, is read when present and makes the run one process of a split
calculation, as the Changes table describes; `mobcal run --split W` writes it, and the shipped
file does not carry it.
