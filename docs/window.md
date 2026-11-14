# The window

The window runs the calculations of the `mobcal` command for anyone who would rather not use a
terminal. It takes ion files and `.mfj` files, and it imports ORCA outputs, Gaussian outputs, and
`.xyz` files. It runs them in helium or nitrogen under one of the shipped methods and estimates
how long each batch will take. It gives a table of cross sections, with the run directories, the
records, and a methods paragraph one click away. Everything the window does, the command line does
too, by the same rules and with the same records; this page names the command for each, and [The
command line](command-line.md) lists every command and option. Every control carries a tooltip
that says what it sets, in the words the command-line help uses for the same option.

To open the window, choose **MOBCAL** in the Start menu on Windows, open `MOBCAL.app` on macOS,
or from a terminal on any platform, run

```
mobcal gui
```

[Installing MOBCAL](install.md) says where each package puts the program. The form is on the
left (Inputs, Method, Basics, Advanced, and Results folder, with the estimate for the batch under
them), and the Queue, Progress, and Results are on the right.

## Inputs

To add inputs, choose **Add files…** or drop files on the list; **Remove** takes the selected rows
out. Each row gives the file, its atoms, its coordinate sets, its charges, its net charge, and a
status, which reads "ready" or says what the input needs before the batch can run.

An ion file, `X.ion.json` ([The ion file](ion-file.md)), or an `.mfj` file runs as it is, and its
row shows what the file makes of the charges, read-only. Charges names the charge mode of the
file: `calc` reads "from file", `equal` reads "uniform", and `none` reads "none". Net charge gives
the charge the calculation uses. A `calc` row shows the sum of the charge column and a `none` row
shows 0, whereas an `equal` row shows one value for each gas, "+1 He / +2 N2" for a column that
sums to 2, because the helium and nitrogen programs read `equal` differently
([Charges](ion-file.md#charges)). A sum within 0.01 e of an integer is shown as the integer and
any other sum to three decimals; the tooltip gives the sum of the first coordinate set to six
decimals, and the sum of every set when they differ by more than 0.01 e. The nitrogen program
reads a charge on every atom line whatever the mode, so a file with four columns, or an ion file
with an atom that has no charge, cannot run in nitrogen, and its status says so.

An `.mfj` in the nine-column layout of MobCal-MPI is refused, as `mobcal run` refuses it.
`mobcal import` reads such a file into an ion file, which the window runs ([A `.mfj` as the
source](import.md#a-mfj-as-the-source)).

An ORCA output, a Gaussian output, or an `.xyz` file is imported as `mobcal import` imports it
([Importing a structure and its charges](import.md)), and its row is where the charges are
chosen. When an output holds an ESP fit, that fit is selected, the Merz-Kollman fit before CHELPG;
otherwise the row asks for a choice before the batch can run. `uniform`, i.e., the net charge
spread evenly over the atoms, is always offered and never selected for you. An `.xyz` file does
not carry the net charge of the ion, so its row asks for it. An output of a program version the
import is not tested on reads "ready (untested version)", and its tooltip gives the warning.

At **Add batch** each import is written as an ion file into `imported/` in the results folder, and
the batch runs that file, so the folder holds the file each run read and the record of where its
charges came from. An ion file already in `imported/` that holds the same ion is left as it is, so
the runs made from it before are still found complete.

## Method, Basics and Advanced

**Method** fills every other field of the form, the gas among them ([Methods](methods.md)). The
list holds the five shipped methods and, below them, the method files loaded or saved, by name:

- **MOBCAL 2012 (He)** and **MOBCAL 2012 (N2)**, the calculation of the 2012 release under RANLUX
  ([Reproducing MOBCAL 2012](mobcal-2012.md));
- **MOBCAL 2012 with Philox (He)** and **MOBCAL 2012 with Philox (N2)**, the same tables and
  settings under Philox4x32-10. The helium one is selected at the first launch, and the method
  last chosen at every later launch;
- **MOBCAL 2000 (He)**, the calculation of the 2000 helium release of the Jarrold group
  ([Reproducing MOBCAL 2000](mobcal-2000.md)).

Holding the pointer over a method shows its description, when it has one. A field changed after a
method is chosen shows the method as Custom, e.g., "Custom (from MOBCAL 2012 (He))", and the runs
record `custom`; changing the field back restores the name, and fields that make another method
show that one. Changing the gas of **MOBCAL 2012 (He)** to N2 therefore shows **MOBCAL 2012
(N2)**, whereas **MOBCAL 2000 (He)**, which has no nitrogen form, becomes Custom.

To keep the fields of the form as a method, choose **File ▸ Save method…**, which writes the gas,
the element table, the generator, and the six settings to a method file, `NAME.method.json`, asks
for the name the list will show, and adds the file to the list. **File ▸ Load method…** adds a
method file saved here or elsewhere and fills the fields from it. The list remembers its files at
the next launch and removes, with a message that says which and why, a file that has been moved,
deleted, or edited since it was added. `mobcal run --method PATH` runs the same file ([Method
files](methods.md#method-files)).

Basics holds the gas (He or N2), the element table, the number of seeds per ion, and the
temperature. **Element table** lists the tables shipped for the gas, and **Other file…** opens a
TOML table written for that gas ([The element tables](parameters.md)). The first seed is the
method seed when the method file carries one, which **Seeds per ion** then shows (", from seed
42"), and the 2012 seed, 5013489, otherwise; each further seed is the next integer ([The
seed](random-numbers.md#the-seed)). With several seeds, each cross section is shown as the mean
and the sample standard deviation over them.

Advanced, which opens at its arrow, holds the generator ([Random numbers](random-numbers.md)), the
five sampling counts ([The run settings](settings.md)), and how the batch uses the cores.

## How a batch uses the cores, and the estimate

By default the window chooses how many runs are in flight at once and how many processes each run
is divided among, by the rule `mobcal run --split auto` uses ([How a batch uses the
cores](large-ions.md#how-a-batch-uses-the-cores)). A divided run, i.e., one calculation run as
several processes, gives the serial result exactly, so the choice changes how long a batch takes
and never a number. The list beside the check box **Choose how the batch uses the cores** in
Advanced selects one of three modes:

- **Balanced**, the default, runs as many runs at once as keeps each divided run at least 70 %
  efficient.
- **Finish in order** runs one run at a time, divided among every core it can use, so runs
  complete one after another and **Pause queue** waits only for the run in flight.
- **Most throughput** runs one process per run when there are at least as many runs as cores. It
  finishes a long batch soonest, and no run finishes before the first wave does.

In every mode a run is divided among at most 40 processes. The window counts physical cores, not
the logical processors that hyperthreading doubles. The mode is a preference of the window, kept
for the next launch, and a batch waiting in the queue starts under the mode selected when it
starts. Unchecking the box sets **Runs at once** and **Processes per run** by hand, the second up
to 400.

Under the form, one line says how the batch will run and about how long it will take: the method,
the runs, how many are in flight at once, the processes each is divided among, the mode, and the
estimate. When each process spends a minute or more before its first trajectory, the line gives
that time as well. The estimate reads the number of atoms of each ion and not its charge, and it
comes from timings on one workstation, so a faster or slower machine scales it ([The
estimate](large-ions.md#the-estimate)).

## The results folder

Choose one results folder for a study. Every batch adds its run directories to it, and
`summary.csv` and `summary.json` are rewritten after each batch to cover every run in the folder
([The results folder](results-folder.md)). A run directory is named for the input, the gas, the
seed, and anything that differs from the default method, so runs of different methods never share
a directory and both gases of a study can share a folder. The window remembers the folder for the
next launch. When some runs of a new batch are already in the folder, complete, **Add batch** asks
whether to skip them or run them again. It refuses a batch with an input whose name the run
directory of another input already carries, since that run would be overwritten; rename the input
or choose another folder.

Each run directory holds the result file of its run, `NAME.result.json`, which carries both inputs
and every value the program reported ([The result file](result-file.md)). **Keep the ion in each
result file**, below the folder, is checked by default, and each result file then carries the
geometries and charges of the ion. To keep result files small when the geometries are kept
elsewhere, as for thousands of frames of a molecular dynamics trajectory, uncheck it, and each
result file names the ion file by its name and SHA-256 alone. A batch keeps the choice it was
added with, in the queue and across launches.

## Running, the queue and stopping

Every batch control is a button in the Queue box: **Add batch**, a second button that starts,
pauses, and resumes the queue, and **Remove batch**. None has a menu entry or a keyboard shortcut.

To run a batch, choose **Add batch** and then **Start queue**. **Add batch** puts the batch the
form describes at the end of the queue and never starts it, whether or not a batch is running; it
is unavailable while an input is being read or needs a choice, and the line under the form says
which. **Start queue** starts the top batch, and each batch after it starts when the one before
ends.

To pause, choose **Pause queue**, as the second button reads while a batch runs. A run cannot save
its place partway, so a pause waits for the runs in flight: no new run of the batch starts, the
runs already started finish and keep their results, and the button reads **Pausing…** until the
last of them lands, with the number still in flight in the progress line. The paused batch keeps
exactly the runs that never started, and **Resume queue** runs those and then moves on to the next
batch; the queue does not move on while a batch is paused. When every run of a batch started at
once, as one ion with three seeds does on a machine with many cores, the pause waits for the whole
batch, and the next batch then waits for **Start queue**.

The running or paused batch is the top row of the queue, marked "Running", "Pausing", or "Paused",
and stays there; waiting batches can be dragged into another order below it. Each row shows its
estimate, the running row the time it has left, and the line under the list gives the total.

To take a batch out of the queue, select it and choose **Remove batch**. On the running batch the
button asks, then stops it: runs already complete keep their results, whereas runs in flight are
killed, keep their directories, are marked stopped in the summary, and start again from their
first trajectory if the batch is run again. The stopped batch leaves the queue, and the next batch
waits for **Start queue**. Removing a paused batch asks only when some of its runs are complete,
since the rest are then forgotten.

Progress shows the runs done of the batch, the time each running run has taken, and, for a
divided run, how many of its blocks of trajectories are written, against the estimate. The queue
is saved as it changes. Closing the window while a batch runs, or choosing **File ▸ Exit**, asks
first, then kills the runs in flight. The batch is kept as the first entry of the queue, holding
the runs that never started and the ones killed, and a paused batch is kept the same way. When
the window next opens it offers the queue back, paused, and **Resume queue** carries on from
there.

## Results

The table has one row for each ion in each gas: the trajectory-method cross section and, in
helium, the projection-approximation and exact hard-sphere values, in Å², each the mean ± s.d.
over seeds; the status, whose tooltip gives the reason the program gave for a failed run; and the
time the program took, summed over the seeds. **Copy** puts the table on the clipboard,
tab-separated, and **Save CSV…** writes it to a file, each with the input file, the run count, and
the folder of every row. **Show in folder** opens the run directory of the selected row, and
**Open output**, or a double-click on the row, opens its `mobcal.out`.

**Copy methods text** puts a paragraph on the clipboard that describes the completed runs of the
batch from their records: the program and version, the method, gas, element table, temperature,
trajectory counts, generator, and seeds, with the papers to cite. When every run is of an ion file
that carries its import record, the paragraph also names the partial charges: the scheme, and the
program, version, and keywords or route of the calculation they came from. `mobcal methods-text
FOLDER` prints the same paragraph for any runs, from their run directories or their result files.

## Help

**Help ▸ MOBCAL Help** (F1, or ⌘? on macOS) opens these pages in a window of their own, which can
stay open beside the main window. It opens on the tutorial for the platform it runs on. The
contents list every page, the three tutorials first and this page after them, each with its
sections under it, and the search box above them finds a word or phrase on every page at once
and lists each place it occurs under its page and section; choosing one opens the page with the
words selected. A link to another page is followed in the help window, and any other link opens
in the web browser: a file of the MOBCAL source opens on GitHub at the version installed. The
pages are the ones the package was built with, so the help needs no network connection.

## About

**Help ▸ About MOBCAL** (in the MOBCAL menu on macOS) gives the version, the papers to cite, the
licence, and the funding, and the Python, Qt, and PySide6 versions. When the helium or nitrogen
program is not the file recorded when it was built from the pinned Fortran sources, it also says
where the programs are and what fails. `mobcal self-check` makes the same check and more
([Installing MOBCAL](install.md#checking-an-installation)).
