"""The ``mobcal`` command.

    mobcal version
    mobcal build [--gas he|n2] [--out DIR]
    mobcal run INPUT [INPUT ...] [--gas he|n2|both] [--seeds N[,N...]] [--workers N] [--out DIR]

``run`` takes input files (paths or globs), makes one job per input, gas and seed, runs them
``--workers`` at a time through ``mobcal.run``, prints each as it lands, and writes
``summary.csv`` and ``summary.json`` beside the run directories. Its exit status is 1 if any run
failed. The window's ``gui`` arrives with its task. This module imports no Qt.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

from mobcal import ROOT, __version__, fortran
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
    ap = argparse.ArgumentParser(prog="mobcal", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="print the package version")

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
    r.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help=f"where the run directories and the summary go (default {DEFAULT_OUT}/)")

    args = ap.parse_args(argv)

    if args.cmd == "version":
        print(__version__)
        return 0

    if args.cmd == "build":
        problems = fortran.verify_sources()
        if problems:
            print("refusing to build: fortran/ is not the 2012 code", file=sys.stderr)
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
    jobs = [Job(p, gas, seed, args.out) for p in inputs for gas in gases for seed in args.seeds]
    workers = max(1, min(args.workers or os.cpu_count() or 1, len(jobs)))
    print(f"{len(jobs)} run{'s' if len(jobs) != 1 else ''} on {workers} worker"
          f"{'s' if workers != 1 else ''}, binaries from {fortran.binary_dir()}, "
          f"output under {args.out}/", flush=True)

    def progress(r: Result, done: int, total: int) -> None:
        print(f"[{done}/{total}] {r}", flush=True)

    summary = run_many(jobs, workers, progress)
    csv_path, json_path = summary.write(args.out)
    print(f"{summary}; wrote {csv_path} and {json_path}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
