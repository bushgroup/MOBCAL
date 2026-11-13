# Random numbers

The trajectory method averages over collisions whose starting conditions are drawn at random.
For each trajectory the program draws three numbers that orient the ion and one that sets the
impact parameter, so the trajectory method takes 1.6 million draws per coordinate set at the
2012 settings, 400 blocks of 1,000 trajectories. The cross section the program reports therefore
depends on the random numbers as well as on the ion, and two runs that differ only in their seed
report cross sections that differ by a few tenths of a percent. This page describes the two
generators the program can draw from, how a run chooses one, the seed, and how the cross
sections under the two generators compare.

## The two generators

RANLUX is the generator of the 2012 release: the subtract-with-borrow generator of Lüscher in
the implementation of F. James, at luxury level 3. Every number MOBCAL 2012 published was computed
with it. It produces its numbers in sequence, so the state after n draws can be reached only by
drawing n times. Its uniforms lie on a grid of 2^−24, apart from those below 2^−12, to which the
generator adds lower bits.

Philox4x32-10 is a counter-based generator (Salmon, Moraes, Dror, and Shaw, *Proceedings of
SC11*, 2011), implemented here as the Random123 library defines it; the test suite holds the
implementation in the program to the known-answer vectors of the library. Draw n is a function of
the seed and n alone, i.e., the program can move to any point in the stream without drawing the
numbers before it. Its uniforms resolve 2^−52, and none is exactly 0 or 1.

## Why there are two

A divided run, i.e., one calculation run as several processes
([Divided runs](large-ions.md#divided-runs)), gives each process a share of the blocks of
trajectories, and each process must reach its own blocks with the random number stream in the
state the serial run would have reached. Under RANLUX a process gets there by drawing through
every block that is not its own, whereas under Philox it moves the draw count past them in one
step. On one 40-core workstation (Windows 11, MSYS2 gfortran 16.2.0, October 2026) the
draw-through cost each process about 2 s, 23 % of the 8.8 s that a process took when choline in
helium, 185 s as one process, was divided among 40, and the run that combines the blocks pays it
once more. The saving is not the reason for the second generator. Under Philox a divided run
equals the serial run by construction, for any number of processes, whereas under RANLUX it does
so because the draw-through repeats the serial stream exactly, which the test suite has to check.

## Choosing one

Every method names its generator ([Methods](methods.md)), and in the window **Generator** under
Advanced shows it and changes it. `mobcal run` draws from Philox unless the method or an option
says otherwise:

```
mobcal run choline.mfj --rng ranlux
```

runs under RANLUX. The run file the program reads, `mobcal.in`, carries the generator after the
seed, `5013489 philox`. A run file without the word is a RANLUX run, as every run file was in
2012, and the shipped one carries no word. The run directory of a RANLUX run that `mobcal run`
makes carries `-ranlux` after the seed, so the same seed under both generators can share a
results folder ([The results folder](results-folder.md)), and `record.json`, `summary.csv`, and
`summary.json` name the generator of every run.

## The seed

The seed starts the random number stream, so the ion, the method, and the seed together decide
every digit a run reports. A seed is a positive integer up to 2,147,483,647. Each run has one
seed, which the name of its run directory carries and which `record.json`, `summary.csv`,
`summary.json`, and the result file record.

Without another choice a run starts at 5013489, the seed of the run file that shipped with the
2012 release and of its reference outputs, called the 2012 seed on these pages. A method file may
carry a seed of its own, and a run of that method starts there ([Method
files](methods.md#method-files)), whereas the shipped methods carry none. The seed is not one of
the fields that identify a method, so a run at another seed is still a run of its method.

From a terminal, `--seeds` takes a list of seeds, which wins over the seed of the method, and
`mobcal run` makes one run of each ion for each seed:

```
mobcal run choline.mfj --seeds 5013489,5013490,5013491
```

In the window, **Seeds per ion** sets how many seeds each ion runs at, from 1 to 1,000. The first
is the seed of the method, which the field then shows (", from seed 42"), or the 2012 seed, and
each further seed is the next integer.

To find how far a cross section depends on its seed, run several seeds. The window then shows
each cross section as the mean and the sample standard deviation over the seeds, and the methods
paragraph states the number of seeds. For choline in helium the standard deviation of the
trajectory-method cross section over 40 seeds is 0.16 Å², 0.3 % of the cross section
([How the two compare](#how-the-two-compare)).

## How the two compare

To test whether Philox gives the same cross sections as RANLUX, i.e., the same distribution over
seeds rather than the same digits, we ran the choline input under both generators, each run
divided among 40 processes: 40 seeds per generator in helium and 10 in nitrogen, on one 40-core
workstation (Windows 11, MSYS2 gfortran 16.2.0, October 2026; lab record, task 18). In helium the
means differ by +0.017 Å² (projection approximation), +0.039 Å² (exact hard spheres), and −0.044
Å² (trajectory method), at most 1.7 times their combined standard error, and the standard
deviations over seeds agree to within 5 %: 0.16 Å² for the trajectory-method value under either
generator, 0.3 % of the cross section. In nitrogen the trajectory-method means differ by −0.10
Å², 0.8 times their combined standard error, and no trajectory failed energy conservation in any
run under either generator. The two generators therefore give cross sections that are
interchangeable at the precision a single calculation has. Note that this comparison used one
ion, choline, a 21-atom cation.

## Reproducing a published number

A cross section published from MOBCAL 2012 reproduces only under RANLUX and at the seed it was
computed with, 5013489 for the choline references and for any calculation run from the shipped
run file. The same input under Philox reports cross sections that differ in their last digits,
as a run at another seed would: the two generators produce different streams, so no line of the
output that depends on the random numbers matches between them. The regression tests and
`mobcal self-check --choline` run under RANLUX for this reason. [Reproducing MOBCAL
2012](mobcal-2012.md) gives the command for each gas and compares the outputs with the 2012
references line by line.
