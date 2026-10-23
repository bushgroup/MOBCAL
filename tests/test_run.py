"""mobcal.run through a stand-in binary: staging, collection, failure reporting, fanout."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

import mobcal
from mobcal import cli, fortran, parameters, run
from mobcal.io.infile import InFile
from mobcal.io.mfj import Mfj
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
    tm = 50 + 5013489 % 7 + 0.5  # the stand-in's Philox half
    assert r.cross_sections == {"PA": tm + 5.5, "EHS": tm + 8, "TM": tm}
    assert r.conformers == [r.cross_sections]
    d = tmp_path / "runs" / "ok-he-5013489"
    assert r.output == d / "mobcal.out"
    assert InFile.read(d / "mobcal.in") == InFile("ok.mfj", "mobcal.out", 5013489,
                                                  generator="philox")
    assert (d / "ok.mfj").read_bytes() == inp.read_bytes()
    assert (d / "stdout.log").is_file()
    assert OutFile.read(r.output).input_name == "ok.mfj"


def test_nitrogen_reports_tm_only(tmp_path):
    r = run_one(Job(write_input(tmp_path / "ok.mfj", "ok"), "n2", 8, tmp_path), launcher)
    assert r.ok and r.cross_sections == {"TM": 51.5}


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
    assert r.conformers == [{"PA": 57.0, "EHS": 59.5, "TM": 51.5},
                            {"PA": 58.0, "EHS": 60.5, "TM": 52.5}]
    assert r.cross_sections == {"PA": 57.5, "EHS": 60.0, "TM": 52.0}


def test_a_refusal_is_failed_not_a_number(tmp_path):
    r = run_one(Job(write_input(tmp_path / "x.mfj", "refuse"), "he", 1, tmp_path), launcher)
    assert not r.ok and r.returncode == 1
    assert r.message == "exit 1: type not defined for atom number   1"
    assert r.cross_sections == {} and r.conformers == []
    assert r.output is not None and r.output.is_file()


def test_a_nonzero_exit_is_failed(tmp_path):
    r = run_one(Job(write_input(tmp_path / "x.mfj", "crash"), "he", 1, tmp_path), launcher)
    assert not r.ok and r.returncode == 3
    assert r.message.startswith("exit 3: using Philox4x32-10 with seed integer")


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
    assert s.results[0].cross_sections["TM"] == 50 + 10 % 7 + 0.5
    assert s.results[2].cross_sections["TM"] == 50 + 12 % 7 + 0.5

    csv_path, json_path = s.write(tmp_path / "runs")
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "name,input,gas,seed,rng,status,PA,EHS,TM,sets,seconds,output,message"
    assert rows[1].startswith("in0-he-10,") and ",10,philox,ok,59.0,61.5,53.5,1," in rows[1]
    assert rows[2].startswith("in1-he-11,") and ",failed,,,,," in rows[2]
    assert rows[2].endswith(",exit 1: type not defined for atom number   1")
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["workers"] == 2 and len(doc["runs"]) == 4
    assert doc["runs"][3] == {**doc["runs"][3], "status": "failed", "returncode": 3}
    assert doc["runs"][0]["conformers"] == [{"PA": 59.0, "EHS": 61.5, "TM": 53.5}]
    assert {run["rng"] for run in doc["runs"]} == {"philox"}


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


# --- the element table and the record --------------------------------------------------------

def _my_table(tmp_path: Path, gas: str = "he", name: str = "my helium") -> Path:
    p = tmp_path / f"mine-{gas}.toml"
    text = parameters.default_path(gas).read_text(encoding="utf-8")
    old = 'name = "MOBCAL 2012 helium"' if gas == "he" else 'name = "MOBCAL 2012 nitrogen"'
    p.write_text(text.replace(old, f'name = "{name}"'), encoding="utf-8")
    return p


@pytest.mark.parametrize("gas", fortran.GASES)
def test_every_run_directory_gets_the_rendered_table(tmp_path, gas):
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), gas, 1, tmp_path / "runs")
    r = run_one(job, launcher)
    assert r.ok
    want = parameters.shipped(gas).render(tmp_path).read_bytes()
    assert (job.run_dir / parameters.RENDERED).read_bytes() == want
    assert r.parameters == parameters.shipped(gas).record()


def test_without_the_rendered_table_the_stand_in_refuses(tmp_path, monkeypatch):
    # The stand-in checks for the table as the program will; the driver is what supplies it.
    monkeypatch.setattr(parameters.ParameterSet, "render", lambda self, d: None)
    r = run_one(Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path), launcher)
    assert not r.ok and r.message == "exit 1: no parameters.tab for this gas in the run directory"


def test_a_job_can_name_its_own_table(tmp_path):
    mine = _my_table(tmp_path)
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path / "runs",
              parameters=str(mine))
    assert job.parameters == mine and job.parameters_path == mine
    r = run_one(job, launcher)
    assert r.ok and r.parameters["name"] == "my helium" and not r.parameters["shipped"]
    head = (job.run_dir / parameters.RENDERED).read_text(encoding="ascii").split()[:5]
    assert head == ["MOBCAL-LJ", "1", "He", "my_helium", r.parameters["sha256"]]


def test_a_refused_table_never_starts_the_binary(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(parameters.default_path("he").read_text(encoding="utf-8")
                   .replace('rhs = "2.95d0"', 'rhs = "2.95"'), encoding="utf-8")
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path / "runs",
              parameters=bad)
    r = run_one(job, launcher)
    assert not r.ok and r.returncode is None
    assert r.message.startswith(f"parameters refused: {bad}: element 28: rhs: ")
    assert not job.run_dir.exists()


def test_a_table_for_the_other_gas_is_refused(tmp_path):
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path / "runs",
              parameters=parameters.default_path("n2"))
    r = run_one(job, launcher)
    assert not r.ok and r.message.endswith("is a table for N2, not He")


def test_a_split_run_renders_into_every_directory(tmp_path):
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 3, tmp_path / "runs", split=3)
    r = run_one(job, launcher)
    assert r.ok
    want = (job.run_dir / parameters.RENDERED).read_bytes()
    assert want == parameters.shipped("he").render(tmp_path).read_bytes()
    for w in (1, 2, 3):
        assert (job.worker_dir(w) / parameters.RENDERED).read_bytes() == want
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["mobcal_in"] == {"seed": 3, "generator": "philox", "split": 3}


def test_the_record_of_a_run(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "n2", 5013489, tmp_path / "runs")
    r = run_one(job, launcher)
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["mobcal_version"] == mobcal.__version__ and rec["name"] == "ok-n2-5013489"
    assert rec["binary"]["gas"] == "n2" and rec["binary"]["command"] == launcher(job)
    assert rec["binary"]["build"] is None  # the stand-in has no build.json
    assert rec["input"] == {"path": str(inp), "staged_name": "ok.mfj",
                            "sha256": hashlib.sha256(inp.read_bytes()).hexdigest(),
                            "atoms": 21, "coordinate_sets": 1}
    assert rec["mobcal_in"] == {"seed": 5013489, "generator": "philox", "split": None}
    assert rec["parameters"] == parameters.shipped("n2").record()
    assert rec["parameters"]["rendered"] == "parameters.tab"
    assert (rec["status"], rec["returncode"], rec["message"]) == ("ok", 0, "")
    assert rec["cross_sections"] == r.cross_sections == {"TM": 50 + 5013489 % 7 + 0.5}
    assert rec["conformers"] == r.conformers
    assert (rec["output"], rec["console_log"]) == ("mobcal.out", "stdout.log")
    assert dt.datetime.fromisoformat(rec["started"]).tzinfo is not None
    assert rec["seconds"] == round(r.seconds, 2)


def test_a_failed_run_has_a_record_too(tmp_path):
    job = Job(write_input(tmp_path / "x.mfj", "refuse"), "he", 1, tmp_path)
    run_one(job, launcher)
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert (rec["status"], rec["returncode"]) == ("failed", 1)
    assert rec["message"] == "exit 1: type not defined for atom number   1"
    assert rec["cross_sections"] == {} and rec["conformers"] == []


def test_the_record_quotes_the_binarys_build(tmp_path):
    # A command whose first word is a recorded binary: the build.json beside it is quoted.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / fortran.binary_name("he")
    exe.write_bytes(b"not run")
    fortran._record(bin_dir, "he", exe, "no-such-gfortran")
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path / "runs")
    r = Result(job, True, "", 0, 1.0, None, {}, [], parameters={"name": "x"})
    run._write_record(r, [str(exe)], Mfj.read(job.input), dt.datetime.now().astimezone())
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["binary"]["build"] == fortran.read_manifest(bin_dir)["binaries"][exe.name]


def test_a_stale_record_does_not_survive_a_rerun_that_cannot_start(tmp_path):
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path)
    assert run_one(job, launcher).ok
    r = run_one(job, lambda j: [str(tmp_path / "no-such-program")])
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert not r.ok and rec["status"] == "failed" and rec["message"].startswith("cannot start")


def test_the_summary_names_each_runs_table(tmp_path):
    mine = _my_table(tmp_path)
    jobs = [Job(write_input(tmp_path / "a.mfj", "ok"), "he", 1, tmp_path / "runs"),
            Job(write_input(tmp_path / "b.mfj", "ok"), "he", 1, tmp_path / "runs",
                parameters=mine)]
    s = run_many(jobs, workers=2, launcher=launcher)
    _, json_path = s.write(tmp_path / "runs")
    runs = json.loads(json_path.read_text(encoding="utf-8"))["runs"]
    shipped = parameters.shipped("he")
    assert (runs[0]["parameters"], runs[0]["parameters_sha256"]) == (shipped.name,
                                                                     shipped.sha256)
    assert runs[1]["parameters"] == "my helium"
    assert runs[1]["parameters_sha256"] == hashlib.sha256(mine.read_bytes()).hexdigest()


def test_a_job_under_philox(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "he", 5013489, tmp_path / "runs", generator="philox")
    r = run_one(job, launcher)
    assert r.ok, r.message
    d = job.run_dir
    assert (d / "mobcal.in").read_bytes() == b"ok.mfj\nmobcal.out\n5013489 philox\n"
    assert InFile.read(d / "mobcal.in") == InFile("ok.mfj", "mobcal.out", 5013489,
                                                  generator="philox")
    out = OutFile.read(r.output)
    assert out.seed == 5013489 and out.generator == "philox"
    rec = json.loads((d / "record.json").read_text(encoding="utf-8"))
    assert rec["mobcal_in"] == {"seed": 5013489, "generator": "philox", "split": None}
    with pytest.raises(ValueError, match="generator must be one of"):
        Job(inp, "he", 1, tmp_path, generator="rand")


# --- the generator: the driver's default, the label, the record and the summary ----------------

def test_the_drivers_generator_is_philox_and_the_run_files_is_ranlux():
    # Loud on purpose: the driver draws from Philox unless told otherwise, while a run file
    # without the word stays the 2012 run. Every comparison with a 2012 output says ranlux.
    assert run.DEFAULT_RNG == "philox" and Job(CHOLINE, "he", 1, Path("runs")).generator == "philox"
    assert InFile("a", "b", 1).generator == "ranlux"
    assert cli.parser().parse_args(["run", "x.mfj"]).rng == "philox"
    assert cli.parser().parse_args(["run", "x.mfj", "--rng", "ranlux"]).rng == "ranlux"
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["run", "x.mfj", "--rng", "mersenne"])


def test_one_seed_under_both_generators_shares_an_output_directory(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    jobs = [Job(inp, "he", 5013489, tmp_path / "runs", generator=g) for g in ("philox", "ranlux")]
    assert [j.label for j in jobs] == ["ok-he-5013489", "ok-he-5013489-ranlux"]
    assert Job(inp, "he", 1, tmp_path, name="gate", generator="ranlux").label == "gate"
    s = run_many(jobs, workers=2, launcher=launcher)
    philox, ranlux = s.results
    assert philox.ok and ranlux.ok and philox.job.run_dir != ranlux.job.run_dir
    assert philox.cross_sections["TM"] == ranlux.cross_sections["TM"] + 0.5
    assert OutFile.read(ranlux.output).generator == "ranlux"
    assert (ranlux.job.run_dir / "mobcal.in").read_bytes() == b"ok.mfj\nmobcal.out\n5013489\n"
    rec = json.loads((ranlux.job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["mobcal_in"]["generator"] == "ranlux"
    csv_path, _ = s.write(tmp_path / "runs")
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert rows[1].startswith("ok-he-5013489,") and ",5013489,philox,ok," in rows[1]
    assert rows[2].startswith("ok-he-5013489-ranlux,") and ",5013489,ranlux,ok," in rows[2]
    assert str(ranlux).startswith("ok-he-5013489-ranlux  ok  ")
