# fortran/

The 2012 release of MOBCAL, with two additions and a few corrections. Six of these files are the
content of [bushgroup/MOBCAL-2012](https://github.com/bushgroup/MOBCAL-2012) at its tag `v1.0`,
copied from those blobs on 2026-10-21 with LF line endings, plus the changes listed under Changes
below: statements that let one calculation run as several processes, the reading of the element
table from a file, a second random number generator the run file can select, the reading of the
temperature and the sampling counts from a file, and corrections to defects that leave every
number the 2012 program computed unchanged. The seventh to tenth files are the element-table
reader, that generator, the declaration of the atom arrays and the settings reader, which both
sources include.

The helium source descends from the Jarrold group's 2000 release, kept as distributed at
[bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000). The 2012 `mobcal_He.f` is
that release's `mobcal.f` with 13 changed regions and nothing else: the run file's name, the
temperature (301 K from 298 K), `imp` (1,000 trajectories per velocity point per cycle from
25), the Lennard-Jones well depths and radii of hydrogen, carbon, nitrogen and oxygen in both
coordinate readers (each 2012 pair is the 2000 pair times one factor per element, 0.95, 0.99,
1.10 and 0.80, on well depth and radius alike), and a row for fluorine. The nitrogen source has
no 2000 ancestor. Since the table, the temperature and the sampling counts became files the
programs read (Changes, below), the shipped helium program reproduces the 2000 release's
reference output on its own example, given that release's table as a parameter file and
`--temperature 298 --imp 25` ([docs/settings.md](../docs/settings.md)).

`mobcal.fortran.SHA256` pins each file as it is committed, and `tools/check_public.py` and the
test suite compare. They are not edited casually: a change to any of them is a decision
recorded elsewhere, lands with new pins and a new row below in the same commit, and counts its
diff line by line in the commit message.

| File | What it is |
|---|---|
| `mobcal_He.f` | Fortran 77 source, helium |
| `mobcal_N2.f` | Fortran 77 source, nitrogen |
| `mobcal_ljread.inc` | The element-table reader, included by both sources (added 2026-10-22) |
| `mobcal_rng.inc` | Philox4x32-10, the second random number generator, included by both sources (added 2026-10-22) |
| `mobcal_arrays.inc` | The atom bound and the four common blocks it dimensions, included by every routine that uses them (added 2026-10-23) |
| `mobcal_settings.inc` | The run-settings reader, the temperature and the five sampling counts, included by both sources (added 2026-10-24) |
| `mobcal.in` | Run file: input file name, output file name, random seed, one per line |
| `Choline.mfj` | The choline input used in the 2012 paper |
| `sample-output/Choline_He.out` | The 2012 output for choline in helium |
| `sample-output/Choline_N2.out` | The 2012 output for choline in nitrogen |

## Changes since 2012

Each row is one commit. No change moves a number the 2012 program computes for the choline
input: the regression test runs it in both gases and holds every line of the output to a
reference, byte for byte after stripping end-of-line carriage returns. Until 2026-10-23 the
references were the 2012 outputs themselves; the row of that date changes how two things print,
the atom count and the q1st column, and the references since are `tests/reference/`, which the
test suite holds to the 2012 outputs line by line, those two changes apart. The additions are
statements a run file without the records they read never reaches, and the reading of the
element table from a file, which the test suite holds to the 2012 tables row by row to the last
bit; the corrections alter how a line is printed or what the program does when it refuses an
input, never a value it computes, with one exception recorded in its row: a copy error in the
nitrogen table that gave silicon iron's parameters from the second coordinate set of an input on.

| Date | Lines added, removed | What |
|---|---|---|
| 2026-10-21 | `mobcal_He.f` +80, −0; `mobcal_N2.f` +74, −0 | **One calculation as several processes.** An optional fourth record of `mobcal.in`, `W w`, makes the run worker `w` of `W`. In `mobil2` the Monte Carlo is 400 blocks of `imp` trajectories per coordinate set, one per cycle and velocity point; a worker integrates the blocks with `(k - 1) mod W = w - 1` for `k = (ig - 1) itn + ic`, velocity-major, draws the random stream through the others (the four draws per trajectory, with no trajectory), and writes each block it integrated as one unformatted record, `block-<set>-<k>.dat`: set, cycle, point, seed, the block's two sums `temp1` and `temp2`, and its energy-conservation failures. A run with `w = 0` integrates nothing, reads every block back, checks the four integers, adds the failures to `ifailc`, and makes the sums, the averages and the SUMMARY with the 2012 statements. Helium's reader also stops, as helium's `gsang` does, when the failures reach `ifail`. One output line, `blocks of imp trajectories: ...`, is printed when the record is present. The He file has six more lines than the N2 file: that stop. Nothing is read from a block file without its set, cycle, point and seed matching. |
| 2026-10-21 | `mobcal_He.f` +1, −1; `mobcal_N2.f` +1, −1 | **Blocks dealt velocity-major.** The block index becomes `k = (ig - 1) itn + ic` instead of `(ic - 1) inp + ig`, so that a worker's share mixes velocity points: a block's cost rises steeply at low velocity (by about ten times in nitrogen), and dealing in stream order pinned each worker to fixed velocity points whenever W divided 40, the slowest nitrogen worker of ten taking twice as long as the fastest. The index names the block file; the file's own set, cycle and point are unchanged. |
| 2026-10-22 | `mobcal_He.f` +1, −1; `mobcal_N2.f` +1, −1 | **The `mass of ion` line prints an `E` exponent.** Format 604 was `1pd11.4`, the only `D` edit descriptor in either file: g77 printed it with an `E`, as the references show, and gfortran with a `D`. It is `1pe11.4`, and a gfortran build prints the line as the references do, so a comparison no longer rewrites it. |
| 2026-10-22 | `mobcal_He.f` +12, −12; `mobcal_N2.f` +10, −10 | **A refusal exits with status 1.** Every termination was a bare `stop`, which exits 0, so a refusal and a finished calculation looked the same to a caller. Each refusal's `stop` is `stop 1`: in both files `units not specified`, `charge distribution not specified`, `type not defined for atom number` (twice, once per coordinate-set reader), `masses do not add up`, `Problem orientating along x axis`, `ibst greater than 500`, and the three refusals of the split reader above; in helium also the `ifail` cap in `gsang` and the split reader's own `ifail` stop. The normal end is the one bare `stop` left in each file, and exits 0. No line of any output file changes. |
| 2026-10-22 | `mobcal_He.f` +14, −2; `mobcal_N2.f` +14, −2 | **The array bounds are checked.** The number of coordinate sets and the number of atoms were read with no check against the arrays they index, 100 sets (the main program's `dimension tmc(100)` and its neighbours) and 1,000 atoms (`parameter (len=1000)`), so a larger input wrote past them. Each count is now checked in `fcoord` right after it is echoed, with `.gt.` because the bound itself is legal: above it the program writes `number of coordinate sets exceeds the limit of 100` or `number of atoms exceeds the limit of 1000` and stops with status 1, the set count being refused before the atom count is read. Six lines per guard. The `type not defined for atom number` refusal's format 602 widens from `i3` to `i4` in both of its copies, so that atom 1,000 prints as a number rather than `***`. No line of the choline outputs changes. |
| 2026-10-22 | `mobcal.in` +1, −1 | **The shipped run file names a neutral output.** Its second record was `temp.choline.n2.out` for both gases, so a helium run by hand wrote a file named for nitrogen. It is `choline.out`. Input, seed and output contents are unchanged; `mobcal run` writes its own run file and never read this one. |
| 2026-10-22 | `mobcal_He.f` +13, −194; `mobcal_N2.f` +13, −235; `mobcal_ljread.inc` +186, new | **The element table is read from a file.** Each program assigned every atom its mass, Lennard-Jones well depth and radius and hard-sphere radius from a chain of `if(imass(iatom).eq.NN)` blocks, written once in `fcoord` and again in `ncoord`, with nitrogen's four combining constants assigned above each chain. Both chains and the constants are gone from both sources. In their place the main program calls `ljread` once, after it opens the output file and before it reads the input, and each reader calls `ljparm` per atom; both live in the new include. `ljread` reads `parameters.tab` from the working directory, the table `mobcal run` renders from the gas's data file: the format line, the kind in bytes of each column, in nitrogen the constants, the row count, and one row per element. Every token is read as text and converted by its column's kind, single or double precision, and promoted, so a literal the 2012 source spelled in single precision gives the number the compiled source gave; each well depth and radius is evaluated term for term as the 2012 statement evaluated it. `ljparm` looks an atom's key up and assigns the four quantities with the same final factors, and an atom whose key is not in the table meets the same format 602 refusal as before. The set's name and hash go to the screen; no output file gains a line, and the comments that stood over each chain travel with the numbers into the data files. A table that is missing, not of this format, for the other gas, of a kind the reader does not convert, longer than 100 rows or unreadable is refused with status 1 before anything is calculated. One number does move, and on purpose: in nitrogen, `ncoord`'s silicon block held iron's well depth and radius (0.0130 and 2.9120 where `fcoord`'s held 0.4020 and 4.2950), a copy error, so the second and later coordinate sets of a nitrogen input containing silicon were computed with iron's parameters; the table carries `fcoord`'s row and both readers now agree. Of the removed lines, 66 in helium and 81 in nitrogen are comments. Choline contains no silicon, and both choline outputs are unchanged. |
| 2026-10-22 | `mobcal_He.f` +11, −28; `mobcal_N2.f` +11, −28 | **The dead RAND branch is gone.** `xrand` chose between RANLUX and the F77 `rand` intrinsic on `i5`, which the main program set to 1 and nothing changed, so the `rand` arm, the `call srand(i2)` that seeded it on every run, and the two `using RAND with seed integer` formats (604 in the main program and 617 in the SUMMARY) with their `if(i5.ne.1)` branches were never reached. They are removed: `xrand` calls RANLUX and returns, the banner and the SUMMARY print their RANLUX lines unconditionally, and `i5` keeps its name as the generator selector. Of the 28 lines removed per file, 16 are statements and 12 are comments; the 11 added are all comments, re-worded for one generator. `rluxgo` and the first draw are unchanged. No line of any output changes. |
| 2026-10-22 | `mobcal_He.f` +65, −23; `mobcal_N2.f` +65, −23; `mobcal_rng.inc` +157, new | **A second random number generator, chosen by the run file.** The third record of `mobcal.in` is the seed integer followed by an optional word, `ranlux` or `philox`. The main program reads the record as a line and takes the seed and then the word from it with internal list-directed reads (`end=` for the bare record), sets `i5` to 1 or 2, and refuses any other word with status 1 before the element table or the input is read. At `ranlux` nothing differs: `rluxgo` is called and prints its lines, the banner and the SUMMARY print their RANLUX lines, `xrand` draws from RANLUX. At `philox`, `xrand` draws from Philox4x32-10 (Salmon, Moraes, Dror and Shaw, SC 2011, as the Random123 library defines it; the test suite holds the include to the library's known-answer vectors) in the new include: the key is (seed, 0), the counter is the running count of draws, draw n being counter block (n−1)/2 and its output words 0 and 1 or 2 and 3, and the uniform is 52 bits of the two words plus a half, (k + 1/2)/2^52, an odd multiple of 2^−53 that is never 0 or 1 and exact in double precision; the banner and the SUMMARY print `using Philox4x32-10 with seed integer =` where the RANLUX lines print (formats 604 and 617, the labels the removed RAND lines had), and `rluxgo` is not called. The draw count lives in the include's own common block; `i6` stays the 2012 call count. In a split run a worker at `philox` moves the count past another worker's block, 4·imp draws, instead of drawing through it with `rantate`; at `ranlux` the draw-through stays. The block file gains the generator as a fifth integer after the seed, and the reader refuses a block from the other generator as it refuses one from another seed, naming it in format 692. Of the 65 lines added per file 43 are statements and 22 comments; of the 23 removed, 9 are statements and 14 comments; the include is 157 lines, 70 of them comments. A run file without the word is the 2012 run: the choline gate holds in both gases. |
| 2026-10-23 | `mobcal_He.f` +15, −105; `mobcal_N2.f` +15, −105; `mobcal_arrays.inc` +24, new | **The atom bound is declared once.** `parameter (len=1000)` and the four common blocks it dimensions, `/charge/`, `/coordinates/`, `/ljparameters/` and `/hsparameters/`, were written out in 15 routines of each source, seven lines a copy. Each copy is now one line, `include 'mobcal_arrays.inc'`, in the place of the parameter statement, so the readers' `dimension imass(len),xmass(len)` still follows it; the `/printswitch/` and `/constants/` blocks between them stay where they were. In the include `fx`, `fy` and `fz` are dimensioned `len+1`, the others `len`: `mobil4` writes the incidence vector of each projection trajectory into slot `inatom+1` of those three arrays and rotates it with the atoms, and for an ion of exactly `len` atoms, which the reader accepts, that slot was `fy(1)`, `fz(1)` and `ox(1)`, so the first atom's coordinates were overwritten in the projection and hard-sphere pass. The bound is still 1,000 atoms. Of the include's 24 lines, 17 are comments. No line of either choline output changes. |
| 2026-10-23 | `mobcal_He.f` +6, −6; `mobcal_N2.f` +6, −6 | **Atom counts print in seven columns, and the q1st column is divided by the number of cycles.** Formats 612 (`number of atoms =`), 652 (`number of atoms exceeds the limit of`), 602 in `fcoord` and in `ncoord` (`type not defined for atom number`) and 602 in `mobil2` (the atom index of the `Problem orientating along x axis` listing) print `i7`, where they printed `i4` or `i5`, so that every count and index the bound will allow prints as a number. The `average values for q1st` table printed `q1st(ig)/dfloat(inp)`, the sum over the cycles divided by the number of velocity points, 40, instead of by the number of cycles it was summed over, `itn`, 10; it now prints `/dfloat(itn)`, four times the 2012 values, and the wgst-weighted sum of the column is the printed `mean OMEGA*(1,1)`, as it was a quarter of it before. Nothing reads the column back: the collision integrals, the cross sections and the standard deviation accumulate separately and do not move. So 41 lines of each choline output change, the atom count's width and the 40 q1st values, and every other line is the 2012 line; `tests/reference/` holds the outputs the changed programs print, and the test suite ties them to the 2012 originals, which stay as they were. |
| 2026-10-23 | `mobcal_arrays.inc` +1, −1 | **The atom bound is 200,000.** `parameter (len=1000)` becomes `parameter (len=200000)`, in the one place it is now declared: an ion of up to 200,000 atoms is read and computed, which holds the largest IM-MS size calibrants with their hydrogens and room to spare. The 16 double-precision arrays of the four common blocks and the readers' two per-atom arrays are static, about 30 MB per process, and the binary's file size does not change. `fcoord`'s guard compares with `len` and its refusal prints it, so above the bound the program writes `number of atoms exceeds the limit of 200000`; `mobcal.io.mfj.MAX_ATOMS` mirrors the bound and refuses first, and `tools/check_public.py` fails if the two disagree. The cost of a calculation grows with the atom count: the projection and hard-sphere pass alone is about a minute per thousand atoms on a workstation, every trajectory step sums over every atom, and at the bound a calculation is weeks of processor time. No line of either choline output changes. |
| 2026-10-24 | `mobcal_He.f` +39, −27; `mobcal_N2.f` +39, −28; `mobcal_settings.inc` +137, new | **The temperature and the five sampling counts are read from a file.** Each main program assigned `t=301.d0`, `imp=1000`, `itn=10`, `inp=40`, `inum=250000` and `inor=30`, and changing one meant editing the source and recompiling. The six assignments are gone from both sources; in their place the main program calls `setread`, in the new include, right after the generator word is checked and before the element table is read. `setread` assigns the same six values and then, if a file `settings.tab` is in the working directory, reads the six from it: a format line, `MOBCAL-SETTINGS 1`, and one line of six tokens, the temperature as a double-precision literal and the counts as integers, which `mobcal run` renders from its settings file and the user's choices into every run directory. Without the file the program computes what it computed before, and the shipped run file runs the 2012 calculation as it did. A file that is not of this format or cannot be read to its end, a temperature that is not a positive finite number, a count outside its bound, or a product `itn*inp*imp` above 9,999,999 is refused with status 1 before anything is calculated, the refusal being the output file's only line. The bounds are the 2012 arrays and formats, declared as parameters in the include: `itn` and `inp` at most 100 (`om11st`, `pgst` and their neighbours in `mobil2` are dimension 100), `inor` at most 100 (`cof`, `crof` in `mobil4`), `imp` at most 999,999 (printed `i6`), `inum` at most 9,999,999 (printed `i7`), and the product at most 9,999,999 (`total number of points` is `i7`); the fields were kept rather than widened, so that no line of a 2012 output moves. The six values go to the screen, never to the output file. The split's block file carries the settings a block was integrated under, `imp itn inp inum inor` as integers and `t` as a double after the generator, 76 bytes with gfortran's markers, and the reader refuses a block from other settings as it refuses one from another seed or generator, format 692 naming what it found; a block file that cannot be read as the record is refused with a line of its own (format 694). `inum` and `inor` reach `mobil2` through the `/split/` common block for that. Blocks per set are `itn*inp`, up to 10,000, so the block file name's index prints `i5.5` where it printed `i4.4` and the three counts of format 690's `blocks of imp trajectories` line print `i5` where they printed `i4`; neither is a 2012 line. Of the lines added per source, 23 are statements and 16 comments; of those removed, 16 are statements and 11 (helium) or 12 (nitrogen, a commented-out `imp=500`) comments. Of the include's 137 lines, 46 are comments. Both choline outputs are unchanged, with and without a `settings.tab` naming the 2012 values. |
| 2026-10-24 | `mobcal_He.f` +5, −2; `mobcal_N2.f` +5, −2 | **The x-axis orientation's off-axis tolerance scales with the ion.** Before the trajectories, `mobil2` rotates the atom farthest from the centre of mass onto +x and stops with `Problem orientating along x axis` unless `fx/rmax` is within 1e-10 of 1 and the atom's `fy` and `fz` are within a tolerance, which was an absolute 1.0d-20 m. When the farthest atom already lies almost on +x the last rotation is almost nothing, and the program computes it to about 1e-11 rad, so an ion of large radius in that orientation was refused after its projection and hard-sphere pass: a 200-atom ion with one atom 100 Å out on +x, and a 200,000-atom ion with its farthest atom on +x, on the workstation the change was made on. The tolerance is now `tolxy = max(1.0d-20, 1.0d-10·rmax)`, the fx test's relative precision and never tighter than 2012, so every ion the 2012 program accepted it still accepts; for an ion of 100 Å it is about 1e-18 m. One statement and two comment lines added, and the two continuation lines of the test altered, in each file. The check prints nothing when it passes, so no line of either choline output changes. |

## What the 2012 release said about building

The 2012 README compiled with g77 and reported two things: compiler optimization such as `-O2`
produced binaries that did not execute correctly, and gfortran had not worked. Both observations
were correct and both have the same cause. The code relies on local variables keeping their
values between calls, which g77 gave it by default. gfortran gives locals automatic storage
under optimization unless told otherwise with `-fno-automatic`. With that flag, an optimized
gfortran build reproduces both reference outputs byte for byte on Windows, macOS and Linux; the
flags the package uses are recorded in `mobcal.fortran` and nowhere else.

## Two things to know before comparing an output with the references

The references were produced with g77, and on Windows a gfortran build differs from them in one
way that is formatting, not physics: the program writes CRLF line endings, because gfortran's
runtime opens the output unit in text mode. A comparison strips end-of-line carriage returns and
should do nothing else. (Until format 604 was corrected, the `mass of ion` line was a second
difference, a `D` exponent where g77 wrote `E`.) A build of the current sources also prints the
atom count in a wider field and the q1st column four times larger than the 2012 outputs do
(Changes, above), so it is compared with `tests/reference/`, not with these files directly.
[docs/mobcal-2012.md](../docs/mobcal-2012.md) gives the commands and lists the differing lines.

The references also echo the name of the input file they were run on, twice, and that name is
`Choline_pop.mfj`. This repository ships the same coordinates as `Choline.mfj`, so a comparison
copies the input to the echoed name before running rather than editing either side.

## The run file

`mobcal.in` as shipped names `Choline.mfj` as input, `choline.out` as output, and seed
`5013489`, which is the seed the references were run at. The 2012 file named
`temp.choline.n2.out` as output for both gases; the name is now neutral (Changes, above). The
seed may be followed on its record by the word `ranlux` or `philox`, naming the random number
generator: RANLUX, the 2012 generator, or Philox4x32-10 (Changes, above); no word is `ranlux`,
and any other word is refused before anything is calculated. A fourth record, `W w`, is read
when present and makes the run one process of a split calculation, as the Changes table
describes; `mobcal run --split W` writes it, and the shipped file does not carry it. The shipped
file, and any run file with three records and no generator word, runs the 2012 calculation,
whereas `mobcal run` writes `philox` after the seed unless it is given `--rng ranlux`, so a
calculation it runs by default draws from Philox and does not reproduce a 2012 output
([docs/random-numbers.md](../docs/random-numbers.md)).

## The run settings

The temperature and the five sampling counts the 2012 programs compiled in are read from
`settings.tab` in the working directory when that file is there, and are the 2012 values when it
is not ([docs/settings.md](../docs/settings.md)). `mobcal run` renders the file into every run
directory beside `parameters.tab`; `mobcal render-parameters` writes both for a directory made
by hand. A program started where there is no `settings.tab` runs the 2012 calculation.

## The element tables

The parameters each program assigns by element are kept as one data file per gas under
`src/mobcal/parameters/`, every number the literal the 2012 source spelled, and `mobcal run`
renders a table from that file, `parameters.tab`, into every run directory beside `mobcal.in`
([docs/parameters.md](../docs/parameters.md)). The programs read that table and nothing else:
started in a directory without one they stop with status 1 and say so. The reader is
`mobcal_ljread.inc`, which both sources include; the test suite reads every row back through it
and holds each to the number the 2012 chain computed, to the last bit. To prepare a directory by
hand the way `mobcal run` does, so that it holds everything a run directory holds, render the
table into it as well:

```
uv run mobcal render-parameters he path/to/run
```
