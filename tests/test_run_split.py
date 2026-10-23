"""mobcal.run with ``split``, through the stand-in binary: the worker directories, the block
files, the combining run, progress, and a worker that leaves a block unwritten."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mobcal.io.block import BLOCKS_PER_SET, Block, expected_names
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile
from mobcal.run import Job, run_many, run_one
from test_run import launcher, write_input

FAKE = Path(__file__).resolve().parent / "fake_mobcal.py"


def test_a_split_job_runs_its_workers_then_the_combining_run(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "he", 5013489, tmp_path / "runs", split=3)
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
    assert any(x.startswith(" blocks of imp trajectories: integrated   0, read from files 400,")
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
    job = Job(write_input(tmp_path / "two.mfj", "sets 2"), "he", 7, tmp_path, split=2)
    r = run_one(job, launcher)
    assert r.ok and len(r.conformers) == 2
    assert len(list(job.run_dir.glob("block-*.dat"))) == 2 * BLOCKS_PER_SET
    assert len(list(job.worker_dir(1).glob("block-002-*.dat"))) == BLOCKS_PER_SET // 2


def test_a_worker_that_leaves_a_block_unwritten_fails_the_run(tmp_path):
    job = Job(write_input(tmp_path / "x.mfj", "lazy"), "he", 1, tmp_path, split=2)
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


def test_the_stand_in_is_run_by_the_test_interpreter():
    assert FAKE.is_file() and sys.executable
