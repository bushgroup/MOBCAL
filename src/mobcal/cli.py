"""The ``mobcal`` command.

    mobcal version
    mobcal self-check [--choline] [--report PATH]
    mobcal build [--gas he|n2] [--out DIR]
    mobcal run INPUT [INPUT ...] [--method KEY|PATH] [--seeds N[,N...]]
               [--rng philox|ranlux] [--parameters PATH|NAME]
               [--workers N] [--split W|auto] [--out DIR] [--skip-done]
               [--settings PATH] [--temperature T] [--imp N] [--itn N] [--inp N] [--inum N]
               [--inor N]
    mobcal methods-text PATH [PATH ...]
    mobcal gui [--check]
    mobcal render-parameters he|n2 [DIR] [--parameters PATH|NAME] [--settings PATH]
    mobcal import SOURCE [--charges KEY|uniform] [--net-charge Q] [--gas he|n2|both]
                  [-o OUT.mfj] [--force]

``run`` takes input files (paths or globs), makes one job per input and seed, prints
how they will use the cores and about how long they will take (``mobcal.estimate``), runs them
``--workers`` at a time through ``mobcal.run``, prints each as it lands, and writes
``summary.csv`` and ``summary.json`` covering every run in the output folder, which can hold a
whole study. It refuses a run whose directory holds a different input of the same name, and
with ``--skip-done`` leaves out the runs the folder already holds complete. With ``--split W``
each calculation runs across W processes and reports the serial result exactly; ``--split
auto`` lets ``mobcal.estimate.allocate`` choose the runs in flight and each run's split.
``--method`` picks the method (``mobcal.methods``), which carries the gas: a shipped one by its
key, ``2012-philox-he`` by default, ``2012-he``, ``2012-n2``, ``2012-philox-n2`` or ``2000-he``,
or a method file by its path. Both gases is two commands. A table, generator or setting given
beside it overrides it, and the run records ``custom``, or the shipped method the fields make.
``--rng`` picks the random number generator: Philox4x32-10, or ``ranlux``, the 2012 generator,
which with the 2012 seed reproduces the 2012 numbers (``mobcal.run.DEFAULT_RNG`` says why the
driver's default is not the run file's). With ``--parameters PATH`` every run uses that element
table instead of the method's, checked the same way and recorded the same way; it must be a
table for the method's gas. ``--parameters NAME`` picks a shipped set by name (``2000``, the
Jarrold group's 2000 helium table; ``2012``, the default for each gas,
``mobcal.parameters.SETS``). ``--settings PATH`` names a settings file (the temperature and the
five sampling counts, ``mobcal.settings``), which replaces the method's settings, and the six
single-value options override either value by value. Its exit status is 1 if any run failed.
``import`` writes a single-set ``.mfj`` from an ORCA output or an ``.xyz`` with the charges
named by ``--charges`` (refused, listing what the file holds, until one is named), and its
provenance record ``OUT.import.json`` beside it; ``mobcal.io.structure`` says what it reads and
refuses. With ``--gas he`` or ``n2`` an element only that gas's table holds is taken; by default
the file must run in both.
``methods-text`` prints the methods paragraph and its references for the runs in the run
directories or folders named (``mobcal.methods.text``).
``render-parameters`` writes ``parameters.tab`` and ``settings.tab`` into a directory, as the
driver does into each run directory, for running the program there by hand. ``self-check`` is
``mobcal.selfcheck``.
``build`` needs a source checkout; an installed copy carries binaries built in CI. ``gui``
opens the window (``mobcal.app``), which is imported only then: this module imports no Qt.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

from mobcal import ROOT, __version__, estimate, fortran, methods, options, parameters, settings
from mobcal.batch import AUTO, CLASH, DEFAULT_SEED, DONE, Batch, BatchError, prior
from mobcal.io.infile import GENERATORS
from mobcal.run import DEFAULT_RNG, Job, Result, run_many

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

    command("version", "Print the package version.")

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
    r.add_argument("--seeds", type=_seeds, default=[DEFAULT_SEED], metavar="N[,N...]",
                   help=options.cli_help("seeds", str(DEFAULT_SEED)))
    r.add_argument("--rng", choices=sorted(GENERATORS, key=lambda g: g != DEFAULT_RNG),
                   default=None,
                   help=options.cli_help("rng", f"the method's, {DEFAULT_RNG} under "
                                         f"{methods.DEFAULT}"))
    r.add_argument("--workers", type=int, default=None, metavar="N",
                   help=options.cli_help("workers", "the number of processors divided by the "
                                         "processes per run, or under --split auto, the "
                                         "number it chooses"))
    r.add_argument("--split", type=_split, default=None, metavar="W|auto",
                   help=options.cli_help("split", "1, one process per calculation"))
    r.add_argument("--parameters", default=None, metavar="PATH|NAME",
                   help=options.cli_help("parameters",
                                         f"the method's, {parameters.DEFAULT} under "
                                         f"{methods.DEFAULT}"))
    r.add_argument("--out", type=Path, default=DEFAULT_OUT, metavar="DIR",
                   help=options.cli_help("out", f"{DEFAULT_OUT}/"))
    r.add_argument("--skip-done", action="store_true",
                   help="Leave out the runs the output folder already holds complete.")
    s = r.add_argument_group(
        "run settings", "The temperature and the five sampling counts the 2012 programs "
        "compiled in. Without these, every run uses its method's values: the 2012 values ("
        f"{_settings_default()}.")
    s.add_argument("--settings", type=Path, default=None, metavar="PATH",
                   help="A settings file (TOML) for every run, which replaces the method's "
                        "settings; a key it leaves out keeps the 2012 value.")
    s.add_argument("--temperature", type=float, default=None, metavar="T",
                   help=options.cli_help("temperature"))
    for name in settings.COUNTS:
        s.add_argument(f"--{name}", type=int, default=None, metavar="N",
                       help=options.cli_help(name))

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
    p.add_argument("--parameters", default=None, metavar="PATH|NAME",
                   help="Write this TOML file, or this shipped table by name "
                        f"({options.set_names()}), instead of the gas's default table.")
    p.add_argument("--settings", type=Path, default=None, metavar="PATH",
                   help="Write this settings file instead of the 2012 values.")

    m = command("import", "Write an .mfj from an ORCA output or an .xyz file, with the charges "
                "you name.")
    m.add_argument("source", type=Path, metavar="SOURCE",
                   help="An ORCA output, or an .xyz file.")
    m.add_argument("--charges", metavar="KEY", help=options.cli_help("charges"))
    m.add_argument("--net-charge", type=int, default=None, metavar="Q",
                   help=options.cli_help("net_charge"))
    m.add_argument("--gas", choices=(*fortran.GASES, "both"), default="both",
                   help="Whose element table the atoms must be in. Default: both.")
    m.add_argument("-o", "--out", type=Path, default=None, metavar="OUT.mfj",
                   help="The file to write, with its record beside it as OUT.import.json. "
                        "Default: SOURCE-STEM_KEY.mfj in the current directory.")
    m.add_argument("--force", action="store_true",
                   help="Replace OUT.mfj and its record if they exist.")
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
        print(__version__)
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

    if args.cmd == "import":
        return _import(args)

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
            ps = parameters.load(parameters.path_for(args.parameters, args.gas), gas=args.gas)
            st = settings.resolve(args.settings)
            args.dir.mkdir(parents=True, exist_ok=True)
            out = ps.render(args.dir)
            out_s = st.render(args.dir)
        except (parameters.ParameterError, settings.SettingsError, OSError) as e:
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
    try:
        s = structure.read(args.source)
        imp = structure.convert(s, args.charges, args.net_charge, gases)
        out = args.out or Path(f"{args.source.stem}_{args.charges}.mfj")
        mfj, rec = structure.write(imp, out, overwrite=args.force)
    except (structure.StructureError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    c = imp.record["charges"]
    print(f"wrote {mfj}: {imp.mfj.atoms} atoms from {s.path.name}"
          + (f" ({s.program} {s.version})" if s.version else "")
          + f", {c['choice']} charges summing to {c['sum']:+.6f} (net charge "
          f"{c['net_charge']:+d}), element keys of the "
          f"{' and '.join(parameters.GAS[g] for g in gases)} table"
          f"{'s' if len(gases) > 1 else ''}")
    print(f"wrote {rec}")
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
    # The method's settings, then a settings file over them whole, then single values.
    given = {k: getattr(args, k) for k in settings.NAMES}
    try:
        if args.settings is not None:
            st = settings.resolve(args.settings, **given)
        elif any(v is not None for v in given.values()) or method.overrides():
            st = settings.resolve(None, **{**method.overrides(),
                                           **{k: v for k, v in given.items() if v is not None}})
        else:
            st = None
    except settings.SettingsError as e:
        raise UsageError(str(e)) from None
    s = st or settings.DEFAULTS
    if isinstance(args.split, int) and not 1 <= args.split <= s.blocks_per_set:
        raise UsageError(f"--split takes a worker count from 1 to {s.blocks_per_set} "
                         f"(itn {s.itn} * inp {s.inp} blocks per coordinate set) or {AUTO}")
    try:
        batch = Batch(tuple(inputs), args.out, method.ref, seeds=tuple(args.seeds),
                      parameters=args.parameters, generator=args.rng, settings=st,
                      split=args.split, workers=args.workers)
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
    plan = batch.plan(jobs=jobs)
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


if __name__ == "__main__":
    sys.exit(main())
