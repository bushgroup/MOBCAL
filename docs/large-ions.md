# Large ions and long runs

The time a calculation takes grows with the number of atoms of the ion and with its charge, and
the programs reach an ion only up to a limit in each. This page gives those limits and what a run
costs. It then describes the divided run, i.e., one calculation run as several processes, which
reports the result of one process exactly; the rule by which a batch uses the cores; and the
estimate that the window and `mobcal run` print.

## How charged and how large an ion can be

The programs hold an ion of up to 200,000 atoms in up to 100 coordinate sets, and the package
refuses a larger input before the program starts ([A run that
fails](results-folder.md#a-run-that-fails)). The arrays of that bound take about 30 MB in each
process, whatever the size of the ion. Within the bound, the search described here sets a second
limit, on the charge and the extent of the ion.

Before its trajectories, each program finds at each velocity point the largest impact parameter,
b_max, at which a trajectory still deflects the gas. It integrates one trajectory at a time,
with b² rising in steps of ro² (ro = 3.043 Å), until five in a row give 1 − cos χ under the
cutoff of 5 × 10⁻⁴, and it refuses the ion with `ibst greater than 10000` if the walk passes
10,000 steps, b = 304 Å. The 2012 program stopped at 500 steps, b = 68 Å. The refusal comes
after the ion has been read, the projection and hard-sphere pass made, and the potential scanned,
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

## What a run costs

A run spends its time in two parts. Before its first trajectory, the program reads the ion, makes
the projection and hard-sphere pass in helium, and searches for b_max. The trajectory method then
integrates `itn` × `inp` × `imp` trajectories for each coordinate set, 400,000 at the 2012
settings. Both parts grow with the number of atoms. The table gives them as they were measured
for the estimate, on one 36-core workstation with every core busy (Windows 11, MSYS2 gfortran
16.2.0, November 2026); its last column is the first part plus 400,000 times the second.

| Ion | Gas | Before the first trajectory | Each trajectory | One coordinate set at the 2012 settings, as one process |
|---|---|---|---|---|
| choline, 21 atoms, 1+ | helium | 1.8 s | 0.42 ms | 3 min |
| choline, 21 atoms, 1+ | nitrogen | 6.8 s | 10 ms | 67 min |
| protein ion from PDB 2MLT, 433 atoms, 4+ | helium | 36 s | 8.8 ms | 59 min |
| protein ion from PDB 2MLT, 433 atoms, 4+ | nitrogen | 6.0 min | 0.35 s | 39 h |
| protein ion from PDB 1UBQ, 1,236 atoms, 5+ | helium | 1.8 min | 32 ms | 3.6 h |
| protein ion from PDB 1UBQ, 1,236 atoms, 5+ | nitrogen | 18 min | 1.2 s | 5.8 days |
| protein ion from PDB 1BSY, 5,220 atoms, 12+ | helium | 9.2 min | 0.17 s | 19 h |

In nitrogen the time rises with the charge as well as with the size: on the same workstation,
choline with every partial charge multiplied by 12 cost 2.8 times as much for each trajectory as
choline itself.

Beyond the ions of the table, the time in helium grows in proportion to the number of atoms. On
one 40-core workstation (Windows 11, MSYS2 gfortran 16.2.0, October 2026), carbon globules of
1,000 and 10,000 atoms, each divided among 40 processes at the 2012 settings, took 7.9 min and 89
min, of which each process spent 1.3 min and 15 min before its first trajectory. An ion at the
bound of 200,000 atoms was not run. By that proportion it takes more than a day divided among 40
processes, and weeks as one process.

## Divided runs

To shorten a long calculation, the package runs it as several processes. This is a divided run,
and it reports the result of the run as one process exactly: the same cross sections, standard
deviation, and count of failed trajectories, to every printed digit. The window divides runs by
the rule of `--split auto` ([How a batch uses the cores](#how-a-batch-uses-the-cores)), and
`--split W` on the command line divides each run among W processes.

The trajectory method integrates its trajectories in blocks, one block of `imp` trajectories for
each velocity point in each cycle. That is `itn` × `inp` blocks per coordinate set, 400 at the
2012 values and up to 10,000 at the bounds, so `--split` takes any number of processes up to that
product. Each process of a divided run runs the program in a folder of its own inside the run
directory, `w01` to `wW`, with its own copy of the `.mfj`, of the run file, and of the two
rendered files; the program and the record call such a process a worker. A process integrates its
share of the blocks and reaches each with the random number stream in the state the run as one
process would have had ([Why there are two](random-numbers.md#why-there-are-two)). It writes a
file of 76 bytes for each block, which carries the sums of the block and the seed, the generator,
and the six settings it was integrated under.

When every block is written, the program runs once more in the run directory, as the combining
run. It integrates nothing, reads the block files back, and makes the sums, the averages, and the
SUMMARY with the statements that a run as one process uses. Its output is the output of the run,
and it refuses a block from other settings as it refuses one from another seed or generator. The
test suite runs choline in helium at 3 cycles of 7 velocity points divided among four processes,
under both generators, and holds the combined output to that of one process line for line, apart
from the lines a divided run adds; the same holds at the 2012 settings ([What the tests
hold](mobcal-2012.md#what-the-tests-hold)).

The blocks are shared among the processes in one of two ways, `--dealing claimed`, the default,
or `--dealing static`. Claimed lets each process take the next block that no process has taken
yet, so a process that finishes its blocks early keeps working until none is left, and a process
slowed by other work on the computer does not set the time the run takes. Static gives each
process a fixed share of the blocks, every W-th one over an index that mixes the velocity points.
The result is the same under both: the trajectories of a block depend only on its place in the
random stream, not on which process computes them, so the combined output is the output of one
process either way. Under Philox a claiming process takes the slowest blocks first, which is what
keeps the processes finishing together, whereas under RANLUX it can only take them in the order
of the stream.

A divided run fails as a whole when a block is missing. The message names the process that owed
or claimed the block and gives the last line of its output, and the combining run never starts.
A run that fails or is stopped keeps every file its processes wrote. A run that succeeds writes
into its `record.json` what only the folders of its processes held ([The record of a
run](results-folder.md#the-record-of-a-run)) and then removes those folders, the claim files of
the claimed dealing, and the block files, which leaves the eight files of a run as one process.
With `--scratch zip` the block files are packed into `blocks.zip` instead, and unpacked into the
run directory they let the program repeat the combining run there; with `--scratch keep` every
file stays. `mobcal clean` removes the same files from the divided runs already in a folder, and
it lists what it would remove until it is given `--apply`
([`mobcal clean`](command-line.md#mobcal-clean)).

Every process repeats the part of the calculation that precedes its first trajectory, and the
combining run repeats it once more, so a divided run falls short of its number of processes by
that fixed cost and by the unevenness of the shares. On one 40-core workstation, choline at the
2012 settings took 188 s in helium as one process and 103, 47, 28, and 20 s divided among 2, 5,
10, and 20 processes, i.e., it ran 1.8, 4.0, 6.6, and 9.5 times faster. In nitrogen it took 70 min
as one process, 7.9 min divided among ten processes, and 4.4 min divided among twenty, i.e., 8.8
and 15.8 times faster (Windows 11, MSYS2 gfortran 16.2.0, October 2026, under RANLUX with the
static dealing; each helium time is the shorter of two runs, and each divided nitrogen run was
made once; lab record, task 11). Dividing pays most on the longest calculations.

### The output of a divided run

A divided run adds differences of its own to the output of the program, the same ones for any
ion. The combined output carries one line per coordinate set recording the blocks it read, such as

```
 blocks of imp trajectories: integrated    0, read from files  400, empty    0 (worker  0 of 20)
```

together with a blank line, and the diagnostic of a trajectory that failed energy conservation
(`energy not conserved`, two lines and the blank line before them) is printed by the process that
integrated it, in the output of that process, instead of in the combined output. A run that
succeeds copies each of those pairs, with the number of its process, into the `diagnostics` list
of the `split` block of its `record.json` before it removes the folders of its processes. The
count of failed trajectories in the SUMMARY, and every number, are those of the run as one
process.

## How a batch uses the cores

The window, by default, and `mobcal run --split auto` choose how many runs are in flight at once
and how many processes each run is divided among, in one of three modes. The count is of physical
cores, not the logical processors that hyperthreading doubles: on a 40-core workstation, 80 runs
at once gave 1.28 to 1.36 times the trajectories per second of 40, and each run took about half
as long again.

- **Balanced**, the default and `--mode balanced`, runs as many runs at once as keeps each divided
  run at least 70 % efficient, where the efficiency is the time of the run as one process over the
  product of its number of processes and its divided time. On a 40-core workstation that is two
  choline runs at once in helium, each divided among 20 processes, and one at a time in nitrogen
  divided among 40; on 8 cores, one at a time.
- **Finish in order**, `--mode in-order`, runs one at a time, divided among every core it can use,
  so runs complete one after another and **Pause queue** waits only for the run in flight. Cores
  that a run cannot use take a second run.
- **Most throughput**, `--mode throughput`, runs one process per run when there are at least as
  many runs as cores, and otherwise starts every run at once, each divided among its share of the
  cores. It finishes a long batch soonest, and no run finishes before the first wave does.

A batch of no more runs than Balanced would put in flight runs them all at once, as Most
throughput does.

In every mode a run is divided among at most 40 processes, and only when that saves at least a
fifth of its time. A divided run gives the result of one process exactly, so the choice changes
how long a batch takes and never a number. Since every process and the combining run repeat the
part that precedes the first trajectory, a divided run takes at least twice that part. In the
example of the 2000 release, which runs 25 trajectories per block, that part is about a third of
the time of the run as one process, so dividing it saves at most a third
([Reproducing MOBCAL 2000](mobcal-2000.md)). A divided run also cannot finish before its costliest
block of trajectories, the one at the slowest velocity point, which costs 1.8 to 2.9 times the
average block in helium and 3.6 to 4.5 times in nitrogen, so a run is never divided among more
processes than that block lets it use.

## The estimate

Before a batch runs, the window and `mobcal run` say how the batch will run and about how long it
will take. The estimate comes from the timings of the table above ([What a run
costs](#what-a-run-costs)) and, in helium, of carbon globules of 30 to 300 atoms, for ions from 21
to 5,220 atoms in helium and from 21 to 1,236 atoms in nitrogen. It is a guide, not a promise, and
a faster or slower machine scales it. It reads the number of atoms and not the charge, and in
nitrogen it follows the protein ions, so for a singly charged ion of 100 to 1,000 atoms it is 1.25
to 1.65 times the time the trajectories of the run take. When each process spends a minute or
more before its first trajectory, the estimate says how long.
