"""The all-elements probe input: one atom per row of a gas's element table, twice.

Choline exercises four rows of each table and one coordinate set. This input exercises every
row and both coordinate readers: one atom per key the table defines, on a 1.6 Å grid, equal
partial charges summing to one, and the same set given twice so that the second is read by
``ncoord``. Run as worker 400 of 400 (the fourth record of ``mobcal.in``), the program
integrates one block of ``imp`` trajectories per set instead of 400, and reaches the SUMMARY
of both sets in seconds; every line it prints is a function of the seed, the input and the
parameters alone, so the whole output compares byte for byte between two builds.

``tests/elements/`` holds the outputs the programs built from the 2012 chains wrote for these
inputs; ``test_elements.py`` holds the programs that read the rendered table to them.
"""

from __future__ import annotations

from mobcal import parameters
from mobcal.io.block import BLOCKS_PER_SET

SEED = 5013489
# The fixtures were captured under the 2012 generator, so the run file carries no generator
# word: the program's own default, RANLUX, whatever the driver's default is.
GENERATOR = "ranlux"
WORKER = (BLOCKS_PER_SET, BLOCKS_PER_SET)  # the last worker of 400: one block per set
INPUT = "probe.mfj"  # the name the output echoes, so the fixtures carry it
OUTPUT = "out.txt"
SPACING = 1.6  # Å between grid neighbours


def all_elements(gas: str, drop: tuple[int, ...] = ()) -> str:
    """The ``.mfj`` text: every key of the shipped table for ``gas`` but those in ``drop``."""
    keys = [k for k in parameters.shipped(gas).keys if k not in drop]
    n = len(keys)
    rows = []
    for i, k in enumerate(keys):
        x, y, z = (SPACING * (i % 3), SPACING * ((i // 3) % 3), SPACING * (i // 9))
        rows.append(f" {x:8.4f} {y:8.4f} {z:8.4f} {k:4d} {1.0 / n:8.4f}")
    body = "\n".join(rows)
    label = f"all elements {gas}" + (f" without {' '.join(map(str, drop))}" if drop else "")
    return f"{label}\n2\n{n}\nang\ncalc\n1.0000\n{body}\n\n{body}\n"


def run_file() -> str:
    """``mobcal.in`` for a probe run: the input, the output, the seed, the worker record."""
    return f"{INPUT}\n{OUTPUT}\n{SEED}\n{WORKER[0]} {WORKER[1]}\n"


# The inputs the fixtures were captured for: (fixture stem, gas, keys left out).
INPUTS = {"he": ("he", ()), "n2": ("n2", ()), "n2-no-si": ("n2", (28,))}
