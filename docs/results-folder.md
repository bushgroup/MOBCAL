# The results folder

Every calculation leaves a run directory in the results folder, i.e., the folder chosen
in the window or named by `--out` on the command line. This page describes how a run
directory is named and the record the package writes into it, `record.json`.

## The name of a run directory

Run
directories are named for the input, the gas, the seed, the generator when it is RANLUX, the
table when it is not the 2012 table for the gas, and each setting that differs from 2012
(`choline-he-5013486-ranlux-lj2000-t298-imp25`), never for the method, so the same calculation
lands in the same directory whichever way it was asked for.

The name of the run directory carries each value that differs from 2012, in the order
temperature, `imp`, `itn`, `inp`, `inum`, `inor`, so two
runs of one input and seed at different settings never share a directory:
`choline-he-5013489-ranlux-t298-imp25`, or, with the 2000 element table as well,
`choline-he-5013489-ranlux-lj2000-t298-imp25`.

## The record of a run

When a run ends, whether it finished or failed, the package writes `record.json` into its
directory: the package version; the program, its path, and the record `mobcal build` wrote when
it compiled it (compiler, flags, source hash); the input file, the name it was copied to, its
SHA-256, its atom count and its number of coordinate sets; the seed, the random number generator
and, for a split run, the number of processes; the parameter table, its path (`null` for a table
of your own that a method carried), name, format and SHA-256, whether it is the shipped one,
and the name of the rendered table; the run settings, the temperature and the five
sampling counts, with where they came from ([The run settings](settings.md)); the start time, the
wall time, the exit status,
the verdict and its message; the cross sections and the values for each coordinate set; and the
names of the output and console files. A split run that got as far as its combining run adds
`split`, what its worker directories alone hold: for each worker the start and end in seconds
after the start time, the blocks it integrated and its exit status, under the claimed dealing the
worker that integrated each block (one string per coordinate set of worker numbers, block 1
first), and each energy-conservation diagnostic a worker printed. Every split run adds
`scratch`, which names what the run kept of the worker files (`delete`, `zip` or `keep`; a run
that fails keeps everything) and, once they are removed, how many of each kind went, any file
that could not be removed, and the seconds the removal took. `mobcal clean` adds `split` to the
record of an older run that lacks it, and `cleaned`, a list of what each pass removed. The output
file of the program is unchanged by any of this, so it still compares byte for byte with the 2012
references. `summary.json` names the table each run used and its SHA-256 as well, and both
summary files name the random number generator each run used in their `rng` column
([Random numbers](random-numbers.md)).

The record does not depend on the method file to say what the method was ([What a run
records](methods.md#what-a-run-records)): the gas, the generator, the
seed, the element table by name and SHA-256 (with its path when the run read a TOML file)
and the six settings are each in it, so a run stays described after its method file is
moved, edited or deleted.

`record.json` in each run directory and the per-run entries of `summary.json` carry a
`settings` block: the six values, whether they are the 2012 ones, the values set over the 2012
ones, by the method or singly, and the name of the rendered file.
`summary.csv` carries the six values as columns after the method.
