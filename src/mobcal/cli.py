"""The ``mobcal`` command.

    mobcal version
    mobcal build [--gas he|n2] [--out DIR]

The driver's ``run`` and the window's ``gui`` arrive with their tasks. This module imports no Qt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mobcal import ROOT, __version__, fortran


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mobcal", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="print the package version")

    b = sub.add_parser("build", help="compile the 2012 Fortran with gfortran")
    b.add_argument("--gas", choices=fortran.GASES, help="one gas; default both")
    b.add_argument("--out", type=Path, default=ROOT / "build" / "fortran",
                   help="output directory (default build/fortran/)")

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

    return 1


if __name__ == "__main__":
    sys.exit(main())
