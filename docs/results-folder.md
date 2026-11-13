# The results folder

Every calculation leaves a run directory in the results folder, i.e., the folder chosen
in the window or named by `--out` on the command line. This page describes the record
the package writes into each run directory, `record.json`.

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
