# The window

The window runs the same calculations as the `mobcal` command, for anyone who would rather not use a
terminal. It takes ion files and `.mfj` files, or ORCA and Gaussian outputs and `.xyz` files that
it imports, runs
them in helium or nitrogen under one of five shipped methods or a method file of one's own, shows
how long the batch will take and how far it has got, and gives a table of cross sections with the
run folders, the records and a methods paragraph one click away. Everything the window does, the
command line does too, with the same rules and the same records; this page says where, and [The
command line](command-line.md) lists every command and option. Every control carries a tooltip that
says what it sets, in the words the command line's help uses for the same option.

To open the window, choose **MOBCAL** in the Start menu on Windows, or open `MOBCAL.app` on
macOS; on Linux, and from a terminal on any platform, run

```
mobcal gui
```

[Installing MOBCAL](install.md) says where each package puts the program.

## Inputs

Add files with Add files, or drop them on the list. An ion file, `.ion.json` ([The ion
file](ion-file.md)), or an `.mfj` file runs as it is, and its row shows what the file makes of the
charges, read-only: the fifth line of an `.mfj`, the `charge_mode` of an ion file, which keeps the
line it was read from. Charges names the mode: `calc` reads
"from file", `equal` "uniform", `none` "none". Net charge gives the charge the calculation uses,
and the two gases read `equal` differently: helium gives the ion +1 whatever the file's fifth
column sums to, nitrogen gives it that sum, so an `equal` row reads "+1 He / +2 N2" for a column
summing to 2. A `calc` row shows the column's sum and a `none` row shows 0. A sum within 0.01 of an
integer is shown as the integer; the tooltip gives it to six decimals, and for a file of several
sets lists each one's when they differ. The nitrogen program reads a charge on every atom line
whatever the mode, so a file with four columns, or an ion file with an atom that has no charge,
is refused when the batch's gas is nitrogen, and its row says so ([Reproducing MOBCAL
2012](mobcal-2012.md)). An `.mfj` in MobCal-MPI's nine-column layout is refused, as `mobcal run`
refuses it; `mobcal import` reads it into an ion file, which the window runs. An ORCA or
Gaussian output or an `.xyz` file is imported as `mobcal import` imports it ([Importing a structure
and its charges](import.md)), and its row shows the charges the import will use. When an output
holds an ESP fit it is selected, the Merz-Kollman fit (`mk`, the scheme of the 2012 choline charges)
before CHELPG; otherwise the row asks for a choice before the batch can run. `uniform`, the net
charge spread evenly over the atoms, is always offered and never selected for you. An `.xyz` file
does not carry the ion's net charge, so its row asks for it. At Add batch each import is written
as an ion file into `imported/` in the results folder, and the batch runs that file, so the folder
holds the file each run read and the record of where its charges came from; the `.mfj` the program
reads is written into each run's folder. An ion file already in `imported/` that holds the same ion
is left as it is, so the runs made from it before are still found complete.

## Method, Basics and Advanced

Method fills every other field, the gas among them ([Methods](methods.md)). The list holds the five
shipped methods, **MOBCAL 2012 (He)** and **(N2)**, the calculation of the 2012 release under RANLUX
([Reproducing MOBCAL 2012](mobcal-2012.md)); **MOBCAL 2012 with Philox (He)** and **(N2)**, the same
tables and settings under Philox4x32-10, the helium one chosen at the first launch; and **MOBCAL
2000 (He)**, the calculation of the Jarrold group's 2000 helium release ([Reproducing MOBCAL
2000](mobcal-2000.md)). Below them are the method files loaded or saved, by name. Holding the
pointer over a method shows its description, when it has one. A field changed
after a method is chosen shows the method as *Custom (from MOBCAL 2012 (He))*, say, and the runs
record `custom`; changing it back restores the name, and fields that make another method show that
one. Changing the gas of MOBCAL 2012 (He) to N2 shows MOBCAL 2012 (N2), whereas MOBCAL 2000 (He),
which has no nitrogen form, becomes Custom. Each shipped method equals the command line its page
gives, run for run.

