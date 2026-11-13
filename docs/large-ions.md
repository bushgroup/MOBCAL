# Large ions and long runs

The time a calculation takes grows with the number of atoms of the ion and with its
charge, and the programs reach an ion only up to a limit in each. This page gives those
limits and describes the divided run, i.e., one calculation run as several processes,
which reports the serial result exactly.

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

## Divided runs

A calculation split across processes (by the choice the window makes,
[The window](window.md#how-a-batch-uses-the-cores-and-the-estimate), or by `--split`) deals
`itn` × `inp` blocks per coordinate set among its workers, 400 at the 2012 values and up to
10,000 at the bounds, so `--split` takes any worker count up to that product. Each block file
carries the settings its block was integrated under, after the seed and the generator, and the
combining run refuses a block from other settings as it refuses one from another seed or
generator. The test suite runs choline in helium at 3 cycles of 7 velocity points split four
ways, under both generators, and holds the combined output to the serial one line for line.

On one 40-core workstation, choline in nitrogen at the 2012 settings took 70 min as one process,
7.9 min divided among ten processes, and 4.4 min divided among twenty (Windows 11, MSYS2
gfortran 16.2.0, October 2026, under RANLUX with the static dealing, one run each; lab record,
task 11).

The blocks are shared among the workers in one of two ways, `--dealing claimed`, the default,
or `--dealing static`. Claimed lets each worker take the next block that no worker has taken
yet, so a worker that finishes its blocks early keeps working until none is left, and a worker
slowed by other work on the computer does not set the time the run takes. Static gives each worker a
fixed share of the blocks, every W-th one over an index that mixes the velocity points. The result is the same
under both: the trajectories of a block depend only on its place in the random stream, not on which
process computes them, so the combined output is the serial output either way. Under Philox a
claiming worker takes the slowest blocks first, which is what keeps the workers finishing
together; under RANLUX it can only take them in the order of the stream.

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
of the `split` block of its `record.json` before it removes the worker directories (`--scratch
keep` leaves them, `w01` to `wW`). The count of failed trajectories in the SUMMARY, and every
number, are those of the run as one process.

## How a batch uses the cores

By default the window and `mobcal run --split auto` choose how many runs are in flight at once
and how many processes each run is divided among, in one of three modes. The count is of physical
cores, not the logical processors that hyperthreading doubles: on a 40-core workstation, 80 runs
at once gave 1.28 to 1.36 times the trajectories per second of 40, and each run took about half
as long again.

- **Balanced**, the default, runs as many runs at once as keeps each divided run at least 70 %
  efficient, where efficiency is the time of the run as one process over the processes it uses times
  its divided time. On a 40-core workstation that is two choline runs at once in helium, each
  across 20 processes, and one at a time in nitrogen across 40; on 8 cores, one at a time.
- **Finish in order** runs one at a time, divided among every core it can use, so runs complete
  one after another and Pause queue waits only for the run in flight. Cores a run cannot use
  take a second run.
- **Most throughput** runs one process per run when there are at least as many runs as cores,
  and otherwise starts every run at once, each divided among its share of the cores. It
  finishes a long batch soonest, and no run finishes before the first wave does.

A batch of no more runs than Balanced would put in flight runs them all at once, as Most
throughput does.

In every mode a run is divided among at most 40 processes, and only when that saves at least a
fifth of its time. A divided run gives the serial result exactly ([Random numbers](random-numbers.md)),
so the choice changes how long a batch takes and never a number. Every process of a divided run
reads the ion and, in helium, repeats the projection and hard-sphere pass before its first
trajectory, so dividing helps little when that part dominates, as in the example of the 2000
release at 25 trajectories per block. A divided run also cannot finish before its costliest block of
trajectories, the one at the slowest velocity point, which costs 1.8 to 2.9 times the average
block in helium and 3.6 to 4.5 times in nitrogen, so a run is never divided among more processes
than that block lets it use.

## The estimate

Before a batch runs, the window and `mobcal run` say how the batch will run and about how long it
will take. The estimate comes from timings of the programs on one 36-core workstation with every
core busy, for ions from 21 to 5,220 atoms in helium and from 21 to 1,236 atoms in nitrogen,
protein ions among them, so it is a guide, not a promise, and a faster or slower machine scales
it. It reads the number of atoms and not the charge. In nitrogen a multiply charged protein ion
takes much longer than a singly charged ion of similar size, and the estimate follows the protein
ions, so for a singly charged ion of 100 to 1,000 atoms it is 1.25 to 1.65 times the time the
trajectories of the run take. When each process spends a minute or more before its first
trajectory, the estimate says how long.
