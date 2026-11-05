"""The ``mobcal`` command.

    mobcal version
    mobcal self-check [--choline] [--report PATH]
    mobcal build [--gas he|n2] [--out DIR]
    mobcal run INPUT [INPUT ...] [--method KEY|PATH] [--seeds N[,N...]]
               [--rng philox|ranlux] [--parameters PATH|NAME]
               [--workers N] [--split W|auto] [--mode in-order|balanced|throughput]
               [--dealing static|claimed] [--out DIR]
               [--skip-done] [--scratch delete|zip|keep] [--temperature T]
               [--imp N] [--itn N] [--inp N] [--inum N] [--inor N]
    mobcal clean DIR [DIR ...] [--scratch delete|zip] [--apply]
    mobcal methods-text PATH [PATH ...]
    mobcal gui [--check]
    mobcal render-parameters he|n2 [DIR] [--method KEY|PATH] [--parameters PATH|NAME]
    mobcal import SOURCE [--charges KEY|uniform] [--net-charge Q] [--gas he|n2|both]
                  [-o OUT.ion.json] [--force]
    mobcal export ION.ion.json [--gas he|n2|both] [--parameters PATH|NAME] [-o OUT.mfj]
                  [--force]

``run`` takes input files, ``.mfj`` or ion files (paths or globs), makes one job per input and
seed, prints how they will use the cores and about how long they will take
(``mobcal.estimate``), runs them ``--workers`` at a time through ``mobcal.run``, prints each
as it lands, and writes
``summary.csv`` and ``summary.json`` covering every run in the output folder, which can hold a
whole study. It refuses a run whose directory holds a different input of the same name, and
with ``--skip-done`` leaves out the runs the folder already holds complete. With ``--split W``
each calculation runs across W processes and reports the serial result exactly; ``--split
auto`` lets ``mobcal.estimate.allocate`` choose the runs in flight and each run's split, in
the ``--mode`` given (balanced by default); ``--mode`` alone implies ``--split auto``, and with
``--split W`` it is refused.
``--method`` picks the method (``mobcal.methods``), which carries the gas: a shipped one by its
key, ``2012-philox-he`` by default, ``2012-he``, ``2012-n2``, ``2012-philox-n2`` or ``2000-he``,
or a method file, ``NAME.method.json``, by its path. Both gases is two commands. A table,
generator or setting given beside it overrides it, and the run records ``custom``, or the
shipped method the fields make.
``--rng`` picks the random number generator: Philox4x32-10, or ``ranlux``, the 2012 generator,
which with the 2012 seed reproduces the 2012 numbers (``mobcal.run.DEFAULT_RNG`` says why the
driver's default is not the run file's). With ``--parameters PATH`` every run uses that element
table instead of the method's, checked the same way and recorded the same way; it must be a
table for the method's gas. ``--parameters NAME`` picks a shipped set by name (``2000``, the
Jarrold group's 2000 helium table; ``2012``, the default for each gas,
``mobcal.parameters.SETS``). The six single-value options (the temperature and the five
sampling counts, ``mobcal.settings``) override the method's settings value by value; a set of
settings to keep is a method file. Its exit status is 1 if any run failed.
``import`` writes an ion file, ``OUT.ion.json`` (``mobcal.io.ion``), from an ORCA or Gaussian
output or an ``.xyz`` with the charges named by ``--charges`` (refused, listing what the file
holds, until one is named), its provenance record inside it; ``mobcal.io.structure`` says what
it reads and refuses, and an output of a version the import is not tested on is taken with a
warning. With ``--gas he`` or ``n2`` an element only that gas's table holds is taken; by default
the file must run in both. A ``.mfj``, the 2012 layout or MobCal-MPI's nine columns, is
taken with its own charges (``--charges`` and ``--net-charge`` are refused), and written as
``SOURCE-STEM.ion.json`` by default.
``export`` writes the ``.mfj`` the 2012 program reads from an ion file, each element's key from
the table of each gas asked for (both by default, which must agree), as a run stages it.
``--scratch`` says what a split run that succeeds keeps of its workers' files
(``mobcal.run.SCRATCH_MODES``); ``clean`` applies the same rule to finished split runs already
on disk, a dry run unless ``--apply`` (``mobcal.clean``).
``methods-text`` prints the methods paragraph and its references for the runs in the run
directories or folders named (``mobcal.methods.text``).
``render-parameters`` writes ``parameters.tab`` and ``settings.tab`` into a directory, as the
driver does into each run directory, for running the program there by hand: the 2012 settings
and the gas's default table, or with ``--method`` that method's (which must be for the gas),
and with ``--parameters`` that table. ``self-check`` is
``mobcal.selfcheck``.
``build`` needs a source checkout; an installed copy carries binaries built in CI. ``gui``
opens the window (``mobcal.app``), which is imported only then: this module imports no Qt.
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import os
import re
import sys
from pathlib import Path

from mobcal import ROOT, __version__, estimate, fortran, methods, options, parameters, settings
from mobcal.batch import AUTO, CLASH, DEFAULT_SEED, DONE, Batch, BatchError, prior
from mobcal.io.infile import DEALINGS, DEFAULT_DEALING, GENERATORS
from mobcal.run import DEFAULT_RNG, DEFAULT_SCRATCH, SCRATCH_MODES, Job, Result, run_many

DEFAULT_OUT = Path("runs")


def _split(text: str) -> int | str:
    if text == AUTO:
        return AUTO
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--split takes a worker count or {AUTO}, "
                                         f"not {text!r}") from None


def _seeds(text: str) -> list[int]:
    try:
        seeds = [int(s) for s in text.replace(",", " ").split()]
    except ValueError:
        raise argparse.ArgumentTypeError(f"seeds must be integers: {text!r}") from None
    if not seeds:
        raise argparse.ArgumentTypeError("no seeds given")
    return seeds


def expand_inputs(patterns: list[str]) -> list[Path]:
    """Each argument as a path if it exists, else as a glob; duplicates dropped, order kept."""
    found: list[Path] = []
    for pat in patterns:
        matches = [Path(pat)] if os.path.exists(pat) else [Path(m) for m in sorted(glob.glob(pat))]
        if not matches:
            raise FileNotFoundError(f"no input matches {pat!r}")
        found += [m for m in matches if m not in found]
    return found


def _settings_default() -> str:
    """The run settings without options, for the group's description."""
    d = settings.DEFAULTS
    two = methods.get("2000-he").overrides()
    return (f"temperature {d.temperature:g} K, "
            + ", ".join(f"{k} {getattr(d, k)}" for k in settings.COUNTS)
            + "), or under 2000-he, "
            + " and ".join(f"{v:g} K" if k == "temperature" else f"{k} {v}"
                           for k, v in two.items()))


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mobcal", description="Collision cross sections by the trajectory method: the 2012 "
        "MOBCAL Fortran, run many calculations at a time.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def command(name: str, help: str, description: str | None = None) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help, description=description or help)

    command("version", "Print the package version and the commit it was built from.")

    c = command("self-check", "Check that this copy can compute a cross section.")
    c.add_argument("--choline", action="store_true",
                   help="Also run the 2012 choline input in helium and compare it with the 2012 "
                        "output, about 3 min.")
    c.add_argument("--report", type=Path, metavar="PATH",
                   help="Write the report to this file as well.")

    b = command("build", "Compile the 2012 Fortran with gfortran.")
    b.add_argument("--gas", choices=fortran.GASES, help="One gas. Default: both.")
    b.add_argument("--out", type=Path, default=ROOT / "build" / "fortran",
                   metavar="DIR",
                   help="The output directory. Default: build/fortran/.")

    r = command("run", "Run calculations in parallel, one process per run.")
    r.add_argument("inputs", nargs="+", metavar="INPUT", help=options.cli_help("inputs"))
    r.add_argument("--method", default=methods.DEFAULT, metavar="KEY|PATH",
                   help=options.cli_help("method", methods.DEFAULT))
    r.add_argument("--seeds", type=_seeds, default=None, metavar="N[,N...]",
                   help=options.cli_help("seeds", f"the method's seed, {DEFAULT_SEED} under a "
                                         "method without one"))
    r.add_argument("--rng", choices=sorted(GENERATORS, key=lambda g: g != DEFAULT_RNG),
                   default=None,
                   help=options.cli_help("rng", f"the method's, {DEFAULT_RNG} under "
                                         f"{methods.DEFAULT}"))
    r.add_argument("--workers", type=int, default=None, metavar="N",
                   help=options.cli_help("workers", "the number of processor cores divided by the "
                                         "processes per run, or under --split auto, the "
                                         "number it chooses"))
    r.add_argument("--split", type=_split, default=None, metavar="W|auto",
                   help=options.cli_help("split", "1, one process per calculation"))
    r.add_argument("--mode", choices=list(estimate.MODES), default=None,
                   help=options.cli_help("mode", estimate.DEFAULT_MODE))
    r.add_argument("--dealing", choices=list(DEALINGS), default=None,
                   help=options.cli_help("dealing", DEFAULT_DEALING))
    r.add_argument("--parameters", default=None, metavar="PATH|NAME",
                   help=options.cli_help("parameters",
                                         f"the method's, {parameters.DEFAULT} under "
                                         f"{methods.DEFAULT}"))
    r.add_argument("--out", type=Path, default=DEFAULT_OUT, metavar="DIR",
                   help=options.cli_help("out", f"{DEFAULT_OUT}/"))
    r.add_argument("--skip-done", action="store_true",
                   help="Leave out the runs the output folder already holds complete.")
    r.add_argument("--scratch", choices=SCRATCH_MODES, default=DEFAULT_SCRATCH,
                   help="What a divided run that succeeds keeps of the files its processes "
                        "wrote. Delete removes the folder of each process, the claim files and "
                        "the block files, after writing what only those folders held into the "
                        "run's record.json. Zip does the same but packs the block files into "
                        "blocks.zip, which unpacked into the run's folder lets the program redo "
                        "the combining step there. Keep leaves every file. A run that fails or "
                        "is stopped keeps every file whatever this says. delete, zip or keep. "
                        f"Default: {DEFAULT_SCRATCH}.")
    s = r.add_argument_group(
        "run settings", "The temperature and the five sampling counts the 2012 programs "
        "compiled in. Without these, every run uses its method's values: the 2012 values ("
        f"{_settings_default()}.")
    s.add_argument("--temperature", type=float, default=None, metavar="T",
                   help=options.cli_help("temperature"))
    for name in settings.COUNTS:
        s.add_argument(f"--{name}", type=int, default=None, metavar="N",
                       help=options.cli_help(name))

    k = command("clean", "Remove the files the processes of finished divided runs left, as a "
                "run now does when it succeeds.")
    k.add_argument("paths", nargs="+", type=Path, metavar="DIR",
                   help="Run directories, or folders of them.")
    k.add_argument("--scratch", choices=("delete", "zip"), default="delete",
                   help="Delete the block files, or pack them into blocks.zip in each run's "
                        "folder. The folder of each process and the claim files go either way. "
                        "Default: delete.")
    k.add_argument("--apply", action="store_true",
                   help="Remove the files. Without it, the command lists what it would remove "
                        "and removes nothing.")

    g = command("gui", "Open the window.")
    g.add_argument("--check", action="store_true",
                   help="Open the window, close it, and exit 0: a test that it starts.")

    t = command("methods-text", "Print the methods paragraph for runs.",
                options.cli_help("methods_text"))
    t.add_argument("paths", nargs="+", type=Path, metavar="PATH",
                   help="Run directories, or folders of them.")

    p = command("render-parameters", "Write the element table and the settings the program "
                "reads into a directory, for running the program there by hand.")
    p.add_argument("gas", choices=fortran.GASES, metavar="GAS",
                   help="The gas whose table is written: he or n2.")
    p.add_argument("dir", type=Path, nargs="?", default=Path("."), metavar="DIR",
                   help="Where to write parameters.tab and settings.tab. Default: the current "
                        "directory.")
    p.add_argument("--method", default=None, metavar="KEY|PATH",
                   help="Write this method's table and settings, a shipped method by its key or "
                        "a method file by its path; it must be a method for the gas. Default: "
                        "the gas's default table and the 2012 settings.")
    p.add_argument("--parameters", default=None, metavar="PATH|NAME",
                   help="Write this TOML file, or this shipped table by name "
                        f"({options.set_names()}), instead of the method's or the gas's "
                        "default table.")

    m = command("import", "Write an ion file from an ORCA or Gaussian output or an .xyz file, "
                "with the charges you name, or from a .mfj, with its own.")
    m.add_argument("source", type=Path, metavar="SOURCE",
                   help="An ORCA or Gaussian output, an .xyz file, or a .mfj (the 2012 "
                        "layout or MobCal-MPI's nine columns).")
    m.add_argument("--charges", metavar="KEY", help=options.cli_help("charges"))
    m.add_argument("--net-charge", type=int, default=None, metavar="Q",
                   help=options.cli_help("net_charge"))
    m.add_argument("--gas", choices=(*fortran.GASES, "both"), default="both",
                   help="Whose element table the atoms must be in. Default: both.")
    m.add_argument("-o", "--out", type=Path, default=None, metavar="OUT.ion.json",
                   help="The ion file to write. Default: SOURCE-STEM_KEY.ion.json in the "
                        "current directory.")
    m.add_argument("--force", action="store_true",
                   help="Replace OUT.ion.json if it exists.")

    x = command("export", "Write the .mfj the 2012 program reads from an ion file.")
    x.add_argument("ion", type=Path, metavar="ION.ion.json", help="The ion file.")
    x.add_argument("--gas", choices=(*fortran.GASES, "both"), default="both",
                   help="Whose element table gives each element its key; with both, each "
                        "element must be in both tables. Default: both.")
    x.add_argument("--parameters", default=None, metavar="PATH|NAME",
                   help="This TOML file, or this shipped table by name "
                        f"({options.set_names()}), instead of the gas's default table.")
    x.add_argument("-o", "--out", type=Path, default=None, metavar="OUT.mfj",
                   help="The file to write. Default: ION.mfj beside the ion file.")
    x.add_argument("--force", action="store_true", help="Replace OUT.mfj if it exists.")
    return ap


