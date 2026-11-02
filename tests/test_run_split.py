"""mobcal.run with ``split``, through the stand-in binary: the worker directories, the block
files, the combining run, progress, a worker that leaves a block unwritten, and the claimed
dealing: the claim files, the judgement (a claimed block not written, a block never claimed, a
block written twice) and stale claims."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from mobcal.io.block import BLOCKS_PER_SET, Block, block_of_claim, claim_name, expected_names
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile
from mobcal.run import Job, run_many, run_one
from test_run import launcher, write_input

FAKE = Path(__file__).resolve().parent / "fake_mobcal.py"


def test_a_split_job_runs_its_workers_then_the_combining_run(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "he", 5013489, tmp_path / "runs", split=3, dealing="static")
    seen: list[tuple[int, int]] = []
    r = run_one(job, launcher, blocks=lambda j, n, t: seen.append((n, t)))
    assert r.ok and r.message == "" and r.returncode == 0, r.message
    tm = 50 + 5013489 % 7 + 0.5  # the stand-in's Philox half
    assert r.cross_sections == {"PA": tm + 5.5, "EHS": tm + 8, "TM": tm}  # the serial numbers

    d = job.run_dir
    assert r.output == d / "mobcal.out"
    assert InFile.read(d / "mobcal.in") == InFile("ok.mfj", "mobcal.out", 5013489, (3, 0),
                                                  "philox")
    assert (d / "ok.mfj").read_bytes() == inp.read_bytes()
    assert len(list(d.glob("block-*.dat"))) == BLOCKS_PER_SET
    combined = OutFile.read(r.output)
    assert any(x.startswith(" blocks of imp trajectories: integrated    0, read from files  400,")
               for x in combined.lines)
    for w in (1, 2, 3):
        wd = job.worker_dir(w)
        assert wd == d / f"w0{w}"
        assert InFile.read(wd / "mobcal.in") == InFile("ok.mfj", "mobcal.out", 5013489, (3, w),
                                                       "philox")
        names = expected_names(1, 3, w)
        assert sorted(p.name for p in wd.glob("block-*.dat")) == sorted(names)
        b = Block.read(wd / names[0])
        assert b.seed == 5013489 and b.coordinate_set == 1 and b.generator == "philox"
        assert (wd / "stdout.log").is_file()
        assert OutFile.read(wd / "mobcal.out").ok  # a worker's partial summary, not a result
    assert seen and seen[-1] == (BLOCKS_PER_SET, BLOCKS_PER_SET)
    assert all(t == BLOCKS_PER_SET for _, t in seen) and [n for n, _ in seen] == sorted(
        n for n, _ in seen)


def test_a_split_job_with_several_coordinate_sets(tmp_path):
    job = Job(write_input(tmp_path / "two.mfj", "sets 2"), "he", 7, tmp_path, split=2,
              dealing="static")
    r = run_one(job, launcher)
    assert r.ok and len(r.conformers) == 2
    assert len(list(job.run_dir.glob("block-*.dat"))) == 2 * BLOCKS_PER_SET
    assert len(list(job.worker_dir(1).glob("block-002-*.dat"))) == BLOCKS_PER_SET // 2


def test_a_worker_that_leaves_a_block_unwritten_fails_the_run(tmp_path):
    job = Job(write_input(tmp_path / "x.mfj", "lazy"), "he", 1, tmp_path, split=2, dealing="static")
    r = run_one(job, launcher)
    assert not r.ok and r.output is None and r.cross_sections == {}
    assert r.message.startswith("worker 2: 1 of 200 blocks missing ("), r.message
    assert not (job.run_dir / "mobcal.out").exists()  # the combining run never started


def test_stale_blocks_are_removed_before_a_run(tmp_path):
    job = Job(write_input(tmp_path / "x.mfj", "ok"), "he", 1, tmp_path, split=2)
    assert run_one(job, launcher).ok
    stray = Block(1, 1, 1, 999, 0.0, 0.0, 0).write(job.run_dir)
    stray_w = Block(1, 1, 1, 999, 0.0, 0.0, 0).write(job.worker_dir(1))
    assert run_one(job, launcher).ok
    assert Block.read(stray).seed == 1 and Block.read(stray_w).seed == 1


def test_split_bounds():
    with pytest.raises(ValueError, match="worker count from 1 to 400"):
        Job(Path("x.mfj"), "he", 1, Path("runs"), split=0)
    with pytest.raises(ValueError, match="worker count from 1 to 400"):
        Job(Path("x.mfj"), "he", 1, Path("runs"), split=401)
    assert Job(Path("x.mfj"), "he", 1, Path("runs"), split=400).split == 400


def test_run_many_takes_split_jobs_and_reports_their_blocks(tmp_path):
    jobs = [Job(write_input(tmp_path / f"in{i}.mfj", "ok"), "he", 10 + i, tmp_path / "runs",
                split=2 if i else None) for i in range(2)]
    blocks: list[str] = []
    s = run_many(jobs, workers=2, launcher=launcher, blocks=lambda j, n, t: blocks.append(j.label))
    assert [r.ok for r in s.results] == [True, True]
    assert set(blocks) == {"in1-he-11"}
    _, json_path = s.write(tmp_path / "runs")
    text = json_path.read_text(encoding="utf-8")
    assert '"split": null' in text and '"split": 2' in text
    assert str(s.results[1]).endswith("(2 workers)")


@pytest.mark.parametrize("generator", ["ranlux", "philox"])
def test_a_claimed_split_job_gives_the_serial_result(tmp_path, generator):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    serial = run_one(Job(inp, "he", 5013489, tmp_path / "serial", generator=generator), launcher)
    job = Job(inp, "he", 5013489, tmp_path / "runs", split=3, generator=generator,
              dealing="claimed")
    seen: list[tuple[int, int]] = []
    r = run_one(job, launcher, blocks=lambda j, n, t: seen.append((n, t)))
    assert r.ok and r.message == "", r.message
    assert r.cross_sections == serial.cross_sections
    d = job.run_dir
    assert InFile.read(d / "mobcal.in") == InFile("ok.mfj", "mobcal.out", 5013489, (3, 0),
                                                  generator)  # the combining run never claims
    for w in (1, 2, 3):
        assert InFile.read(job.worker_dir(w) / "mobcal.in") == InFile(
            "ok.mfj", "mobcal.out", 5013489, (3, w), generator, "claimed")
    # every block claimed once, and written once by the worker that claimed it
    claims = sorted(p.name for p in d.glob("claim-*"))
    assert claims == [claim_name(1, k) for k in range(1, BLOCKS_PER_SET + 1)]
    owners = {block_of_claim(c): int((d / c).read_text()) for c in claims}
    written = {p.name: w for w in (1, 2, 3) for p in job.worker_dir(w).glob("block-*.dat")}
    assert written == owners
    assert len(list(d.glob("block-*.dat"))) == BLOCKS_PER_SET
    walk = "point" if generator == "philox" else "cycle"
    for w in (1, 2, 3):
        out = OutFile.read(job.worker_dir(w) / "mobcal.out")
        assert f" blocks claimed as reached, visited {walk}-major" in out.lines
    assert seen and seen[-1] == (BLOCKS_PER_SET, BLOCKS_PER_SET)
    rec = json.loads((d / "record.json").read_text(encoding="utf-8"))
    assert rec["mobcal_in"] == {"seed": 5013489, "generator": generator, "split": 3,
                                "dealing": "claimed"}


def test_a_claimed_block_a_worker_never_writes_fails_the_run(tmp_path):
    job = Job(write_input(tmp_path / "x.mfj", "lazy"), "he", 1, tmp_path, split=2,
              dealing="claimed")
    r = run_one(job, launcher)
    assert not r.ok and r.output is None
    assert r.message.startswith("worker 2: 1 claimed block not written, block-001-"), r.message
    assert not (job.run_dir / "mobcal.out").exists()


def test_blocks_no_worker_claims_fail_the_run(tmp_path):
    # each of two workers claims 150 blocks and stops: 100 of the 400 are never claimed
    job = Job(write_input(tmp_path / "x.mfj", "short 150"), "he", 1, tmp_path, split=2,
              dealing="claimed")
    r = run_one(job, launcher)
    assert not r.ok
    assert r.message.startswith("100 blocks never claimed, block-001-"), r.message


def test_a_block_written_twice_fails_the_run(tmp_path):
    # the stand-in's greedy worker ignores the claims: every block written by both workers
    job = Job(write_input(tmp_path / "x.mfj", "greedy"), "he", 1, tmp_path, split=2,
              dealing="claimed")
    r = run_one(job, launcher)
    assert not r.ok
    assert "block-001-00001.dat written by workers 1 and 2" in r.message, r.message


def test_stale_claims_are_removed_before_a_run(tmp_path):
    job = Job(write_input(tmp_path / "x.mfj", "ok"), "he", 1, tmp_path, split=2,
              dealing="claimed")
    assert run_one(job, launcher).ok
    stale = job.run_dir / claim_name(1, 1)
    stale.write_text("   99\n")  # a claim from an earlier run would keep block 1 from everyone
    r = run_one(job, launcher)
    assert r.ok, r.message
    assert int(stale.read_text()) in (1, 2)


def test_a_static_job_claims_nothing(tmp_path):
    assert Job(Path("x.mfj"), "he", 1, Path("runs"), split=2).dealing == "claimed"  # the default
    job = Job(write_input(tmp_path / "x.mfj", "ok"), "he", 1, tmp_path, split=2, dealing="static")
    assert run_one(job, launcher).ok
    assert not list(job.run_dir.glob("claim-*"))
    with pytest.raises(ValueError, match="dealing must be one of"):
        Job(Path("x.mfj"), "he", 1, Path("runs"), split=2, dealing="claim")


def test_the_stand_in_is_run_by_the_test_interpreter():
    assert FAKE.is_file() and sys.executable
