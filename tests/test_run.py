"""mobcal.run through a stand-in binary: staging, collection, failure reporting, fanout."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from mobcal import fortran
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile
from mobcal.run import FALLBACK_STAGED_NAME, Job, Result, run_many, run_one

FAKE = Path(__file__).resolve().parent / "fake_mobcal.py"
CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"


def launcher(job: Job) -> list[str]:
    return [sys.executable, str(FAKE), job.gas]


def write_input(path: Path, label: str) -> Path:
    """Choline's atoms under another label: the stand-in reads the label, the reader the rest."""
    body = CHOLINE.read_text(encoding="latin-1").split("\n", 1)[1]
    path.write_text(f"{label}\n{body}", encoding="latin-1", newline="\n")
    return path


def test_run_one_stages_runs_and_collects(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "he", 5013489, tmp_path / "runs")
    r = run_one(job, launcher)
    assert r.ok and r.message == "" and r.returncode == 0
    tm = 50 + 5013489 % 7
    assert r.cross_sections == {"PA": tm + 5.5, "EHS": tm + 8, "TM": tm}
    assert r.conformers == [r.cross_sections]
    d = tmp_path / "runs" / "ok-he-5013489"
    assert r.output == d / "mobcal.out"
    assert InFile.read(d / "mobcal.in") == InFile("ok.mfj", "mobcal.out", 5013489)
    assert (d / "ok.mfj").read_bytes() == inp.read_bytes()
    assert (d / "stdout.log").is_file()
    assert OutFile.read(r.output).input_name == "ok.mfj"


def test_nitrogen_reports_tm_only(tmp_path):
    r = run_one(Job(write_input(tmp_path / "ok.mfj", "ok"), "n2", 8, tmp_path), launcher)
    assert r.ok and r.cross_sections == {"TM": 51.0}


def test_staged_name_and_label_can_be_chosen(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "he", 1, tmp_path, name="gate", staged_name="Choline_pop.mfj")
    r = run_one(job, launcher)
    assert r.ok and r.output == tmp_path / "gate" / "mobcal.out"
    assert (tmp_path / "gate" / "Choline_pop.mfj").is_file()
    assert OutFile.read(r.output).input_name == "Choline_pop.mfj"


def test_a_long_input_name_is_staged_under_the_fallback(tmp_path):
    name = "a-name-the-a30-field-cannot-hold.mfj"
    assert len(name) > 30
    job = Job(write_input(tmp_path / name, "ok"), "he", 1, tmp_path)
    assert job.staged == FALLBACK_STAGED_NAME
    r = run_one(job, launcher)
    assert r.ok and (job.run_dir / FALLBACK_STAGED_NAME).is_file()


def test_multi_set_output_gives_per_set_values_and_their_mean(tmp_path):
    r = run_one(Job(write_input(tmp_path / "two.mfj", "sets 2"), "he", 7, tmp_path), launcher)
    assert r.ok
    assert r.conformers == [{"PA": 56.5, "EHS": 59.0, "TM": 51.0},
                            {"PA": 57.5, "EHS": 60.0, "TM": 52.0}]
    assert r.cross_sections == {"PA": 57.0, "EHS": 59.5, "TM": 51.5}


def test_a_refusal_is_failed_not_a_number(tmp_path):
    r = run_one(Job(write_input(tmp_path / "x.mfj", "refuse"), "he", 1, tmp_path), launcher)
    assert not r.ok and r.returncode == 1
    assert r.message == "exit 1: type not defined for atom number  1"
    assert r.cross_sections == {} and r.conformers == []
    assert r.output is not None and r.output.is_file()


def test_a_nonzero_exit_is_failed(tmp_path):
    r = run_one(Job(write_input(tmp_path / "x.mfj", "crash"), "he", 1, tmp_path), launcher)
    assert not r.ok and r.returncode == 3
    assert r.message.startswith("exit 3: using RANLUX with seed integer")


def test_no_output_file_is_failed(tmp_path):
    r = run_one(Job(write_input(tmp_path / "x.mfj", "silent"), "he", 1, tmp_path), launcher)
    assert not r.ok and r.output is None
    assert r.message == "no output file written (exit 0)"


