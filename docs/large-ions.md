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
