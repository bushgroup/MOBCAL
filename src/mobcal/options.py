"""What each setting means, in the words ``mobcal run``'s help and the window's tooltips share.

The command line's options and the window's form set the same things, so their descriptions
live here, once, and both read them: ``mobcal.cli`` for its ``help=`` strings and
``mobcal.app`` for its tooltips. An entry of ``SHARED`` is a ``Description``: ``text`` says what
the value does and is the whole of the tooltip and the start of the option's help; ``cli`` adds
what only the command line needs (the values it takes and how they are written), ``window``
what only the window needs (how its control behaves). Neither addition restates ``text``, so
the two surfaces cannot drift apart without a test failing. A default is the parser's, passed
in by ``cli`` (``cli_help(key, default=...)``), since the parser owns it.

``WINDOW`` and ``COLUMNS`` hold the tooltips of the window's controls that no option sets: its
buttons, the Advanced toggle, the queue, the progress and the tables' column headers. They are
here rather than in ``mobcal.app`` so that every outward-facing sentence about a setting is in
one file, read in one place; this module imports no Qt.

One string serves both renderings. argparse rewraps help text and interpolates ``%``, so
``cli_help`` escapes ``%`` and no entry carries a line break; the window wraps a tooltip by
handing it to Qt as rich text (``mobcal.app.tip``). The text is outward-facing prose, in the
voice of ``docs/``: whole sentences, numbers where an adjective would go, no dashes as
punctuation.

    from mobcal import options
    options.cli_help("seeds", default="5013489")
    options.tooltip("seeds")
"""

from __future__ import annotations

from dataclasses import dataclass

from mobcal import estimate, methods, parameters
from mobcal.batch import AUTO, DEFAULT_SEED


@dataclass(frozen=True)
class Description:
    text: str  # what the setting does: the tooltip, and the start of the option's help
    cli: str = ""  # added on the command line
    window: str = ""  # added in the window


def set_names() -> str:
    """The shipped element tables and their gases: ``2012 (He, N2), 2000 (He)``."""
    sets = parameters.SETS
    return ", ".join(f"{n} ({', '.join(parameters.GAS[g] for g in sets if n in sets[g])})"
                     for n in parameters.names())


# What each shipped method is, for the --method help.
_METHOD = {
    "2012-he": "the 2012 release's calculation in helium, its element table and settings under "
               "RANLUX",
    "2012-n2": "the same in nitrogen",
    "2012-philox-he": "the 2012 helium table and settings under Philox4x32-10",
    "2012-philox-n2": "the same in nitrogen",
    "2000-he": "the 2000 helium release's calculation, its table at 298 K and 25 trajectories "
               "per block under RANLUX",
}
assert set(_METHOD) == set(methods.METHODS)

# How the batch divides the cores when it chooses (mobcal.estimate.allocate), shared by
# --split auto and the window's check box; the mode's entry says how each mode weighs it.
AUTO_RULE = ("chooses the runs in flight and the processes per run from the run count, the "
             "processor cores and the ion sizes, in the mode chosen, dividing a run among at "
             f"most {estimate.MAX_SPLIT} processes, no more than its slowest block of "
             "trajectories lets it use, and only when that saves at least "
             f"{1 - estimate.MIN_GAIN:.0%} of its time")