REFERENCE = Path("docs") / "command-line.md"
REFERENCE_WIDTH = 88  # the usage lines' wrap, fixed so the page does not follow the terminal
REFERENCE_OPENING = (
    "`mobcal` is the program the window runs, typed in a terminal: one command with a "
    "subcommand for each task, running calculations, writing an input from a quantum chemistry "
    "output, writing the methods paragraph for finished runs, checking and building the "
    "programs, and opening the window. `mobcal` runs in any terminal once the installation's "
    "folder is on the `PATH`, which the Windows installer offers to do, and in the MOBCAL "
    "command prompt of the Windows Start menu either way ([Installing MOBCAL](install.md)). "
    "The options of `mobcal run` and `mobcal import` that the "
    "window also sets carry the same descriptions as its tooltips, from one table in the "
    "package, so the two say the same thing about every setting they share "
    "([The window](window.md)). `mobcal COMMAND -h` prints a command's section of this page.")


def _code(help: str) -> str:
    """A help string for the page: argparse's escapes undone, option names as code."""
    return re.sub(r"(?<![\w`])(--[a-z][\w-]*)", r"`\1`", help.replace("%%", "%"))


def reference() -> str:
    """``docs/command-line.md``: every subcommand's usage and arguments, from the parser.
    ``tools/make_command_line.py`` writes it and a test holds the committed page to it."""
    # argparse keeps its subcommands and groups in private attributes, stable since 2.7.
    ap = parser()
    sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
    short = {a.dest: a.help for a in sub._choices_actions}
    lines = ["# The command line", "",
             "<!-- Generated by tools/make_command_line.py from the argument parser in "
             "src/mobcal/cli.py and the descriptions in src/mobcal/options.py. Edit those and "
             "run the tool; a test fails while this page differs from what it writes. -->", "",
             REFERENCE_OPENING, ""]
    lines += [f"- [`mobcal {name}`](#mobcal-{name}): {short[name]}" for name in sub.choices]
    for name, p in sub.choices.items():
        p.formatter_class = lambda prog: argparse.HelpFormatter(prog, width=REFERENCE_WIDTH)
        lines += ["", f"## mobcal {name}", "", p.description, "", "```",
                  p.format_usage().strip(), "```"]
        fmt = argparse.HelpFormatter(p.prog)
        for g in p._action_groups:
            acts = [a for a in g._group_actions if a.dest != "help"]
            if not acts:
                continue
            if g.title not in ("positional arguments", "options"):
                lines += ["", f"### {g.title[0].upper()}{g.title[1:]}"]
                if g.description:
                    lines += ["", g.description]
                lines.append("")
            elif lines[-1] == "```":
                lines.append("")
            lines += [f"- `{fmt._format_action_invocation(a)}`: {_code(a.help or '')}"
                      for a in acts]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    if args.cmd == "version":
        commit = fortran.short_commit(fortran._commit())
        print(f"{__version__} ({commit})" if commit else __version__)
        return 0

    if args.cmd == "self-check":
        from mobcal import selfcheck
        return selfcheck.run(choline=args.choline, report=args.report)

    if args.cmd == "build":
        if fortran.frozen():
            print("error: this is an installed copy, which carries the binaries built for it "
                  f"in {fortran.binary_dir()}; `mobcal build` needs a source checkout",
                  file=sys.stderr)
            return 2
        problems = fortran.verify_sources()
        if problems:
            print("refusing to build: fortran/ is not the pinned code", file=sys.stderr)
            for p in problems:
                print("  " + p, file=sys.stderr)
            return 2
        print(fortran.describe())
        for gas in ([args.gas] if args.gas else fortran.GASES):
            try:
                b = fortran.build(gas, args.out)
            except FileNotFoundError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            print(f"built {b.binary}" + (f" ({b.warnings} warnings)" if b.warnings else ""))
        return 0

    if args.cmd == "run":
        return _run(args)

    if args.cmd == "clean":
        return _clean(args)

    if args.cmd == "import":
        return _import(args)

    if args.cmd == "export":
        return _export(args)

    if args.cmd == "gui":
        from mobcal.app import main as gui
        return gui(sys.argv[:1], check=args.check)

    if args.cmd == "methods-text":
        try:
            print(methods.text(methods.read_records(args.paths)), end="")
        except (OSError, ValueError, KeyError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "render-parameters":
        try:
            st, table = settings.DEFAULTS, args.parameters
            if args.method is not None:
                m = methods.get(args.method)
                if m.gas != args.gas:
                    raise methods.MethodError(
                        f"{m.title} is a method for {parameters.GAS[m.gas]}, not "
                        f"{parameters.GAS[args.gas]}")
                st = m.settings
                if table is None:
                    table = m.table_path()
            ps = parameters.load(parameters.path_for(table, args.gas), gas=args.gas)
            args.dir.mkdir(parents=True, exist_ok=True)
            out = ps.render(args.dir)
            out_s = st.render(args.dir)
        except (parameters.ParameterError, methods.MethodError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"wrote {out}: {ps.name}, {len(ps.elements)} elements, from {ps.path}")
        print(f"wrote {out_s}: " + ("the 2012 settings" if st.is_default else
                                    " ".join(f"{k}={v:g}" for k, v in st.values().items())))
        return 0

    return 1


def _import(args: argparse.Namespace) -> int:
    from mobcal.io import structure
    gases = tuple(fortran.GASES) if args.gas == "both" else (args.gas,)
    if args.source.suffix.lower() == ".mfj":
        return _import_mfj(args, gases)
    try:
        s = structure.read(args.source)
        imp = structure.convert(s, args.charges, args.net_charge, gases)
        out = structure.write(imp, args.out or structure.default_name(args.source, args.charges),
                              overwrite=args.force)
    except (structure.StructureError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for w in s.warnings:
        print(f"warning: {w}", file=sys.stderr)
    c = imp.record["charges"]
    print(f"wrote {out}: {imp.ion.atoms} atoms from {s.path.name}"
          + (f" ({s.program} {s.version})" if s.version else "")
          + f", {c['choice']} charges summing to {c['sum']:+.6f} (net charge "
          f"{c['net_charge']:+d}), every element in the "
          f"{' and '.join(parameters.GAS[g] for g in gases)} table"
          f"{'s' if len(gases) > 1 else ''}")
    return 0


def _import_mfj(args: argparse.Namespace, gases: tuple[str, ...]) -> int:
    from mobcal.io import structure
    given = [f for f, v in (("--charges", args.charges), ("--net-charge", args.net_charge))
             if v is not None]
    try:
        if given:
            raise structure.StructureError(
                f"{args.source.name}: a .mfj carries its charges, which the ion file keeps as "
                f"read; {' and '.join(given)} {'is' if len(given) == 1 else 'are'} not taken")
        imp = structure.from_mfj(args.source, gases)
        out = structure.write(imp, args.out or structure.default_name(args.source, None),
                              overwrite=args.force)
    except (structure.StructureError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    i = imp.ion
    layout = imp.record["source"]["program"]
    print(f"wrote {out}: {i.atoms} atoms, {len(i.conformers)} conformer"
          f"{'s' if len(i.conformers) > 1 else ''} from {args.source.name}"
          + (" (MobCal-MPI layout)" if layout == "MobCal-MPI" else "")
          + f", {i.charge_mode} mode, "
          + (f"net charge {i.molecular_charge:+d}" if i.molecular_charge is not None
             else "no integer net charge")
          + f", every element in the {' and '.join(parameters.GAS[g] for g in gases)} table"
          f"{'s' if len(gases) > 1 else ''}")
    return 0


def _export(args: argparse.Namespace) -> int:
    from mobcal.io import ion
    gases = tuple(fortran.GASES) if args.gas == "both" else (args.gas,)
    out = args.out or args.ion.with_name(ion.stem(args.ion) + ".mfj")
    try:
        i = ion.Ion.read(args.ion)
        tables = [parameters.load(parameters.path_for(args.parameters, g), gas=g)
                  for g in gases]
        written = {t.name: i.mfj(t) for t in tables}
        first = next(iter(written.values()))
        if any(m != first for m in written.values()):
            raise ion.IonError(f"the tables {' and '.join(written)} give an element different "
                               "keys; export for one gas")
        if out.exists() and not args.force:
            raise ion.IonError(f"{out} exists; not replacing it")
        m = first.write(out)
    except (ion.IonError, parameters.ParameterError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"wrote {m}: {i.atoms} atoms, {len(i.conformers)} conformer"
          f"{'s' if len(i.conformers) > 1 else ''}, keys of the "
          f"{' and '.join(repr(t.name) for t in tables)} table{'s' if len(tables) > 1 else ''}")
    return 0


class UsageError(ValueError):
    """Options that cannot make a batch; the message is the one the command prints."""


def batch_from_args(args: argparse.Namespace) -> Batch:
    """The batch ``mobcal run``'s options describe, checked but not run: what the window's
    form makes too. Raises UsageError."""
    try:
        inputs = expand_inputs(args.inputs)
    except FileNotFoundError as e:
        raise UsageError(str(e)) from None
    try:
        method = methods.get(args.method)
    except methods.MethodError as e:
        raise UsageError(str(e)) from None
    gas = method.gas
    # A shipped set's name stands for the gas's set of that name; a path, for one gas's table.
    try:
        parameters.path_for(args.parameters, gas)
    except parameters.ParameterError as e:
        raise UsageError(str(e)) from None
    if args.parameters is not None and args.parameters not in parameters.names():
        try:
            ps = parameters.load(args.parameters)
        except parameters.ParameterError as e:
            raise UsageError(str(e)) from None
        if ps.gas != gas:
            raise UsageError(f"{args.parameters} is a table for {parameters.GAS[ps.gas]} and "
                             f"{method.title} is a method for {parameters.GAS[gas]}; run it "
                             f"with a {parameters.GAS[ps.gas]} method")
    # The method's settings, then single values.
    given = {k: getattr(args, k) for k in settings.NAMES}
    try:
        if any(v is not None for v in given.values()) or method.overrides():
            st = settings.resolve(**{**method.overrides(),
                                           **{k: v for k, v in given.items() if v is not None}})
        else:
            st = None
    except settings.SettingsError as e:
        raise UsageError(str(e)) from None
    s = st or settings.DEFAULTS
    if isinstance(args.split, int) and args.mode is not None:
        raise UsageError(f"--mode chooses under --split {AUTO}; --split {args.split} sets the "
                         "processes per run itself")
    if args.mode is not None and args.split is None:
        args.split = AUTO
    if isinstance(args.split, int) and not 1 <= args.split <= s.blocks_per_set:
        raise UsageError(f"--split takes a worker count from 1 to {s.blocks_per_set} "
                         f"(itn {s.itn} * inp {s.inp} blocks per coordinate set) or {AUTO}")
    try:
        batch = Batch(tuple(inputs), args.out, method.ref,
                      seeds=None if args.seeds is None else tuple(args.seeds),
                      parameters=args.parameters, generator=args.rng, settings=st,
                      split=args.split, workers=args.workers, dealing=args.dealing)
        batch.jobs()
    except (BatchError, ValueError) as e:
        raise UsageError(str(e)) from None
    return batch


def _run(args: argparse.Namespace) -> int:
    try:
        batch = batch_from_args(args)
        fortran.find_binary(batch.resolved_gas)
    except (UsageError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    jobs = batch.jobs()

    found = prior(jobs)
    clashes = [f for f in found if f.kind == CLASH]
    if clashes:
        for f in clashes:
            print(f"error: {f.job.run_dir} {f.detail}", file=sys.stderr)
        print("error: rename the input or choose another --out", file=sys.stderr)
        return 2
    if args.skip_done:
        done = {f.job.label for f in found if f.kind == DONE}
        if done:
            print(f"skipping {len(done)} run{'s' if len(done) != 1 else ''} the folder holds "
                  "complete", flush=True)
        jobs = [j for j in jobs if j.label not in done]
        if not jobs:
            print(f"nothing to run; {args.out}/ holds every run complete")
            return 0
    jobs = [dataclasses.replace(j, scratch=args.scratch) for j in jobs]
    plan = batch.plan(jobs=jobs, mode=args.mode or estimate.DEFAULT_MODE)
    gen = batch.resolved_generator
    st = batch.resolved_settings
    changed = " ".join(f"{k}={v:g}" for k, v in st.values().items()
                       if v != getattr(settings.DEFAULTS, k))
    print(f"method {batch.title()}, generator {gen}"
          + (f", settings {changed}" if changed else ", the 2012 settings")
          + (f", element table {args.parameters}" if args.parameters else "")
          + f", binaries from {fortran.binary_dir()}, output under {args.out}/", flush=True)
    print(estimate.describe(plan), flush=True)

    def progress(r: Result, done: int, total: int) -> None:
        print(f"[{done}/{total}] {r}", flush=True)

    def blocks(job: Job, n: int, total: int) -> None:
        if n and n % 40 == 0 or n == total:
            print(f"    {job.label}: {n}/{total} blocks", flush=True)

    summary = run_many(plan.jobs, plan.workers, progress, blocks=blocks)
    csv_path, json_path = summary.write(args.out)
    print(f"{summary}; wrote {csv_path} and {json_path}")
    return 1 if summary.failed else 0


def _clean(args: argparse.Namespace) -> int:
    from mobcal import clean
    todo = clean.plan(args.paths)
    if not todo:
        print("nothing to clean: no finished divided run here holds files of its processes")
        return 0
    files = sum(c.files for c in todo)
    for c in todo:
        print(c, flush=True)
        if args.apply:
            entry = clean.apply(c, args.scratch)
            if entry["left"]:
                print(f"    left {len(entry['left'])}: {', '.join(entry['left'][:5])}",
                      flush=True)
    n = len(todo)
    runs = f"{n} run{'s' if n != 1 else ''}"
    if args.apply:
        print(f"cleaned {runs}, {files} files")
    else:
        print(f"{runs}, {files} files would be removed; run again with --apply to remove them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
