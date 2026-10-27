# The window

`mobcal gui` opens a window that runs the same calculations as `mobcal run`, for anyone who
would rather not use a terminal. It takes `.mfj` files, or ORCA outputs and `.xyz` files that it
imports, runs them in helium, nitrogen or both under one of three named methods, shows how long
the batch will take and how far it has got, and gives a table of cross sections with the run
folders, the records and a methods paragraph one click away. Everything the window does, the
command line does too, with the same rules and the same records; this page says where.

```
uv run mobcal gui
```

## Inputs

Add files with Add files, or drop them on the list. An `.mfj` file runs as it is. An ORCA output
or an `.xyz` file is imported as `mobcal import` imports it ([import.md](import.md)), and its row
shows the charges the import will use. When an ORCA output holds CHELPG charges they are
selected; otherwise the row asks for a choice before the batch can run. `uniform`, the net
charge spread evenly over the atoms, is always offered and never selected for you. An `.xyz`
file does not carry the ion's net charge, so its row asks for it. At Run each import is written,
`.mfj` and `.import.json`, into `imported/` in the results folder, so the folder holds the file
each run read.

## Method, Basics and Advanced

Method fills every other field. **Current** is what `mobcal run` does without options: the 2012
element tables and settings, under the Philox4x32-10 random number generator. **MOBCAL 2012** is
the calculation of the 2012 release, the same under RANLUX ([mobcal-2012.md](mobcal-2012.md)).
**MOBCAL 2000** is the calculation of the Jarrold group's 2000 helium release: its element
table, 298 K and 25 trajectories per block, under RANLUX ([mobcal-2000.md](mobcal-2000.md)). It
has no nitrogen form, so choosing nitrogen leaves it. A field changed after a method is chosen
shows the method as *Custom (from MOBCAL 2012)*, say, and the runs record `custom`; changing it
back restores the name. Each method equals the command line its page gives, run for run.

Basics holds the gas (He, N2, or both), the element table (the tables shipped for the gas, or a
file of one's own for one gas, [parameters.md](parameters.md)), the number of seeds per ion, and
the temperature. The first seed is the 2012 seed, 5013489, under every method, and each further
seed is the next integer; with several seeds, each cross section is shown as the mean and sample
standard deviation over them. Advanced holds the generator, the five sampling counts
([settings.md](settings.md)), and how the batch uses the processors.

## How a batch uses the processors, and the estimate

By default the window chooses, by the rule `mobcal run --split auto` uses. With at least as many
runs as processors, each run is one process. With fewer, every run starts at once, and each is
divided among its share of the processors, at most 40, when that saves at least a fifth of its
time. A divided run gives the serial result exactly ([random-numbers.md](random-numbers.md)), so
the choice changes how long a batch takes and never a number. Every process of a divided run
reads the ion and, in helium, repeats the projection and hard-sphere pass before its first
trajectory, so dividing helps little when that part dominates, as in the 2000 release's example
at 25 trajectories per block, and never by much more than 25 times. Unchecking the choice in
Advanced sets the runs at once and the processes per run by hand.

Under the form, the window says how the batch will run and about how long it will take. The
estimate comes from timings of the programs on one workstation for ions from 21 to 10,000 atoms
in helium and from 21 to 300 atoms in nitrogen, so it is a guide, not a promise, and a faster or
slower machine scales it. For a large ion it also says how long each process spends before its
first trajectory.

## The results folder

Choose one results folder for a study. Every batch adds its run directories to it, named for the
input, the gas, the seed and anything that differs from the default method, so that runs of
different methods never share a directory, and `summary.csv` and `summary.json` are rewritten
after each batch to cover every run in the folder. The window remembers the folder for next
time. When some runs of a new batch are already in the folder, complete, the window asks whether
to skip them or run them again. It refuses to run an input whose name another input's run
directory already carries, since that run would be overwritten; rename the input or choose
another folder.

## Running, the queue and stopping

Run starts the batch. While a batch runs, Run adds the form's batch to the queue instead, and the
queue starts its next batch when the running one ends. Queued batches can be reordered by
dragging and removed. The queue is saved as it changes, and batches still queued when the window
closes are offered back when it next opens.

Progress shows the runs done of the batch, the time each running run has taken, and, for a
divided run, how many of its blocks of trajectories are written, against the estimate. Stop asks,
then ends every process of the running batch. Runs already complete keep their results; the
stopped ones keep their directories, marked stopped in the summary. Closing the window while a
batch runs asks the same question and stops the batch.

## Results

The table has one row per ion and gas: the trajectory-method cross section, and in helium the
projection-approximation and exact hard-sphere values, in Å², with mean ± s.d. over seeds; the
status, and for a failed run the program's reason in the status's tooltip; and the time. Copy
puts the table on the clipboard, tab-separated, and Save CSV writes it to a file. Show in folder
opens the selected row's run directory, and Open output its `mobcal.out`. Copy methods text puts
a paragraph on the clipboard that describes the completed runs of the batch from their records,
the program and version, the method, gas, element table, temperature, trajectory counts,
generator and seeds, with the papers to cite. `mobcal methods-text FOLDER` prints the same for
any runs.
