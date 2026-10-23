"""Nitrogen in every session: choline as worker 10 of 10, one cycle against the 2012 reference.

The nitrogen regression gate is about an hour and runs only when asked for (``-m nitrogen``).
This is the part of it that costs a tenth. The 2012 run is ``itn = 10`` cycles of ``inp = 40``
velocity points of ``imp = 1000`` trajectories, and a split run deals block
k = (ig - 1)*itn + ic to worker (k - 1) mod W + 1, so worker 10 of 10 integrates the 40 blocks
of cycle 10, 40,000 trajectories, and draws the other 360 blocks through without integrating
them. Its per-cycle table prints cycle 10's own cross section and Ko^-1 (columns 1 and 3;
columns 2 and 4 are running averages) from exactly the trajectories the 2012 run integrated
for that cycle, and zeros for the nine others. The binary is the session pool's, and the run
starts before the pool's helium batch and is waited for after it (``conftest.py``).

Checked, with no tolerance:

- **T1**, as the gate's: every line no pattern in ``stochastic-lines.txt`` matches equals the
  reference's, with the worker's ``blocks of imp trajectories`` line left out as well. These
  are the lines the element table, the geometry, the velocity grid and the b2max search reach.
- **Cycle 10's row**: columns 1 and 3 equal the reference's as printed, which takes the
  generator's state after nine cycles of draws and the integration of cycle 10 both exact.
- **The share**: the worker integrated 40 blocks and left 360 empty, and rows 1 to 9 are zero.

Left to the ``nitrogen``-marked gate: T2 and T3, which is the SUMMARY's cross section, the other
nine cycles, the q1st table, the moments, ``f`` and the failure count; and the serial path
itself, since this run's ``mobcal.in`` carries the fourth record. That drawing a block through
leaves the stream where integrating it would is ``test_split.py``'s, in helium.
"""

from __future__ import annotations

import difflib
import re

import pytest

import gate
from mobcal.io.block import BLOCKS_PER_SET
from mobcal.io.outfile import OutFile

ROW = re.compile(r"^ +(\d+) +(\S+) +(\S+) +(\S+) +(\S+)$")
ZERO = "0.0000E+00"


@pytest.fixture(scope="module")
def n2_cycle(pool) -> gate.WorkerRun:
    r = pool.cycles["n2"]
    assert r.returncode == 0 and r.out is not None and r.out.ok, \
        f"exit {r.returncode}: {r.out.last_line if r.out else 'no output'}\n{r.log}"
    return r


def cycles(out: OutFile) -> dict[int, tuple[str, str]]:
    """The per-cycle table: each cycle's own cross section and Ko^-1, as printed."""
    head = out.lines.index(next(x for x in out.lines if x.startswith(" cycle ")))
    rows = {}
    for line in out.lines[head + 1:]:
        m = ROW.match(line)
        if not m:
            break
        rows[int(m[1])] = (m[2], m[4])
    return rows


def test_t1_deterministic_lines(n2_cycle):
    patterns = gate.stochastic_patterns() + [gate.PROVENANCE]
    ref = gate.deterministic(n2_cycle.ref.lines, patterns)
    new = gate.deterministic(n2_cycle.out.lines, patterns)
    assert new == ref, "deterministic lines differ:\n" + "\n".join(
        difflib.unified_diff(ref, new, "reference", "worker 10 of 10", lineterm=""))


def test_cycle_10_is_the_references(n2_cycle):
    W, me = gate.CYCLE
    ref, new = cycles(n2_cycle.ref), cycles(n2_cycle.out)
    assert sorted(ref) == sorted(new) == list(range(1, W + 1))
    assert new[me] == ref[me]


def test_the_worker_integrated_cycle_10_alone(n2_cycle):
    W, me = gate.CYCLE
    mine = BLOCKS_PER_SET // W
    assert gate.provenance(mine, 0, BLOCKS_PER_SET - mine, me, W) in n2_cycle.out.lines
    assert {c: v for c, v in cycles(n2_cycle.out).items() if c != me} == \
        {c: (ZERO, ZERO) for c in range(1, W + 1) if c != me}
