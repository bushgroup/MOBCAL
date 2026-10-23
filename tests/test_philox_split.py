"""Under Philox a split calculation reproduces the serial one, by construction, and a block
file from the other generator is refused.

With the word ``philox`` on the seed record the program draws from Philox4x32-10, whose draw n
is a function of the seed and n alone, so a worker reaches each of its blocks by moving the
draw count past the others instead of drawing through them. The pool runs choline in helium
under Philox serially and split W = 10 and W = 40 ways, and the combining run's output must
equal the serial run's on every line but the per-process ones (the ``energy not conserved``
pairs and the ``blocks of imp trajectories`` line, removed from both as ``test_split.py``
removes them for RANLUX): the per-cycle table, the moments, the mobility, the cross section
and the SUMMARY, with no tolerance. W = 40 is ten blocks per worker, the share a workstation
run uses, and the seek's own case: at RANLUX a worker of forty draws through 390 blocks.

The serial Philox run is also held to the 2012 reference on every deterministic line but the
two that name the generator and its seed: the orientation, the velocity grid and the b2max
search draw nothing, so they are the reference's under either generator, and the cross sections
agree within the method's own scatter while the sample is a different one.

The block file's fifth integer is the generator, and the program accepts no block drawn from the
other generator's stream: a combining run under one generator that finds a block written under
the other stops at it, exit 1, naming the block and the generator it found.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from collections import Counter

import pytest

import gate
from mobcal import parameters
from mobcal.io.block import BLOCKS_PER_SET, Block
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile
from mobcal.run import OUTPUT_NAME
from test_split import diagnostics, failed_count, shared

SEED_LINES = [re.compile(p) for p in
              (r"^ using RANLUX", r"^ RANLUX ", r"^ using Philox4x32-10 with seed integer =")]
SCATTER = 0.02  # the two generators' cross sections agree to within this, relative


def _diff(a: list[str], b: list[str]) -> str:
    return "\n".join(difflib.unified_diff(a, b, "serial", "combined", lineterm=""))


@pytest.mark.parametrize("WP", [10, 40])
def test_a_philox_split_run_reproduces_the_philox_serial_run(pool, WP):
    serial = OutFile.read(pool.philox[0].output)
    r = pool.philox[WP]
    assert r.ok, r.message
    combined = OutFile.read(r.output)

    a, b = shared(serial.lines), shared(combined.lines)
    assert a == b, _diff(a, b)
    assert combined.cross_sections == serial.cross_sections
    assert combined.generator == serial.generator == "philox"
    assert gate.provenance(0, BLOCKS_PER_SET, 0, 0, WP) in combined.lines

    seen = diagnostics(combined.lines)
    conserved = Counter(seen)
    for w in range(1, WP + 1):
        worker = OutFile.read(r.job.worker_dir(w) / OUTPUT_NAME)
        assert worker.generator == "philox"
        conserved += diagnostics(worker.lines) - seen
    assert conserved == diagnostics(serial.lines)

    blocks = [Block.read(p) for p in sorted(r.job.run_dir.glob("block-*.dat"))]
    assert len(blocks) == BLOCKS_PER_SET
    assert {b.generator for b in blocks} == {"philox"} and {b.seed for b in blocks} == {5013489}
    assert sum(b.failures for b in blocks) == failed_count(serial) - len(list(seen.elements()))


@pytest.mark.parametrize("WP", [0])  # the serial Philox run, which the pool runs for WP = 0
def test_the_philox_serial_run_is_the_reference_on_every_deterministic_line_but_the_seeds(
        pool, WP):
    ref = pool.runs["he"].ref
    ranlux = pool.runs["he"].new
    philox = OutFile.read(pool.philox[0].output)
    assert philox.ok and philox.seed == ranlux.seed == ref.seed
    assert philox.generator == "philox" and ranlux.generator == "ranlux"
    line = " using Philox4x32-10 with seed integer = 5013489"
    assert philox.lines.count(line) == 2  # the banner and the SUMMARY
    assert not any("RANLUX" in x for x in philox.lines)

    # Blank lines are left out of this comparison: RANLUX's banner is followed by rluxgo's own
    # lines and Philox's is not, and the gate's rule drops the blank before each dropped line,
    # so the two sides keep different numbers of blanks around the lines removed here.
    patterns = gate.stochastic_patterns() + SEED_LINES
    a = [x for x in gate.deterministic(ref.lines, patterns) if x.strip()]
    b = [x for x in gate.deterministic(philox.lines, patterns) if x.strip()]
    assert a == b, _diff(a, b)

    # A different sample of the same quantities: not the RANLUX numbers, but within scatter.
    assert philox.cross_sections.keys() == ranlux.cross_sections.keys()
    assert philox.cross_sections != ranlux.cross_sections
    for k, v in ranlux.cross_sections.items():
        assert abs(philox.cross_sections[k] - v) <= SCATTER * v, (k, v, philox.cross_sections[k])


@pytest.mark.parametrize("written, combining", [("ranlux", "philox"), ("philox", "ranlux")])
def test_a_block_from_the_other_generator_is_refused(pool, tmp_path, written, combining):
    # A combining run of choline, W = 2, that finds block 1 written under the other generator:
    # the b2max search runs (seconds), then the first block's file is read and refused.
    d = tmp_path
    (d / "Choline.mfj").write_bytes(gate.CHOLINE.read_bytes())
    InFile("Choline.mfj", "out.txt", 5013489, (2, 0), combining).write(d)
    parameters.shipped("he").render(d)
    Block(1, 1, 1, 5013489, 0.5, 0.5, 0, written).write(d)
    proc = subprocess.run([str(pool.binaries["he"])], cwd=d, capture_output=True, timeout=300,
                          stdin=subprocess.DEVNULL)
    out = OutFile.read(d / "out.txt")
    assert proc.returncode == 1, (proc.returncode, out.last_line)
    code = {"ranlux": 1, "philox": 2}[written]
    assert out.last_line == ("file block-001-0001.dat   is not this block: set   1 cycle  1 "
                             f"point  1 seed   5013489 generator {code}")
    assert not out.ok