def test_an_input_the_reader_refuses_never_starts_the_binary(tmp_path):
    bad = tmp_path / "bad.mfj"
    bad.write_text("label\n1\n1\n ang\ncalc\n1.0\n0 0 0 1 1\n", encoding="latin-1")
    r = run_one(Job(bad, "he", 1, tmp_path), launcher)
    assert not r.ok and r.returncode is None
    assert r.message.startswith("input refused: line 4: units ' ang'")
    assert not (tmp_path / "bad-he-1").exists()


def test_a_stale_output_is_not_read_as_success(tmp_path):
    inp = write_input(tmp_path / "x.mfj", "ok")
    job = Job(inp, "he", 1, tmp_path)
    assert run_one(job, launcher).ok
    write_input(inp, "silent")
    r = run_one(job, launcher)
    assert not r.ok and r.message == "no output file written (exit 0)"


def test_a_missing_binary_is_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("MOBCAL_BIN_DIR", str(tmp_path / "nowhere"))
    r = run_one(Job(write_input(tmp_path / "x.mfj", "ok"), "he", 1, tmp_path))
    assert not r.ok and r.returncode is None
    assert r.message.startswith(f"no {fortran.binary_name('he')} in ")


def test_run_many_keeps_job_order_reports_progress_and_writes_the_summary(tmp_path):
    labels = ["ok", "refuse", "ok", "crash"]
    jobs = [Job(write_input(tmp_path / f"in{i}.mfj", lab), "he", 10 + i, tmp_path / "runs")
            for i, lab in enumerate(labels)]
    seen: list[tuple[str, int, int]] = []
    s = run_many(jobs, workers=2, progress=lambda r, d, n: seen.append((r.job.label, d, n)),
                 launcher=launcher)
    assert [r.job.label for r in s.results] == [j.label for j in jobs]
    assert [r.ok for r in s.results] == [True, False, True, False]
    assert s.workers == 2 and len(s.ok) == 2 and len(s.failed) == 2
    assert sorted(lab for lab, _, _ in seen) == sorted(j.label for j in jobs)
    assert [(d, n) for _, d, n in seen] == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert s.results[0].cross_sections["TM"] == 50 + 10 % 7
    assert s.results[2].cross_sections["TM"] == 50 + 12 % 7

    csv_path, json_path = s.write(tmp_path / "runs")
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "name,input,gas,seed,status,PA,EHS,TM,sets,seconds,output,message"
    assert rows[1].startswith("in0-he-10,") and ",ok,58.5,61.0,53.0,1," in rows[1]
    assert rows[2].startswith("in1-he-11,") and ",failed,,,,," in rows[2]
    assert rows[2].endswith(",exit 1: type not defined for atom number  1")
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["workers"] == 2 and len(doc["runs"]) == 4
    assert doc["runs"][3] == {**doc["runs"][3], "status": "failed", "returncode": 3}
    assert doc["runs"][0]["conformers"] == [{"PA": 58.5, "EHS": 61.0, "TM": 53.0}]


def test_run_many_runs_jobs_at_once(tmp_path):
    # Four one-second runs on four workers take about one second, not four.
    jobs = [Job(write_input(tmp_path / f"s{i}.mfj", "sleep 1"), "he", i + 1, tmp_path)
            for i in range(4)]
    t0 = time.perf_counter()
    s = run_many(jobs, workers=4, launcher=launcher)
    wall = time.perf_counter() - t0
    assert all(r.ok for r in s.results)
    assert all(r.seconds >= 1 for r in s.results)
    assert wall < 3.0, f"{wall:.1f} s for four one-second runs on four workers"


def test_run_many_with_no_jobs(tmp_path):
    s = run_many([], workers=4, launcher=launcher)
    assert s.results == [] and s.workers == 1
    assert str(s).startswith("0 runs, 0 ok, 0 failed")


def test_job_refuses_an_unknown_gas(tmp_path):
    with pytest.raises(ValueError, match="gas must be one of"):
        Job(CHOLINE, "ar", 1, tmp_path)


def test_result_str():
    j = Job(CHOLINE, "he", 1, Path("runs"))
    ok = Result(j, True, "", 0, 190.4, None, {"PA": 61.075, "TM": 55.402}, [{}])
    assert str(ok) == "Choline-he-1  ok  PA 61.075  TM 55.402 A^2  190 s"
    bad = Result(j, False, "no SUMMARY: masses do not add up", 0, 0.2, None, {}, [])
    assert str(bad) == "Choline-he-1  FAILED  no SUMMARY: masses do not add up"
