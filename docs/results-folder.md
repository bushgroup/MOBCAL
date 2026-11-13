# The results folder

The results folder holds a study. Every calculation leaves a run directory in it, and two summary
files, `summary.csv` and `summary.json`, cover every run the folder holds. It is the folder
chosen in the window or named by `--out` on the command line, `runs` in the current folder by
default. This page describes how a run directory is named, the files in it, the record of a run,
how a failed run is reported, and the summary files.

## The name of a run directory

A run directory is named for the calculation, e.g., `Choline-he-5013489`: the name of the input
without its extension, the gas (`he` or `n2`), and the seed. Three further parts follow, in this
order, each only when it applies:

- `-ranlux`, when the generator is RANLUX;
- the element table, when it is not the 2012 table of the gas: `-lj2000` for the 2000 helium
  table, or `-lj` and the first eight digits of the SHA-256 of any other table;
- each run setting that differs from its 2012 value, in the order temperature, `imp`, `itn`,
  `inp`, `inum`, `inor`, as in `-t298-imp25`.

A run of `Choline.mfj` under `--method 2000-he` at the seed 5013486 therefore lands in
`Choline-he-5013486-ranlux-lj2000-t298-imp25`. The name never carries the method, so the same
calculation lands in the same directory whichever way it was asked for, and two runs of one input
and seed that differ in the generator, the table, or a setting never share a directory.

