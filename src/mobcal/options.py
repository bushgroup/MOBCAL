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
    options.cli_help("gas", default="he")
    options.tooltip("gas")
"""

from __future__ import annotations

from dataclasses import dataclass

from mobcal import estimate, methods, parameters
from mobcal.batch import DEFAULT_SEED


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


# What each method is, for the --method help.
_METHOD = {
    methods.CURRENT: "the 2012 element tables and settings under Philox4x32-10",
    "2012": "the 2012 release's calculation, the same under RANLUX",
    "2000": "the 2000 helium release's, its table at 298 K and 25 trajectories per block under "
            "RANLUX, for helium only",
}

# How the batch divides the processors when it chooses (mobcal.estimate.allocate), shared by
# --split auto and the window's check box.
AUTO_RULE = ("chooses the runs in flight and the processes per run from the run count, the "
             "processors and the ion sizes, dividing a run among at most "
             f"{estimate.MAX_SPLIT} processes and only when that saves at least "
             f"{1 - estimate.MIN_GAIN:.0%} of its time")

SHARED = {
    "inputs": Description(
        "The ions to run, one calculation for each input, gas and seed.",
        cli="Paths to .mfj files, or globs.",
        window=".mfj files run as they are; ORCA outputs and .xyz files are imported at Run, "
               "into imported/ in the results folder. Add files, or drop them here."),
    "method": Description(
        "A preset of the element table, the random number generator and the six run settings.",
        cli="The methods are " + "; ".join(f"{k}, {v}" for k, v in _METHOD.items())
            + ". A table, generator or setting given beside it overrides it, and the run "
            "records custom.",
        window="A field changed afterwards makes the method Custom."),
    "gas": Description(
        "The buffer gas, helium or nitrogen.",
        cli="With both, every ion runs in each."),
    "parameters": Description(
        "The element table, which gives each atom of the ion its mass and its Lennard-Jones "
        "and hard-sphere parameters in the gas: a table the package ships, or a TOML file of "
        "one's own for one gas.",
        cli=f"A path, or a shipped table by name: {set_names()}.",
        window="Other file… opens a table of one's own when one gas is chosen."),
    "seeds": Description(
        f"One run of each ion in each gas for every seed; the 2012 seed is {DEFAULT_SEED}.",
        cli="A list of integers separated by commas.",
        window=f"The seeds are {DEFAULT_SEED} and each integer after it. With more than one, "
               "each cross section is the mean ± s.d. over them."),
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
    "workers": Description(
        "How many runs are in flight at once.",
        window="Set here when the box above is unchecked."),
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
        "Which atomic charges the .mfj carries: a set the file holds, such as CHELPG or "
        "Mulliken, or uniform, the net charge spread evenly over the atoms.",
        cli="The keys are mulliken, lowdin, chelpg and hirshfeld for an ORCA output's "
            "blocks, column for an .xyz file's fifth column, and uniform. Without it, the "
            "import lists what the file holds.",
        window="CHELPG is chosen when the file holds it; otherwise choose before the batch can "
               "run."),
    "net_charge": Description(
        "The ion's net charge, in elementary charges.",
        cli="An .xyz file needs it; for an output it must agree with the charge the output was "
            "computed at.",
        window="An .xyz file does not carry it, so give it here."),
    "methods_text": Description(
        "A methods paragraph for the completed runs, written from their records: the program "
        "and version, method, gas, element table, temperature, trajectory counts, generator "
        "and seeds, with the papers to cite.",
        cli="Printed for the run directories, or folders of them, named.",
        window="Copied to the clipboard once a batch has completed runs."),
}

WINDOW = {
    "advanced": "Shows the generator, the five sampling counts and how the batch uses the "
                "processors.",
    "auto_cores": f"When checked, the batch {AUTO_RULE}. Unchecked, the two fields below set "
                  "it.",
    "add_files": "Adds .mfj files or imports ORCA outputs and .xyz files. Files can also be "
                 "dropped on the list.",
    "remove_inputs": "Removes the selected inputs.",
    "choose_folder": "Chooses the results folder.",
    "net_charge_read": "Read from the output, which was computed at this charge.",
    "queue": "Batches waiting to run, in the order they start; each starts when the one before "
             "it ends. Drag a batch to move it.",
    "remove_queued": "Removes the selected batches from the queue.",
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
        "Charges": SHARED["charges"].text,
        "Net charge": SHARED["net_charge"].text,
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
