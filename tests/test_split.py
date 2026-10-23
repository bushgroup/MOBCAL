"""One calculation across W processes gives the serial output, to the byte, where it can.

The combining run's output is compared with the serial run's from the same binary, in the same
session (the pool fixture runs both). Two kinds of line are the only ones allowed to differ,
and they are removed from both sides before the comparison: the ``energy not conserved``
diagnostic pairs, each with the blank line it opens with, which are printed by whichever
process integrated the failing trajectory; and the one ``blocks of imp trajectories`` line the
program adds when the run file carries the fourth record. Everything else, the per-cycle table,
the q1st table, the mean, the standard deviation, the moments, the mobility, the cross section
and the SUMMARY's failure count, must be identical. No tolerance: a moved digit fails.

The diagnostics are then checked to be conserved: the serial run's, as a multiset, equal the
combining run's (which repeats the b2max search, where the only trajectories it integrates are)
plus each worker's beyond those.

W = 1 is the block files' round trip; W = 3 is uneven shares (134, 133, 133 blocks) and three
interleaved streams. Both run in every session with gfortran. Larger W and nitrogen split runs
are measured in the lab record and are not CI's business; ``test_nitrogen_cycle.py`` runs one
nitrogen worker alone against the 2012 reference.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter

import pytest

import gate
from mobcal.io.block import BLOCKS_PER_SET, Block, expected_names
from mobcal.io.outfile import OutFile
from mobcal.run import OUTPUT_NAME, Job, run_many, run_one

ENERGY = [re.compile(r"^ energy not conserved:"), re.compile(r"^ gst2 = .*theta = ")]


def shared(lines: list[str]) -> list[str]:
    """The lines a combining run and a serial run must agree on."""
    return gate.deterministic(lines, ENERGY + [gate.PROVENANCE])


def diagnostics(lines: list[str]) -> Counter[str]:
    """The energy-conservation diagnostics, each pair as one string."""
    pairs = [lines[i] + "\n" + lines[i + 1] for i in range(len(lines) - 1)
             if ENERGY[0].search(lines[i]) and ENERGY[1].search(lines[i + 1])]
    return Counter(pairs)


def failed_count(out: OutFile) -> int:
    line = [x for x in out.lines if x.startswith(" number of failed trajectories =")][-1]
    return int(line.split("=")[1])


@pytest.mark.parametrize("W", [1, 3])
def test_a_split_run_reproduces_the_serial_output(pool, W):
    serial = pool.runs["he"].new
    r = pool.splits[W]
    assert r.ok, r.message
    combined = OutFile.read(r.output)

    a, b = shared(serial.lines), shared(combined.lines)
    assert a == b, "\n".join(difflib.unified_diff(a, b, "serial", f"W={W}", lineterm=""))
    assert combined.cross_sections == serial.cross_sections
    assert gate.provenance(0, BLOCKS_PER_SET, 0, 0, W) in combined.lines

    seen = diagnostics(combined.lines)
    conserved = Counter(seen)
    for w in range(1, W + 1):
        worker = OutFile.read(r.job.worker_dir(w) / OUTPUT_NAME)
        mine = len(expected_names(1, W, w))
        assert gate.provenance(mine, 0, BLOCKS_PER_SET - mine, w, W) in worker.lines
        conserved += diagnostics(worker.lines) - seen
    assert conserved == diagnostics(serial.lines)

    blocks = [Block.read(p) for p in sorted(r.job.run_dir.glob("block-*.dat"))]
    assert len(blocks) == BLOCKS_PER_SET
    assert [b.k for b in blocks] == list(range(1, BLOCKS_PER_SET + 1))
    assert [(b.cycle, b.point) for b in blocks] == [Block.cycle_point(k) for k in range(1, 401)]
    assert {b.seed for b in blocks} == {serial.seed} and {b.coordinate_set for b in blocks} == {1}
    assert sum(b.failures for b in blocks) == failed_count(serial) - len(list(seen.elements()))
    assert all(b.temp1 > 0 and b.temp2 > 0 for b in blocks)


@pytest.mark.long
def test_a_split_run_with_two_coordinate_sets(pool, tmp_path):
    # Choline doubled into two identical sets: set 2's trajectories continue the one random
    # stream after set 1's, so this is the draw-through carrying the stream across sets. The
    # serial two-set run is about twice the helium gate, hence the marker.
    lines = gate.CHOLINE.read_text(encoding="latin-1").splitlines()
    assert lines[1].strip() == "1"
    atoms = lines[6:6 + int(lines[2])]
    two = tmp_path / "two.mfj"
    two.write_text("\n".join([lines[0], "2", *lines[2:6], *atoms, "", *atoms]) + "\n",
                   encoding="latin-1", newline="\n")
    jobs = [Job(two, "he", 5013489, tmp_path, name="serial"),
            Job(two, "he", 5013489, tmp_path, name="split", split=3)]
    serial, split = run_many(jobs, workers=2, launcher=pool.launcher).results
    assert serial.ok and split.ok, (serial.message, split.message)
    assert len(serial.conformers) == 2 and split.conformers == serial.conformers
    a, b = shared(OutFile.read(serial.output).lines), shared(OutFile.read(split.output).lines)
    assert a == b, "\n".join(difflib.unified_diff(a, b, "serial", "W=3", lineterm=""))
    assert len(list(split.job.run_dir.glob("block-*.dat"))) == 2 * BLOCKS_PER_SET


def test_a_run_that_reaches_the_failure_cap_fails_split_as_it_fails_serial(pool, tmp_path):
    # Water: the trajectories fail energy conservation almost every time, the helium program
    # stops at the hundredth with no SUMMARY and exit 1, and the driver calls that failed.
    # Split, a worker reaches the cap on its own blocks and stops short of writing them, or the
    # combining run's sum reaches it; either way there is no SUMMARY and no number.
    water = tmp_path / "water.mfj"
    water.write_text("H2O+\n1\n3\nang\ncalc\n1.0000\n 0.0000  0.0000  0.1173 16 0.0\n"
                     " 0.0000  0.7572 -0.4692  1 0.5\n 0.0000 -0.7572 -0.4692  1 0.5\n",
                     encoding="latin-1", newline="\n")
    serial = run_one(Job(water, "he", 5013489, tmp_path, name="serial"), pool.launcher)
    assert not serial.ok and serial.returncode == 1
    assert serial.message.startswith("exit 1"), serial.message
    split = run_one(Job(water, "he", 5013489, tmp_path, name="split", split=2), pool.launcher)
    assert not split.ok and split.cross_sections == {}
    assert "blocks missing" in split.message or "reached ifail" in split.message, split.message
