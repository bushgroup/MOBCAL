"""The ``mobcal`` command.

    mobcal version
    mobcal self-check [--choline] [--report PATH]
    mobcal build [--gas he|n2] [--out DIR]
    mobcal run INPUT [INPUT ...] [--gas he|n2|both] [--seeds N[,N...]] [--rng philox|ranlux]
               [--workers N] [--split W] [--parameters PATH|NAME] [--out DIR]
               [--settings PATH] [--temperature T] [--imp N] [--itn N] [--inp N] [--inum N]
               [--inor N]
    mobcal render-parameters he|n2 [DIR] [--parameters PATH|NAME] [--settings PATH]

``run`` takes input files (paths or globs), makes one job per input, gas and seed, runs them
``--workers`` at a time through ``mobcal.run``, prints each as it lands, and writes
``summary.csv`` and ``summary.json`` beside the run directories. With ``--split W`` each
calculation runs across W processes and reports the serial result exactly. ``--rng`` picks the
random number generator: Philox4x32-10 by default, or ``ranlux``, the 2012 generator, which
with the 2012 seed reproduces the 2012 numbers (``mobcal.run.DEFAULT_RNG`` says why the
default is not the run file's). With
``--parameters PATH`` every run uses that element table instead of the package's own, checked
the same way and recorded the same way; ``--parameters NAME`` picks a shipped set by name
(``2000``, the Jarrold group's 2000 helium table; ``2012``, the default for each gas,
``mobcal.parameters.SETS``). ``--settings PATH`` names a settings file (the
temperature and the five sampling counts, ``mobcal.settings``) and the six single-value
options override it value by value; without them every run uses the 2012 values. Its exit
status is 1 if any run failed.
``render-parameters`` writes ``parameters.tab`` and ``settings.tab`` into a directory, as the
driver does into each run directory, for running the program there by hand. ``self-check`` is
``mobcal.selfcheck``.
``build`` needs a source checkout; an installed copy carries binaries built in CI. The window's
``gui`` arrives with its task. This module imports no Qt.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

from mobcal import ROOT, __version__, fortran, parameters, settings
from mobcal.io.infile import GENERATORS
from mobcal.run import DEFAULT_RNG, Job, Result, run_many

# The seed the shipped mobcal.in carries, at which the 2012 references were run.
DEFAULT_SEED = 5013489
DEFAULT_OUT = Path("runs")


def _seeds(text: str) -> list[int]:
    try:
        seeds = [int(s) for s in text.replace(",", " ").split()]
    except ValueError:
        raise argparse.ArgumentTypeError(f"seeds must be integers: {text!r}") from None
    if not seeds:
        raise argparse.ArgumentTypeError("no seeds given")
    return seeds


def _set_names() -> str:
    """The shipped sets, for the help: ``2012 (He, N2), 2000 (He)``."""
    sets = parameters.SETS
    return ", ".join(f"{n} ({', '.join(parameters.GAS[g] for g in sets if n in sets[g])})"
                     for n in parameters.names())


def expand_inputs(patterns: list[str]) -> list[Path]:
    """Each argument as a path if it exists, else as a glob; duplicates dropped, order kept."""
    found: list[Path] = []
    for pat in patterns:
        matches = [Path(pat)] if os.path.exists(pat) else [Path(m) for m in sorted(glob.glob(pat))]
        if not matches:
            raise FileNotFoundError(f"no input matches {pat!r}")
        found += [m for m in matches if m not in found]
    return found


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mobcal", description="Collision cross sections by the trajectory method: the 2012 "
        "MOBCAL Fortran, run many calculations at a time.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="print the package version")

    c = sub.add_parser("self-check", help="check that this copy can compute a cross section")
    c.add_argument("--choline", action="store_true",
                   help="also run the 2012 choline input in helium and compare (about 3 min)")
    c.add_argument("--report", type=Path, metavar="PATH",
                   help="write the report to this file as well")

    b = sub.add_parser("build", help="compile the 2012 Fortran with gfortran")
    b.add_argument("--gas", choices=fortran.GASES, help="one gas; default both")
    b.add_argument("--out", type=Path, default=ROOT / "build" / "fortran",
                   help="output directory (default build/fortran/)")

    r = sub.add_parser("run", help="run calculations in parallel, one process per run")
    r.add_argument("inputs", nargs="+", metavar="INPUT", help=".mfj files, paths or globs")
    r.add_argument("--gas", choices=(*fortran.GASES, "both"), default="he",
                   help="which binary (default he)")
    r.add_argument("--seeds", type=_seeds, default=[DEFAULT_SEED], metavar="N[,N...]",
                   help=f"one run per seed (default {DEFAULT_SEED}, the 2012 seed)")
    r.add_argument("--rng", choices=sorted(GENERATORS, key=lambda g: g != DEFAULT_RNG),
                   default=DEFAULT_RNG,
                   help=f"random number generator (default {DEFAULT_RNG}); ranlux is the 2012 "
                        "generator, which reproduces the 2012 numbers at the 2012 seed")
    r.add_argument("--workers", type=int, default=None, metavar="N",
                   help="runs in flight at once (default: the number of CPUs)")
    r.add_argument("--split", type=int, default=None, metavar="W",
                   help="run each calculation across W processes, with the serial result "
                        "exactly (default: one process per calculation)")
    r.add_argument("--parameters", default=None, metavar="PATH|NAME",
                   help="the element table for every run: a TOML file, or a shipped set by "
                        f"name ({_set_names()}); default {parameters.DEFAULT}")
    r.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help=f"where the run directories and the summary go (default {DEFAULT_OUT}/)")
    s = r.add_argument_group(
        "run settings", "the temperature and the five sampling counts the 2012 programs "
        "compiled in; without these every run uses the 2012 values (temperature 301 K, imp "
        "1000, itn 10, inp 40, inum 250000, inor 30)")
    s.add_argument("--settings", type=Path, default=None, metavar="PATH",
                   help="a settings file (TOML) for every run; a key it leaves out keeps the "
                        "2012 value")
    s.add_argument("--temperature", type=float, default=None, metavar="T",
                   help="buffer gas temperature in kelvin")
    s.add_argument("--imp", type=int, default=None, metavar="N",
                   help="trajectories per block of the trajectory method")
    s.add_argument("--itn", type=int, default=None, metavar="N",
                   help="cycles of the trajectory method")
    s.add_argument("--inp", type=int, default=None, metavar="N",
                   help="velocity points of the trajectory method")
    s.add_argument("--inum", type=int, default=None, metavar="N",
                   help="trajectories of the projection and hard-sphere pass (helium)")
    s.add_argument("--inor", type=int, default=None, metavar="N",
                   help="reflections followed per hard-sphere trajectory (helium)")

    p = sub.add_parser("render-parameters",
                       help="write the element table and the settings the program reads into "
                            "a directory")
    p.add_argument("gas", choices=fortran.GASES)
    p.add_argument("dir", type=Path, nargs="?", default=Path("."), metavar="DIR",
                   help="where to write parameters.tab and settings.tab (default: the current "
                        "directory)")
    p.add_argument("--parameters", default=None, metavar="PATH|NAME",
                   help="render this TOML file, or this shipped set by name "
                        f"({_set_names()}), instead of the gas's default set")
    p.add_argument("--settings", type=Path, default=None, metavar="PATH",
                   help="render this settings file instead of the 2012 values")
    return ap


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


def _run(args: argparse.Namespace) -> int:
    try:
        inputs = expand_inputs(args.inputs)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    gases = list(fortran.GASES) if args.gas == "both" else [args.gas]
    # A shipped set's name stands for each gas's set of that name; a path, for one gas's table.
    try:
        tables = {gas: parameters.path_for(args.parameters, gas) for gas in gases}
    except parameters.ParameterError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.parameters is not None and args.parameters not in parameters.names():
        try:
            ps = parameters.load(args.parameters)
        except parameters.ParameterError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if gases != [ps.gas]:
            print(f"error: {args.parameters} is a table for {parameters.GAS[ps.gas]}; run it "
                  f"with --gas {ps.gas}", file=sys.stderr)
            return 2
    for gas in gases:
        try:
            fortran.find_binary(gas)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    try:
        st = settings.resolve(args.settings, **{k: getattr(args, k) for k in settings.NAMES})
    except settings.SettingsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    split = args.split
    if split is not None and not 1 <= split <= st.blocks_per_set:
        print(f"error: --split takes a worker count from 1 to {st.blocks_per_set} "
              f"(itn {st.itn} * inp {st.inp} blocks per coordinate set)", file=sys.stderr)
        return 2
    try:
        jobs = [Job(p, gas, seed, args.out, split=split,
                    parameters=tables[gas] if args.parameters is not None else None,
                    generator=args.rng, settings=st)
                for p in inputs for gas in gases for seed in args.seeds]
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    cpus = os.cpu_count() or 1
    workers = max(1, min(args.workers or (cpus // split if split else cpus), len(jobs)))
    changed = " ".join(f"{k}={v:g}" for k, v in st.values().items()
                       if v != getattr(settings.DEFAULTS, k))
    print(f"{len(jobs)} run{'s' if len(jobs) != 1 else ''} on {workers} worker"
          f"{'s' if workers != 1 else ''}" + (f", each across {split} processes" if split else "")
          + f", generator {args.rng}"
          + (f", settings {changed}" if changed else ", the 2012 settings")
          + f", binaries from {fortran.binary_dir()}, output under {args.out}/"
          + (f", element table {args.parameters}" if args.parameters else ""), flush=True)

    def progress(r: Result, done: int, total: int) -> None:
        print(f"[{done}/{total}] {r}", flush=True)

    def blocks(job: Job, n: int, total: int) -> None:
        if n and n % 40 == 0 or n == total:
            print(f"    {job.label}: {n}/{total} blocks", flush=True)

    summary = run_many(jobs, workers, progress, blocks=blocks)
    csv_path, json_path = summary.write(args.out)
    print(f"{summary}; wrote {csv_path} and {json_path}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