SHARED = {
    "inputs": Description(
        "The ions to run, one calculation for each input and seed.",
        cli="Paths to .mfj or .ion.json files, or globs.",
        window="Ion files (.ion.json) and .mfj files run as they are; ORCA and Gaussian "
               "outputs and .xyz files are imported at Add batch, into imported/ in the results "
               "folder. Add files, or drop them here."),
    "method": Description(
        "A preset of the gas, the element table, the random number generator and the six run "
        "settings.",
        cli="The methods are " + "; ".join(f"{k}, {v}" for k, v in _METHOD.items())
            + "; or the path of a method file. A table, generator or setting given beside it "
            "overrides it, and the run records custom.",
        window="A field changed afterwards makes the method Custom."),
    "parameters": Description(
        "The element table, which gives each atom of the ion its mass and its Lennard-Jones "
        "and hard-sphere parameters in the gas: a table the package ships, or a TOML file of "
        "one's own for one gas.",
        cli=f"A path to a table for the method's gas, or a shipped table by name: "
            f"{set_names()}.",
        window="Other file… opens a table of one's own for the gas chosen."),
    "seeds": Description(
        f"One run of each ion for every seed; the 2012 seed is {DEFAULT_SEED}. A method file "
        "may carry a seed of its own.",
        cli="A list of integers separated by commas, which wins over the method's seed.",
        window=f"The seeds are the method's seed, {DEFAULT_SEED} unless the method carries "
               "one, and each integer after it. With more than one, each cross section is the "
               "mean ± s.d. over them."),
    "temperature": Description(
        "The buffer gas temperature in kelvin, 301 K in 2012 and 298 K in 2000. It sets the "
        "trajectory method's velocity grid and the conversion of each cross section to a "
        "mobility."),
    "rng": Description(
        "The random number generator: Philox4x32-10, or RANLUX, the 2012 generator, which "
        "reproduces the 2012 outputs at the 2012 seed."),
    "imp": Description(
        "Trajectories per block of the trajectory method, one block for each velocity point "
        "in each cycle."),
    "itn": Description(
        "Cycles of the trajectory method, each an independent estimate of the collision "
        "integral, whose standard deviation the output reports."),
    "inp": Description(
        "Velocity points of the trajectory method's integration over the relative "
        "velocity."),
    "inum": Description(
        "Trajectories of the projection-approximation and exact hard-sphere pass, which the "
        "helium program alone makes."),
    "inor": Description(
        "The most reflections followed per trajectory of the exact hard-sphere pass."),
    "mode": Description(
        "How a batch of more runs than fit at once uses the processor cores. Finish in order "
        "runs one at a time, divided among every core it can use, so runs complete one after "
        "another and a pause waits for the run in flight. Balanced runs as many at once as keeps "
        f"each divided run at least {estimate.BALANCE:.0%} efficient (its time as one process, "
        "over the processes times its divided time): on a 40-core workstation, three choline "
        "runs at once in helium and one in nitrogen, and on 8 cores one at a time. Most "
        "throughput runs one process per run when there are at least as many runs as cores, "
        "which finishes the batch soonest and no run before the first wave ends. The counts "
        "are physical cores, not the logical processors hyperthreading doubles, which add a "
        "quarter to a third more throughput and make every run take about half as long again.",
        cli=f"in-order, balanced or throughput; given alone, it implies --split {AUTO}.",
        window="It is a preference of the window, kept for the next launch, and a batch "
               "waiting in the queue starts under the mode chosen when it starts."),
    "workers": Description(
        "How many runs are in flight at once.",
        window="Set here when the box above is unchecked."),
    "dealing": Description(
        "How a divided calculation shares its blocks of trajectories among its processes. "
        "Static gives each process a fixed share. Claimed lets each process take the next "
        "block no other has taken, so the processes finish together and one slowed by other "
        "work does not set the run's time. The result is the same either way.",
        cli="static or claimed."),
    "split": Description(
        "How many processes each calculation is divided among. A divided run gives the serial "
        "result exactly.",
        cli=f"W processes, or auto, which {AUTO_RULE}.",
        window="Set here when the box above is unchecked; 1 runs each calculation as one "
               "process."),
    "out": Description(
        "The folder for a study: each batch adds its run directories here, and summary.csv "
        "and summary.json are rewritten to cover every run it holds."),
    "charges": Description(
        "Which atomic charges the imported ion carries: a set the file holds, such as CHELPG or "
        "Mulliken, or uniform, the net charge spread evenly over the atoms.",
        cli="The keys are mulliken, lowdin, chelpg and hirshfeld for an ORCA output's "
            "blocks; mulliken, hirshfeld, cm5, natural, mk and chelpg for a Gaussian "
            "output's; column for an .xyz file's fifth column; and uniform. Without it, the "
            "import lists what the file holds.",
        window="An ESP fit is chosen when the file holds one, Merz-Kollman (mk) before CHELPG; "
               "otherwise choose before the batch can run."),
    "net_charge": Description(
        "The ion's net charge, in elementary charges.",
        cli="An .xyz file needs it; for an output it must agree with the charge the output was "
            "computed at.",
        window="An .xyz file does not carry it, so give it here."),
    "methods_text": Description(
        "A methods paragraph for the completed runs, written from their records: the program "
        "and version, method, gas, element table, temperature, trajectory counts, generator "
        "and seeds, with the papers to cite; and the partial charges, when every run is of an "
        "ion file that carries its import record.",
        cli="Printed for the run directories, or folders of them, named.",
        window="Copied to the clipboard once a batch has completed runs."),
}

