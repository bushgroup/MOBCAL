# The window

The window runs the same calculations as the `mobcal` command, for anyone who would rather not
use a terminal. It takes `.mfj` files, or ORCA outputs and `.xyz` files that it imports, runs
them in helium or nitrogen under one of five shipped methods or a method file of one's own,
shows how long the batch will take and how far it has got, and gives a table of cross sections
with the run folders, the records and a methods paragraph one click away. Everything the window
does, the command line does too, with the same rules and the same records; this page says
where, and [The command line](command-line.md) lists every command and option. Every control
carries a tooltip that says what it sets, in the words the command line's help uses for the same
option.

To open the window, choose **MOBCAL** in the Start menu on Windows, or open `MOBCAL.app` on
macOS; on Linux, and from a terminal on any platform, run

```
mobcal gui
```

[Installing MOBCAL](install.md) says where each package puts the program.

## Inputs

Add files with Add files, or drop them on the list. An `.mfj` file runs as it is. An ORCA output or
an `.xyz` file is imported as `mobcal import` imports it ([Importing a structure and its
charges](import.md)), and its row shows the charges the import will use. When an ORCA output holds
CHELPG charges they are selected; otherwise the row asks for a choice before the batch can run.
`uniform`, the net charge spread evenly over the atoms, is always offered and never selected for
you. An `.xyz` file does not carry the ion's net charge, so its row asks for it. At Run each import
is written, `.mfj` and `.import.json`, into `imported/` in the results folder, so the folder holds
the file each run read.

## Method, Basics and Advanced

Method fills every other field, the gas among them ([Methods](methods.md)). The list holds the five
shipped methods, **MOBCAL 2012 (He)** and **(N2)**, the calculation of the 2012 release under RANLUX
([Reproducing MOBCAL 2012](mobcal-2012.md)); **MOBCAL 2012 with Philox (He)** and **(N2)**, the same
tables and settings under Philox4x32-10, the helium one chosen at the first launch; and **MOBCAL
2000 (He)**, the calculation of the Jarrold group's 2000 helium release ([Reproducing MOBCAL
2000](mobcal-2000.md)). Below them are the method files loaded or saved, by name. A field changed
after a method is chosen shows the method as *Custom (from MOBCAL 2012 (He))*, say, and the runs
record `custom`; changing it back restores the name, and fields that make another method show that
one. Changing the gas of MOBCAL 2012 (He) to N2 shows MOBCAL 2012 (N2), whereas MOBCAL 2000 (He),
which has no nitrogen form, becomes Custom. Each shipped method equals the command line its page
gives, run for run.

File, Save method… writes the gas, element table, generator and six settings the form holds to
a method file, asks for the name the list will show, and adds the file to the list. File, Load
method… adds a file saved here or elsewhere and fills the fields from it. The list remembers its
files at the next launch, and removes one that has been moved, deleted or edited since it was
added, with a message that says which and why. `mobcal run --method PATH` runs the same file.

Basics holds the gas (He or N2), the element table (the tables shipped for the gas, or a file of
one's own for the gas, [The element tables](parameters.md)), the number of seeds per ion, and
the temperature. The first seed is the 2012 seed, 5013489, under every method, and each further
seed is the next integer; with several seeds, each cross section is shown as the mean and sample
standard deviation over them. Advanced holds the generator, the five sampling counts
([The run settings](settings.md)), and how the batch uses the processors.

## How a batch uses the processors, and the estimate

By default the window chooses, by the rule `mobcal run --split auto` uses. With at least as many
runs as processors, each run is one process. With fewer, every run starts at once, and each is
divided among its share of the processors, at most 40, when that saves at least a fifth of its
time. A divided run gives the serial result exactly ([Random numbers](random-numbers.md)), so
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
different methods never share a directory and both gases of a study can share a folder, and
`summary.csv` and `summary.json` are rewritten after each batch to cover every run in the folder.
The window remembers the folder for next time. When some runs of a new batch are already in the
folder, complete, the window asks whether to skip them or run them again. It refuses to run an input
whose name another input's run directory already carries, since that run would be overwritten;
rename the input or choose another folder.

## Running, the queue and stopping

Run, Stop and Resume queue are in the Batch menu, and Add batch, under the queue, does what Run
does. Ctrl+R or F5 runs (⌘R on macOS), and Shift+F5 stops. Run starts the batch. While a batch runs,
Run adds the form's batch to the queue instead, and the queue starts its next batch when the running
one ends. Queued batches can be reordered by dragging and removed. The queue is saved as it changes,
and batches still queued when the window closes are offered back when it next opens; Batch, Resume
queue starts them.

Progress shows the runs done of the batch, the time each running run has taken, and, for a
divided run, how many of its blocks of trajectories are written, against the estimate. Stop asks,
then ends every process of the running batch. Runs already complete keep their results; the
stopped ones keep their directories, marked stopped in the summary. Closing the window while a
batch runs, or choosing File, Exit, asks the same question and stops the batch.

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