Two inputs of the same name would share a directory. To keep one from replacing the other,
`mobcal run` compares the SHA-256 of each input with the one in the record of the directory its
run would take, and when they differ it stops before any run starts, with exit status 2 and a
message to rename the input or choose another folder. The window refuses to add such a batch. A
run whose directory already holds a run of the same input is run again and replaces it. With
`--skip-done`, the runs that the folder already holds complete are left out instead, and the
window asks which of the two to do ([The results folder](window.md#the-results-folder)).

## The files of a run directory

A run as one process leaves eight files in its directory, here for `Choline.mfj`:

| File | Contents |
|---|---|
| `Choline.mfj` | The input as the program read it. A `.mfj` is copied byte for byte. For an ion file, `X.ion.json`, this is `X.mfj`, written from the ion file for the element table of the run ([Writing the `.mfj`](ion-file.md#writing-the-mfj)). An input whose name is longer than the 30 characters the program reads is copied as `input.mfj`. |
| `mobcal.in` | The run file the program read: the names of the input and the output, the seed, and the generator. |
| `parameters.tab` | The element table as rendered for the program ([The rendered table](parameters.md#the-rendered-table)). |
| `settings.tab` | The six run settings as rendered for the program ([The rendered file](settings.md#the-rendered-file)). |
| `mobcal.out` | The output of the program. |
| `stdout.log` | What the program printed to the console: the settings and the element table it read, and any message of the Fortran runtime. |
| `record.json` | The record of the run, described below. |
| `NAME.result.json` | The result file, where NAME is the name of the run directory ([The result file](result-file.md)). |

The package writes nothing into `mobcal.out`, which is the output of the program as the program
wrote it. The directory of a run as one process is a complete record of the run: the program
started again in that directory repeats the calculation.

A divided run that succeeds leaves the same eight files, with the `mobcal.in` of its combining
run. What its processes wrote besides is removed, packed into `blocks.zip`, or kept, as
`--scratch` says ([Divided runs](large-ions.md#divided-runs)).

## The record of a run

When a run ends, whether it finished, failed, or was stopped, the package writes `record.json`
into its directory. The record says what ran, on which input, under which method, and what came
of it. It does not depend on the method file to say what the method was ([What a run
records](methods.md#what-a-run-records)): the gas, the generator, the seed, the element table by
name and SHA-256, and the six settings are each in it, so a run stays described after its method
file is moved, edited, or deleted.

| Key | Contents |
|---|---|
| `mobcal_version` | The version of the package. |
| `name` | The name of the run directory. |
| `binary` | The gas, the path of the program, the command, and `build`, the entry that `mobcal build` wrote for the program when it compiled it: the source and the include files with their SHA-256, the SHA-256 of the executable, the compiler, the flags, the platform, the commit, and the time. `build` is `null` when no `build.json` lies beside the program. |
| `input` | The path of the input as given, the name it was copied under, its SHA-256, its number of atoms, and its number of coordinate sets. For an ion file, also the format, the SHA-256 of the `.mfj` written from it, the charge mode, and what the import record of the ion file says of the source of its charges. |
| `mobcal_in` | The seed, the generator, and for a divided run the number of processes (`split`) and the dealing; these two are `null` for a run as one process. |
| `method`, `method_file` | The key of a shipped method, the name of a method file, or `custom`; and for a method file, its path and SHA-256. |
| `parameters` | The element table: its path (`null` for a table that a method file carried), its name, format, gas, and SHA-256, whether it is a shipped table, and the name of the rendered table. |
| `settings` | The six values, whether they are the 2012 ones (`default`), the values set over the 2012 ones, by the method or singly (`source`), and the name of the rendered file. |
| `started`, `seconds` | The time the run started, to the second with its offset from UTC, and the seconds the program took. For a divided run the seconds run from the start of its first process to the end of its combining run. |
| `returncode`, `status`, `message` | The exit status of the program; `ok`, `failed`, or `stopped`; and for a run that is not `ok`, the reason. |
| `cross_sections`, `conformers` | The cross sections in Å², as the mean over the coordinate sets that the program reports, and the values for each coordinate set. Both are empty for a run that is not `ok`. |
| `output`, `console_log` | The names of the output file and the console file. |
| `platform`, `python` | The operating system and the version of Python. |

A divided run adds two blocks to its record. A run that got as far as its combining run has
`split`, which holds what only the folders of its processes held. For each process, `workers`
gives its number, its start and its end in seconds after `started`, the number of blocks it
integrated, its exit status, and any line of its console file that the console file of the run
lacks. Under the claimed dealing, `claims` gives for each coordinate set the numbers of the
processes that integrated blocks 1 to `itn` × `inp`, in that order. `diagnostics` gives each
energy-conservation diagnostic that a process printed, with the number of the process ([The
output of a divided run](large-ions.md#the-output-of-a-divided-run)).

Every divided run has `scratch`, which names what the run kept of the files of its processes:
`delete`, `zip`, or `keep`, and always `keep` for a run that failed or was stopped. Once the
files are removed, the block also says how many folders, claim files, and block files went, which
files could not be removed, and the seconds the removal took. `mobcal clean` appends to a list,
`cleaned`, what each of its passes removed ([`mobcal clean`](command-line.md#mobcal-clean)).

## A run that fails

A run that did not finish is reported as failed, never as a number. The program exits with status
1 when it refuses its input, and a completed calculation ends its output in a SUMMARY block. A
run whose program exits with a status other than 0, or whose output lacks that block, is
`failed`, and its message is the last line the program wrote. For an atom whose mass matches no
row of the element table, the message is

```
exit 1: type not defined for atom number      1
```

Such a run keeps its directory, and its record and its result file each carry the status
`failed` and no cross section.

The package refuses some inputs itself, before the program starts, and such a run is `failed`
with no run directory. Its message begins `input refused:`, `cannot read input:`, or
`parameters refused:`. A `.mfj` whose units line is not exactly `ang` or `au`, or that holds
more than 200,000 atoms or more than 100 coordinate sets, is refused in this way, as is an ion
file with an element that the table lacks ([Writing the `.mfj`](ion-file.md#writing-the-mfj)).
An ion too highly charged or too extended is refused by the program itself, minutes to hours into
its run ([How charged and how large an ion can
be](large-ions.md#how-charged-and-how-large-an-ion-can-be)).

A run that the window ended before it finished, because its batch was removed or the window was
closed, is `stopped`. It keeps its directory and its record, and it starts again from its first
trajectory when its batch runs again ([Running, the queue and
stopping](window.md#running-the-queue-and-stopping)). `mobcal run` exits with status 1 if any run
failed.

## The summary files

After each batch, `mobcal run` and the window rewrite `summary.csv` and `summary.json` in the
results folder. The two files cover every run the folder holds, in the order of their names: the
runs of the batch, and every other run directory by its record. A later batch therefore adds its
runs beside the earlier ones, and one results folder holds a study.

`summary.csv` has one row for each run:

| Column | Contents |
|---|---|
| `name` | The name of the run directory. |
| `input` | The path of the input as given. |
| `gas` | `he` or `n2`. |
| `seed` | The seed. |
| `rng` | The generator, `philox` or `ranlux`. |
| `method` | The method, as in the record. |
| `temperature`, `imp`, `itn`, `inp`, `inum`, `inor` | The six run settings. |
| `status` | `ok`, `failed`, or `stopped`. |
| `PA`, `EHS`, `TM` | The cross sections in Å²: for an input of several coordinate sets, the mean over the sets, as the program reports it. A cell is empty where the program reports no value, as for `PA` and `EHS` in nitrogen and for a run that is not `ok`. |
| `sets` | The number of coordinate sets of a run that is `ok`. |
| `seconds` | The seconds the program took. |
| `output` | The path of the output file. |
| `message` | For a run that is not `ok`, the reason. |

`summary.json` holds the same runs under `runs`. Each entry carries what the row carries and, in
addition, the values for each coordinate set (`conformers`), the number of processes of a divided
run (`split`), the exit status, the `settings` block of the record, the method file, and the name
and SHA-256 of the element table. Above the runs, the file gives the version of the package, the
date, the platform, and the version of Python, and of the batch that wrote it, the names of its
runs (`batch`), the number in flight at once (`workers`), and the seconds it took.

A run without a run directory, i.e., one that the package refused before the program started, has
no record, so it is in the summary files that its own batch writes and in none written later.
A run that a paused batch has not reached adds no row to either file.

`mobcal methods-text` reads the records of a results folder and prints a methods paragraph for
its runs ([`mobcal methods-text`](command-line.md#mobcal-methods-text)).
