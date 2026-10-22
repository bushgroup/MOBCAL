"""The ``mobcal`` command.

    mobcal version
    mobcal self-check [--choline] [--report PATH]
    mobcal build [--gas he|n2] [--out DIR]
    mobcal run INPUT [INPUT ...] [--gas he|n2|both] [--seeds N[,N...]] [--workers N]
               [--split W] [--out DIR]

``run`` takes input files (paths or globs), makes one job per input, gas and seed, runs them
``--workers`` at a time through ``mobcal.run``, prints each as it lands, and writes
``summary.csv`` and ``summary.json`` beside the run directories. With ``--split W`` each
calculation runs across W processes and reports the serial result exactly. Its exit status is
1 if any run failed. ``self-check`` is ``mobcal.selfcheck``. ``build`` needs a source checkout;
an installed copy carries binaries built in CI. The window's ``gui`` arrives with its task.
This module imports no Qt.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

from mobcal import ROOT, __version__, fortran
from mobcal.io.block import BLOCKS_PER_SET
from mobcal.run import Job, Result, run_many

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


def expand_inputs(patterns: list[str]) -> list[Path]:
    """Each argument as a path if it exists, else as a glob; duplicates dropped, order kept."""
    found: list[Path] = []
    for pat in patterns:
        matches = [Path(pat)] if os.path.exists(pat) else [Path(m) for m in sorted(glob.glob(pat))]
        if not matches:
            raise FileNotFoundError(f"no input matches {pat!r}")
        found += [m for m in matches if m not in found]
    return found


def main(argv: list[str] | None = None) -> int:
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
    r.add_argument("--workers", type=int, default=None, metavar="N",
                   help="runs in flight at once (default: the number of CPUs)")
    r.add_argument("--split", type=int, default=None, metavar="W",
                   help="run each calculation across W processes, with the serial result "
                        "exactly (default: one process per calculation)")
    r.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help=f"where the run directories and the summary go (default {DEFAULT_OUT}/)")

    args = ap.parse_args(argv)

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

    return 1


def _run(args: argparse.Namespace) -> int:
    try:
        inputs = expand_inputs(args.inputs)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    gases = list(fortran.GASES) if args.gas == "both" else [args.gas]
    for gas in gases:
        try:
            fortran.find_binary(gas)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    split = args.split
    if split is not None and not 1 <= split <= BLOCKS_PER_SET:
        print(f"error: --split takes a worker count from 1 to {BLOCKS_PER_SET}", file=sys.stderr)
        return 2
    try:
        jobs = [Job(p, gas, seed, args.out, split=split)
                for p in inputs for gas in gases for seed in args.seeds]
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    cpus = os.cpu_count() or 1
    workers = max(1, min(args.workers or (cpus // split if split else cpus), len(jobs)))
    print(f"{len(jobs)} run{'s' if len(jobs) != 1 else ''} on {workers} worker"
          f"{'s' if workers != 1 else ''}" + (f", each across {split} processes" if split else "")
          + f", binaries from {fortran.binary_dir()}, output under {args.out}/", flush=True)

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
