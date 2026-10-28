# Random numbers

The trajectory method averages over collisions whose starting conditions are drawn at random.
For each trajectory the program draws three numbers that orient the ion and one that sets the
impact parameter, so one coordinate set of the shipped calculation, 400 blocks of 1,000
trajectories, takes 1.6 million draws. The cross section the program reports therefore depends
on the random numbers as well as on the ion, and two runs that differ only in their seed report
cross sections that differ by a few tenths of a percent. The program can draw these numbers
from either of two generators, and the run file names which.

## The two generators

RANLUX is the generator of the 2012 release: Lüscher's subtract-with-borrow generator in
F. James's implementation, at luxury level 3. Every number MOBCAL 2012 published was computed
with it. It produces its numbers in sequence, so the state after n draws can be reached only by
drawing n times, and its uniforms lie on a grid of 2^−24.

Philox4x32-10 is a counter-based generator (Salmon, Moraes, Dror and Shaw, *Proceedings of
SC11*, 2011), implemented here as the Random123 library defines it; the test suite holds the
program's implementation to the library's known-answer vectors. Draw n is a function of the
seed and n alone, i.e., the program can move to any point in the stream without drawing the
numbers before it. Its uniforms resolve 2^−52, and none is exactly 0 or 1.

## Why there are two

A calculation split across processes (the [README](../README.md#running-calculations)) gives
each process a share of the trajectory blocks, and each process must reach its own blocks with
the random number stream in the state the serial run would have reached. Under RANLUX a process
gets there by drawing through every block that is not its own, whereas under Philox it moves
the draw count past them in one step. On one workstation (Windows 11, MSYS2 gfortran 16.2.0)
the draw-through cost each process about 2 s of the 185 s that choline takes in helium, 23 % of
a process's time when that calculation was split 40 ways, and the combining run pays it once
more. The saving is not the reason for the second generator. Under Philox a split run equals
the serial run by construction, for any number of processes, whereas under RANLUX it does so
because the draw-through repeats the serial stream exactly, which the test suite has to check.

## Choosing one

`mobcal run` draws from Philox unless asked otherwise:

```
uv run mobcal run choline.mfj --rng ranlux
```

runs under RANLUX. The run file the program reads, `mobcal.in`, carries the generator after the
seed, `5013489 philox`. A run file without the word is a RANLUX run, as every run file was in
2012, and the shipped one carries no word. The run directory of a RANLUX run that `mobcal run`
makes ends in `-ranlux`, so the same seed under both generators can share an output folder, and
`record.json`, `summary.csv` and `summary.json` name the generator of every run.

## How the two compare

To test whether Philox gives the same cross sections as RANLUX, i.e., the same distribution
over seeds rather than the same digits, we ran the choline input under both generators, each
run split across 40 processes: 40 seeds per generator in helium and 10 in nitrogen, on one
workstation (Windows 11, MSYS2 gfortran 16.2.0, October 2026; lab record, task 18). In helium
the means differ by +0.017 Å² (projection approximation), +0.039 Å² (exact hard spheres) and
−0.044 Å² (trajectory method), at most 1.7 times their combined standard error, and the
standard deviations over seeds agree to within 5 %: 0.16 Å² for the trajectory-method value
under either generator, 0.3 % of the cross section. In nitrogen the trajectory-method means
differ by −0.10 Å², 0.8 times their combined standard error, and no trajectory failed energy
conservation in any run under either generator. The two generators therefore give cross sections that are interchangeable
at the precision a single calculation has. Note that this comparison used one ion, choline, a
21-atom cation.

## Reproducing a published number

A cross section published from MOBCAL 2012 reproduces only under RANLUX and at the seed it was
computed with, 5013489 for the choline references and for any calculation run from the shipped
run file:

```
uv run mobcal run Choline.mfj --method 2012-he
```

reports 61.075, 63.473 and 55.402 Å² by the projection approximation, exact hard spheres and the
trajectory method, the 2012 values to every printed digit. The same input under Philox reports
cross sections that differ in their last digits, as a run at another seed would: the two
generators produce different streams, so no line of the output that depends on the random
numbers matches between them. The regression tests and `mobcal self-check --choline` run under
RANLUX for this reason. [mobcal-2012.md](mobcal-2012.md) gives the command for each gas and
compares the outputs with the 2012 references line by line.