WINDOW = {
    "gas": "The buffer gas, helium or nitrogen. It is part of the method, so changing it "
           "changes the method.",
    "load_method": "Adds a method file to the Method list, remembered at the next launch, and "
                   "fills the fields from it.",
    "save_method": "Writes the gas, the element table, the generator and the six run settings "
                   "to a method file, and adds it to the Method list.",
    "advanced": "Shows the generator, the five sampling counts and how the batch uses the "
                "processors.",
    "auto_cores": f"When checked, the batch {AUTO_RULE}. Unchecked, the two fields below set "
                  "it.",
    "add_files": "Adds ion files and .mfj files, or imports ORCA and Gaussian outputs and .xyz "
                 "files. Files can also be dropped on the list.",
    "remove_inputs": "Removes the selected inputs.",
    "choose_folder": "Chooses the results folder.",
    "net_charge_read": "Read from the output, which was computed at this charge.",
    "queue": "The batches, in the order they run. The running or paused batch is the top row "
             "and stays there; drag a waiting batch to move it.",
    "add_batch": "Adds a batch of the inputs and the fields to the left to the end of the "
                 "queue. It never starts it.",
    "start_queue": "Starts the batch at the top of the queue. Each batch after it starts when "
                   "the one before ends.",
    "pause_queue": "Starts no more runs of this batch. Runs in flight finish and keep their "
                   "results; the rest wait for Resume queue.",
    "pausing": "Waiting for the runs in flight to finish.",
    "resume_queue": "Runs the paused batch's remaining runs, then the batches after it.",
    "remove_queued": "Removes the selected batches. On the running batch it asks, then stops "
                     "it.",
    "progress": "Runs done of the batch.",
    "running": "Each running run and its time so far, and for a divided run, its blocks of "
               "trajectories written.",
    "results": "One row for each ion in each gas. Double-click a row to open its output.",
    "copy": "Copies the table to the clipboard, tab-separated, with each row's input file, run "
            "count and folder.",
    "save_csv": "Saves the table as a CSV file, with each row's input file, run count and "
                "folder.",
    "show_in_folder": "Opens the selected row's run directory, or the results folder.",
    "open_output": "Opens the selected row's mobcal.out, as double-clicking the row does.",
}

# The column headers of the window's two tables, by their text.
COLUMNS = {
    "inputs": {
        "File": "The input file; its full path is in the cell's tooltip.",
        "Atoms": "Atoms in the ion.",
        "Sets": "Coordinate sets in the file; a run reports the mean over them.",
        "Charges": "Which atomic charges the run uses. An ion file's or .mfj file's row names "
                   "its charge mode, from file, uniform or none, read from the file; an imported "
                   "structure's row is where to choose its charges.",
        "Net charge": "The ion's net charge, in elementary charges. An ion file's or .mfj file's "
                      "row shows the charge its calculation uses, read from the file and by gas "
                      "where helium and nitrogen read it differently; an .xyz file's row asks "
                      "for it.",
        "Status": "ready, or what the input needs before the batch can run; an unreadable "
                  "file's reason is in the cell's tooltip.",
    },
    "results": {
        "Ion": "The input file's name.",
        "Gas": "The buffer gas.",
        "TM (Å²)": "The trajectory-method cross section, the mean ± s.d. over seeds when there "
                   "are several.",
        "PA (Å²)": "The projection-approximation cross section, calculated in helium alone.",
        "EHS (Å²)": "The exact hard-sphere cross section, calculated in helium alone.",
        "Status": "ok, or how many of the seeds failed or were stopped; a failed run's reason "
                  "is in the cell's tooltip.",
        "Time": "The time the program took, summed over the seeds.",
    },
}


def _join(*parts: str) -> str:
    return " ".join(p for p in parts if p)


def cli_help(key: str, default: str | None = None) -> str:
    """The option's help: the shared text, the command line's addition and the default,
    with ``%`` escaped for argparse."""
    d = SHARED[key]
    return _join(d.text, d.cli, f"Default: {default}." if default else "").replace("%", "%%")


def tooltip(key: str) -> str:
    """The control's tooltip, as plain text: the shared text and the window's addition."""
    if key in WINDOW:
        return WINDOW[key]
    d = SHARED[key]
    return _join(d.text, d.window)
