"""The claimed dealing through the real binaries: a split run whose workers claim blocks as they
reach them gives the serial output to the byte, under both generators and both walks.

With ``W w claim`` on the fourth record a worker takes every block it is the first to claim,
creating ``../claim-<set>-<k>`` exclusively before each block, instead of its fixed share. At
RANLUX it walks the blocks in stream order, cycle-major; at Philox point-major, the slowest
velocity point's blocks first, seeking the draw count to each block it wins. Either way a block's
two sums depend on its index and the generator state at its start, not on who integrates it, so
the combining run's output must equal the serial run's on every line but the per-process ones
(``test_split.shared``): the ``energy not conserved`` pairs, the ``blocks of imp trajectories``
line and the ``blocks claimed`` line.

The cheap cases run choline in helium at small settings in every session with gfortran: 21
blocks of 100 trajectories on four workers under both generators; 6 blocks on six workers, as
many as the driver allows; and the forced-contention case, 400 blocks of one trajectory raced
by forty workers, where every block must be claimed and written exactly once and every claim
file must
name the worker whose directory holds the block, the exclusive create's test on this platform.
The 2012-settings case, W = 3 under both generators against the pool's serial runs, is the
claimed counterpart of ``test_split.py``'s W = 3 and ``test_philox_split.py``'s runs. Nitrogen
at W = 10 is behind the ``nitrogen`` marker with the serial nitrogen gate it compares with.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter

import pytest

import gate
from mobcal.io.block import BLOCKS_PER_SET, Block, all_names, block_of_claim
from mobcal.io.outfile import OutFile
from mobcal.run import OUTPUT_NAME, Job, run_many, run_one
from mobcal.settings import DEFAULTS
from test_split import diagnostics, failed_count, shared

CLAIMED = " blocks claimed as reached, visited "
WALK = {"ranlux": "cycle", "philox": "point"}


def _diff(a: list[str], b: list[str]) -> str:
    return "\n".join(difflib.unified_diff(a, b, "serial", "claimed", lineterm=""))


def check_claimed(r, serial: OutFile, generator: str, sets: int = 1) -> None:
    """What every claimed run must show: the serial lines, every block claimed and written
    exactly once by the worker that claimed it, the walk the generator sets, the diagnostics
    conserved."""
    assert r.ok, r.message
    combined = OutFile.read(r.output)
    a, b = shared(serial.lines), shared(combined.lines)
    assert a == b, _diff(a, b)
    assert combined.cross_sections == serial.cross_sections
    job, d = r.job, r.job.run_dir
    every = all_names(sets, job.settings.blocks_per_set)
    claims = sorted(p.name for p in d.glob("claim-*"))
    assert [block_of_claim(c) for c in claims] == every
    owners = {block_of_claim(c): int((d / c).read_text(encoding="ascii")) for c in claims}
    written: Counter[str] = Counter()
    seen = diagnostics(combined.lines)
    conserved = Counter(seen)
    for w in range(1, job.split + 1):
        wd = job.worker_dir(w)
        mine = [p.name for p in wd.glob("block-*.dat")]
        written.update(mine)
        assert all(owners[n] == w for n in mine), (w, mine[:3])
        worker = OutFile.read(wd / OUTPUT_NAME)
        assert CLAIMED + WALK[generator] + "-major" in worker.lines
        conserved += diagnostics(worker.lines) - seen
    assert written == Counter(every)
    assert conserved == diagnostics(serial.lines)
    # the record's harvest says the same as the files: the claim map, each worker's blocks and
    # the diagnostics the workers printed
    split = json.loads((d / "record.json").read_text(encoding="utf-8"))["split"]
    harvested = {n: int(w) for s_, row in enumerate(split["claims"], 1)
                 for n, w in zip([n for n in every if n.startswith(f"block-{s_:03d}-")],
                                 row.split(), strict=True)}
    assert harvested == owners
    assert [e["blocks"] for e in split["workers"]] == [
        len(list(job.worker_dir(w).glob("block-*.dat"))) for w in range(1, job.split + 1)]
    from_record = Counter(seen)
    for w in range(1, job.split + 1):
        mine = [ln for e in split["diagnostics"] if e["worker"] == w for ln in e["lines"]]
        from_record += diagnostics(mine) - seen
    assert from_record == conserved
    blocks = [Block.read(p) for p in sorted(d.glob("block-*.dat"))]
    assert [b.name for b in blocks] == every
    assert {b.generator for b in blocks} == {generator}
    assert sum(b.failures for b in blocks) == failed_count(serial) - len(list(seen.elements()))


def _pair(tmp_path, generator: str, settings, W: int, launcher):
    jobs = [Job(gate.CHOLINE, "he", 5013489, tmp_path, name="serial", generator=generator,
                settings=settings),
            Job(gate.CHOLINE, "he", 5013489, tmp_path, name="claimed", generator=generator,
                settings=settings, split=W, dealing="claimed", scratch="keep")]
    serial, claimed = run_many(jobs, workers=2, launcher=launcher).results
    assert serial.ok, serial.message
    return OutFile.read(serial.output), claimed


@pytest.mark.parametrize("generator", ["ranlux", "philox"])
def test_a_claimed_run_at_small_settings_reproduces_the_serial_run(pool, tmp_path, generator):
    s = DEFAULTS.replace(itn=3, inp=7, imp=100)  # 21 blocks of 100 trajectories: seconds
    serial, r = _pair(tmp_path, generator, s, 4, pool.launcher)
    check_claimed(r, serial, generator)
    assert gate.provenance(0, 21, 0, 0, 4) in OutFile.read(r.output).lines


@pytest.mark.parametrize("generator", ["ranlux", "philox"])
def test_as_many_workers_as_blocks(pool, tmp_path, generator):
    # 6 blocks on 6 workers, the most the driver allows (Job bounds W by itn * inp): a worker
    # claims one block, or two when it reaches the next before a slower worker does, and a
    # worker that finds every block claimed integrates nothing and is fine.
    s = DEFAULTS.replace(itn=2, inp=3, imp=50)
    serial, r = _pair(tmp_path, generator, s, 6, pool.launcher)
    check_claimed(r, serial, generator)
    counts = sorted(len(list(r.job.worker_dir(w).glob("block-*.dat"))) for w in range(1, 7))
    assert sum(counts) == 6 and counts[-1] >= 1


@pytest.mark.parametrize("generator", ["ranlux", "philox"])
def test_forced_contention_claims_every_block_exactly_once(pool, tmp_path, generator):
    # A block of one trajectory is microseconds, so forty workers race for 400 claims at once:
    # the exclusive create under contention, through the real binary, on this platform.
    s = DEFAULTS.replace(imp=1)
    serial, r = _pair(tmp_path, generator, s, 40, pool.launcher)
    check_claimed(r, serial, generator)
    counts = [len(list(r.job.worker_dir(w).glob("block-*.dat"))) for w in range(1, 41)]
    assert sum(counts) == BLOCKS_PER_SET


@pytest.mark.parametrize("WP", [0])  # asks the pool for the serial Philox run as well
def test_a_claimed_run_at_the_2012_settings_reproduces_the_serial_run(pool, tmp_path, WP):
    jobs = [Job(gate.CHOLINE, "he", 5013489, tmp_path, name=f"claimed-{g}", generator=g,
                split=3, dealing="claimed", staged_name=pool.runs["he"].ref.input_name,
                scratch="keep")
            for g in ("ranlux", "philox")]
    ranlux, philox = run_many(jobs, workers=2, launcher=pool.launcher).results
    check_claimed(ranlux, pool.runs["he"].new, "ranlux")
    check_claimed(philox, OutFile.read(pool.philox[WP].output), "philox")
    for r in (ranlux, philox):
        assert gate.provenance(0, BLOCKS_PER_SET, 0, 0, 3) in OutFile.read(r.output).lines
        counts = [len(list(r.job.worker_dir(w).glob("block-*.dat"))) for w in (1, 2, 3)]
        assert sum(counts) == BLOCKS_PER_SET and min(counts) > 0


@pytest.mark.nitrogen
@pytest.mark.parametrize("choline", ["n2"])  # asks the pool for the serial nitrogen gate run
def test_a_claimed_nitrogen_run_reproduces_the_serial_run(pool, tmp_path, choline):
    ref = pool.runs["n2"]
    r = run_one(Job(gate.CHOLINE, "n2", ref.ref.seed, tmp_path, name="claimed-n2",
                    generator=ref.ref.generator, split=10, dealing="claimed",
                    staged_name=ref.ref.input_name, scratch="keep"), pool.launcher)
    check_claimed(r, ref.new, ref.ref.generator)