File, Save method… writes the gas, element table, generator and six settings the form holds to
a method file, `NAME.method.json`, asks for the name the list will show, and adds the file to the
list. The file carries the element table whole, a table of one's own included, so it runs on
another computer without the table's TOML file ([The element table in a
method](methods.md#the-element-table-in-a-method)). File, Load method… adds a file saved here or
elsewhere and fills the fields from it, and a table of one's own that the file carries shows in
the Element table field as its name followed by *(in the method)*. The list remembers its files
at the next launch, and removes one that has been moved, deleted or edited since it was added, or
that no longer loads, such as a TOML method file saved by version 2.0, with a message that says
which and why ([Methods](methods.md#method-files)). `mobcal run --method PATH` runs the same file.

Basics holds the gas (He or N2), the element table (the tables shipped for the gas, or a file of
one's own for the gas, [The element tables](parameters.md)), the number of seeds per ion, and
the temperature. The first seed is the method's seed when its file carries one, which Seeds per
ion then shows (", from seed 42"), and the 2012 seed, 5013489, otherwise; each further seed is
the next integer; with several seeds, each cross section is shown as the mean and sample
standard deviation over them. Advanced holds the generator, the five sampling counts
([The run settings](settings.md)), and how the batch uses the processors.

## How a batch uses the processors, and the estimate

By default the window chooses, by the rule `mobcal run --split auto` uses, in one of three modes
chosen beside the check box in Advanced. The window counts physical cores, not the logical
processors that hyperthreading doubles: on a 40-core workstation, 80 runs at once gave 1.28 to
1.36 times the trajectories per second of 40, and each run took about half as long again.

- **Balanced**, the default, runs as many runs at once as keeps each divided run at least 70%
  efficient, where efficiency is the run's time as one process over the processes it uses times
  its divided time. On a 40-core workstation that is three choline runs at once in helium, each
  across 13 processes, and one at a time in nitrogen across 40; on 8 cores, one at a time.
- **Finish in order** runs one at a time, divided among every core it can use, so runs complete
  one after another and Pause queue waits only for the run in flight. Cores a run cannot use
  take a second run.
- **Most throughput** runs one process per run when there are at least as many runs as cores,
  and otherwise starts every run at once, each divided among its share of the cores. It
  finishes a long batch soonest, and no run finishes before the first wave does.

A batch with fewer runs than Balanced would put in flight runs them all at once, as Most
throughput does. The mode is a preference of the window, kept for the next launch, and a batch
waiting in the queue starts under the mode chosen when it starts.

In every mode a run is divided among at most 40 processes, and only when that saves at least a
fifth of its time. A divided run gives the serial result exactly ([Random numbers](random-numbers.md)),
so the choice changes how long a batch takes and never a number. Every process of a divided run
reads the ion and, in helium, repeats the projection and hard-sphere pass before its first
trajectory, so dividing helps little when that part dominates, as in the 2000 release's example
at 25 trajectories per block. A divided run also cannot finish before its costliest block of
trajectories, the one at the slowest velocity point, which costs two to four and a half times
the average block, so a run is never divided among more processes than that block lets it
use. Unchecking the choice in Advanced sets the runs at once and the processes per run by hand.

Under the form, the window says how the batch will run and about how long it will take. The
estimate comes from timings of the programs on one workstation for ions from 21 to 10,000 atoms
in helium and from 21 to 300 atoms in nitrogen, so it is a guide, not a promise, and a faster or
slower machine scales it. For a large ion it also says how long each process spends before its
first trajectory.

## The results folder

Choose one results folder for a study. Every batch adds its run directories to it, named for the
input, the gas, the seed and anything that differs from the default method, so that runs of
different methods never share a directory and both gases of a study can share a folder, and
`summary.csv` and `summary.json` are rewritten after each batch to cover every run in the folder.
The window remembers the folder for next time. When some runs of a new batch are already in the
folder, complete, the window asks whether to skip them or run them again. It refuses to run an input
whose name another input's run directory already carries, since that run would be overwritten;
rename the input or choose another folder.

Each run directory holds the run's result file, `NAME.result.json`, which carries both inputs
and every value the program reported ([The result file](result-file.md)). *Keep the ion in each
result file*, below the folder, is checked by default, and each result file then carries the
ion's geometries and charges. To keep result files small when the geometries are kept
elsewhere, as for thousands of frames of a molecular dynamics trajectory, uncheck it, and each
result file names the ion file by its name and SHA-256 alone. A batch keeps the choice it was
added with, in the queue and across launches.

## Running, the queue and stopping

Every batch control is a button in the Queue box: Add batch, a second button that starts, pauses
and resumes the queue, and Remove batch. None has a menu entry or a keyboard shortcut. Add batch
puts the form's batch at the end of the queue and never starts it, whether or not a batch is
running. The second button reads Start queue when batches are waiting and none has started, and
starts the top one; each batch after it starts when the one before ends. While a batch runs it
reads Pause queue. A run cannot save its place partway, so a pause waits for the runs in flight:
no new run of the batch starts, the runs already started finish and keep their results, and the
button reads Pausing… until the last of them lands, with the number still in flight in the
progress line. When every run of a batch started at once, as one ion with three seeds does on a
machine with many processors, the pause waits for the whole batch. The paused batch keeps exactly
the runs that never started, and Resume queue runs those and then moves on to the next batch; the
queue does not move on while a batch is paused.

The running or paused batch is the top row of the queue, marked Running, Pausing or Paused, and
stays there; waiting batches can be dragged into another order below it. Each row shows its
estimate, the running row the time it has left, and the line under the list gives the total.
Remove batch removes the selected waiting batches. On the running batch it asks, then stops it:
runs already complete keep their results, and runs in flight are killed, keep their directories
marked stopped in the summary, and start again from their first trajectory if the batch is run
again. The stopped batch leaves the queue, and the next batch waits for Start queue. Removing a
paused batch asks only when some of its runs are complete, since the rest are then forgotten.

Progress shows the runs done of the batch, the time each running run has taken, and, for a
divided run, how many of its blocks of trajectories are written, against the estimate. The queue
is saved as it changes. Closing the window while a batch runs, or choosing File, Exit, asks
first, then kills the runs in flight. The batch is kept as the first entry of the queue, holding
the runs that never started and the ones killed, and a paused batch is kept the same way. When
the window next opens it offers the queue back, paused, and Resume queue carries on from there.

## Results

The table has one row per ion and gas: the trajectory-method cross section, and in helium the
projection-approximation and exact hard-sphere values, in Å², with mean ± s.d. over seeds; the
status, and for a failed run the program's reason in the status's tooltip; and the time. Copy
puts the table on the clipboard, tab-separated, and Save CSV writes it to a file. Show in folder
opens the selected row's run directory, and Open output its `mobcal.out`. Copy methods text puts
a paragraph on the clipboard that describes the completed runs of the batch from their records,
the program and version, the method, gas, element table, temperature, trajectory counts,
generator and seeds, with the papers to cite. When every run is of an ion file that carries its
import record, the paragraph also names the partial charges: the scheme, and the program,
version and keywords or route of the calculation they came from. `mobcal methods-text FOLDER`
prints the same for any runs, from their run directories or their result files.

## Help

Help, MOBCAL Help (F1, or ⌘? on macOS) opens these pages in a window of their own, which can
stay open beside the main window. The contents list every page, this one first, with its
sections under it, and the search box above them finds a word or phrase on every page at once
and lists each place it occurs under its page and section; choosing one opens the page with the
words selected. A link to another page is followed in the help window, and any other link opens
in the web browser: a file of MOBCAL's source opens on GitHub at the version installed. The
pages are the ones the package was built with, so the help needs no network connection.

## About

Help, About MOBCAL (in the MOBCAL menu on macOS) gives the version, the papers to cite, the
licence and the funding, and the Python, Qt and PySide6 versions. When the helium or nitrogen
program is not the file recorded when it was built from the pinned Fortran sources, it also says
where the programs are and what fails. `mobcal self-check` makes the same check and more
([Installing MOBCAL](install.md#checking-an-installation)).
