"""The methods, the batch, the estimate and the study folder: the Qt-free half of the window.

Through the stand-in binary where a run is needed. A preset is held to its ``docs/`` command
line by the jobs both make and the bytes they stage: the program reads nothing else, so equal
staged directories are equal outputs at the same seed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from mobcal import batch, cli, estimate, fortran, methods, parameters, run, settings
from mobcal.batch import Batch, BatchError
from mobcal.run import Job, Stop, run_many

FAKE = Path(__file__).resolve().parent / "fake_mobcal.py"
CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"


def launcher(job: Job) -> list[str]:
    return [sys.executable, str(FAKE), job.gas]


def write_input(path: Path, label: str) -> Path:
    body = CHOLINE.read_text(encoding="latin-1").split("\n", 1)[1]
    path.write_text(f"{label}\n{body}", encoding="latin-1", newline="\n")
    return path


def from_cli(tmp_path: Path, *argv: str) -> Batch:
    return cli.batch_from_args(cli.parser().parse_args(["run", *argv, "--out",
                                                        str(tmp_path / "runs")]))


def staged(job: Job, d: Path) -> dict[str, bytes]:
    pset = parameters.load(job.parameters_path, gas=job.gas)
    run._prepare(job, d, None, pset)
    return {p.name: p.read_bytes() for p in sorted(d.iterdir())}


# --- the presets ---------------------------------------------------------------------------

def test_the_three_methods():
    cur, m12, m00 = (methods.METHODS[k] for k in ("current", "2012", "2000"))
    assert (cur.generator, cur.parameters, cur.settings) == ("philox", "2012", settings.DEFAULTS)
    assert (m12.generator, m12.parameters, m12.settings) == ("ranlux", "2012", settings.DEFAULTS)
    assert (m00.generator, m00.parameters, m00.gases) == ("ranlux", "2000", ("he",))
    assert m00.overrides() == {"temperature": 298.0, "imp": 25}
    with pytest.raises(methods.MethodError, match="MOBCAL 2000 is a method for He only"):
        m00.check_gas("n2")


@pytest.mark.parametrize("method, docs", [
    ("2012", ["--rng", "ranlux"]),
    ("2012", ["--gas", "both", "--rng", "ranlux"]),
    ("2000", ["--parameters", "2000", "--temperature", "298", "--imp", "25", "--rng", "ranlux"]),
])
def test_a_preset_is_its_docs_command_line(tmp_path, method, docs):
    # docs/mobcal-2012.md and docs/mobcal-2000.md give these command lines; the preset must
    # make the same jobs and stage the same bytes, so the program computes the same output.
    gas = ["--gas", "both"] if "both" in docs else []
    by_method = from_cli(tmp_path, str(CHOLINE), "--method", method, *gas)
    by_docs = from_cli(tmp_path, str(CHOLINE), *docs)
    a, b = by_method.jobs(), by_docs.jobs()
    assert a == b and [j.label for j in a] == [j.label for j in b]
    for ja, jb in zip(a, b, strict=True):
        assert staged(ja, tmp_path / "a" / ja.label) == staged(jb, tmp_path / "b" / jb.label)
        assert ja.method == jb.method == method
        assert ja.settings.source.record() == jb.settings.source.record()
    assert by_method.title() == methods.TITLES[method]


def test_the_2000_preset_names_its_run_directory_as_the_docs_say(tmp_path):
    b = from_cli(tmp_path, str(CHOLINE), "--method", "2000", "--seeds", "5013486")
    assert [j.label for j in b.jobs()] == ["Choline-he-5013486-ranlux-lj2000-t298-imp25"]


def test_the_2000_preset_is_refused_in_nitrogen(tmp_path, capsys):
    with pytest.raises(cli.UsageError, match="for He only, not N2; run it with --gas he"):
        from_cli(tmp_path, str(CHOLINE), "--method", "2000", "--gas", "both")
    assert cli.main(["run", str(CHOLINE), "--method", "2000", "--gas", "n2"]) == 2


@pytest.mark.parametrize("argv, want, title", [
    ([], "current", "Current"),
    (["--rng", "ranlux"], "2012", "MOBCAL 2012"),
    (["--imp", "25"], "custom", "Custom (from Current)"),
    (["--method", "2012", "--rng", "philox"], "current", "Current"),
    (["--method", "2012", "--temperature", "300"], "custom", "Custom (from MOBCAL 2012)"),
    (["--parameters", "2000", "--rng", "ranlux"], "custom", "Custom (from Current)"),
    (["--method", "2000", "--imp", "1000"], "custom", "Custom (from MOBCAL 2000)"),
])
def test_a_run_records_the_method_its_fields_make(tmp_path, argv, want, title):
    b = from_cli(tmp_path, str(CHOLINE), *argv)
    assert b.method_now == want and b.title() == title


def test_a_settings_file_over_a_method_replaces_its_settings(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text("format = 1\nitn = 5\n", encoding="utf-8")
    b = from_cli(tmp_path, str(CHOLINE), "--method", "2000", "--settings", str(f))
    assert b.resolved_settings.values() == {**settings.DEFAULTS.values(), "itn": 5}
    assert b.method_now == "custom"


# --- the record, the summary and the study folder ------------------------------------------

def test_the_record_and_the_summary_carry_the_method(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    jobs = [Job(inp, "he", 1, tmp_path / "runs"),
            Job(inp, "he", 1, tmp_path / "runs", generator="ranlux")]
    s = run_many(jobs, 2, launcher=launcher)
    csv_path, json_path = s.write(tmp_path / "runs")
    recs = [json.loads((j.run_dir / "record.json").read_text(encoding="utf-8")) for j in jobs]
    assert [r["method"] for r in recs] == ["current", "2012"]
    assert [r["method"] for r in json.loads(json_path.read_text(encoding="utf-8"))["runs"]] \
        == ["current", "2012"]
    assert [line.split(",")[5] for line in csv_path.read_text().splitlines()] == \
        ["method", "current", "2012"]


def test_the_summary_covers_every_run_in_the_folder(tmp_path):
    out = tmp_path / "runs"
    a = write_input(tmp_path / "a.mfj", "ok")
    b = write_input(tmp_path / "b.mfj", "refuse")
    run_many([Job(a, "he", 1, out)], 1, launcher=launcher).write(out)
    s = run_many([Job(b, "he", 2, out), Job(a, "he", 3, out)], 2, launcher=launcher)
    csv_path, json_path = s.write(out)
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert [r["name"] for r in doc["runs"]] == ["a-he-1", "a-he-3", "b-he-2"]
    assert doc["batch"] == ["b-he-2", "a-he-3"] and doc["workers"] == 2
    assert [r["status"] for r in doc["runs"]] == ["ok", "ok", "failed"]
    assert doc["runs"][0]["output"] == str(out / "a-he-1" / "mobcal.out")
    assert len(csv_path.read_text().splitlines()) == 4


def test_a_table_other_than_the_default_names_the_run_directory(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    mine = tmp_path / "mine.toml"
    mine.write_bytes(parameters.default_path("he").read_bytes().replace(
        b'name = "MOBCAL 2012 helium"', b'name = "my helium"'))
    copy = tmp_path / "copy.toml"
    copy.write_bytes(parameters.default_path("he").read_bytes())
    sha = run.hashlib.sha256(mine.read_bytes()).hexdigest()
    assert Job(inp, "he", 1, tmp_path).label == "ok-he-1"
    assert Job(inp, "he", 1, tmp_path, parameters=copy).label == "ok-he-1"
    assert Job(inp, "he", 1, tmp_path,
               parameters=parameters.shipped_path("he", "2000")).label == "ok-he-1-lj2000"
    assert Job(inp, "he", 1, tmp_path, parameters=mine).label == f"ok-he-1-lj{sha[:8]}"
    assert Job(inp, "he", 1, tmp_path, parameters=mine).method == "custom"


def test_prior_runs_in_the_folder(tmp_path):
    out = tmp_path / "runs"
    a = write_input(tmp_path / "a.mfj", "ok")
    bad = write_input(tmp_path / "bad.mfj", "refuse")
    run_many([Job(a, "he", 1, out), Job(bad, "he", 1, out)], 2, launcher=launcher)
    other = tmp_path / "elsewhere"
    other.mkdir()
    a2 = write_input(other / "a.mfj", "sets 2")  # another input under the same name
    found = {p.job.input: p for p in batch.prior([Job(a, "he", 1, out), Job(bad, "he", 1, out),
                                                  Job(a, "he", 2, out)])}
    assert found[a].kind == batch.DONE and found[bad].kind == batch.NOT_DONE
    assert len(found) == 2  # seed 2 has no directory
    clash = batch.prior([Job(a2, "he", 1, out)])
    assert [p.kind for p in clash] == [batch.CLASH]
    assert cli.main(["run", str(a2), "--seeds", "1", "--out", str(out)]) == 2


# --- stop -----------------------------------------------------------------------------------

def test_stop_ends_a_batch_and_marks_its_runs_stopped(tmp_path):
    out = tmp_path / "runs"
    jobs = [Job(write_input(tmp_path / f"s{i}.mfj", "sleep 30"), "he", i, out)
            for i in (1, 2, 3)]
    jobs.append(Job(write_input(tmp_path / "later.mfj", "ok"), "he", 9, out))
    stop = Stop()
    timer = run.threading.Timer(1.5, stop)
    timer.start()
    t0 = time.perf_counter()
    s = run_many(jobs, workers=3, launcher=launcher, stop=stop)
    assert time.perf_counter() - t0 < 15
    assert [r.status for r in s.results] == ["stopped"] * 4
    assert s.results[3].message == "not started: the batch was stopped"
    assert not jobs[3].run_dir.exists()
    rec = json.loads((jobs[0].run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["status"] == "stopped" and rec["message"].startswith("stopped")
    assert "4 stopped" in str(s) and not s.failed
    _, json_path = s.write(out)
    assert {r["status"] for r in json.loads(json_path.read_text())["runs"]} == {"stopped"}


def test_stop_ends_a_split_run_before_its_combining_run(tmp_path):
    job = Job(write_input(tmp_path / "s.mfj", "sleep 30"), "he", 1, tmp_path / "runs", split=3)
    stop = Stop()
    run.threading.Timer(1.5, stop).start()
    t0 = time.perf_counter()
    r = run_many([job], 1, launcher=launcher, stop=stop).results[0]
    assert time.perf_counter() - t0 < 15
    assert r.status == "stopped" and not (job.run_dir / "mobcal.out").exists()


# --- the batch as data -------------------------------------------------------------------

def test_a_batch_round_trips_through_the_queue_file(tmp_path):
    b1 = Batch((CHOLINE,), tmp_path / "runs", gases=("he", "n2"), seeds=(1, 2), method="2012",
               settings=settings.resolve(None, imp=25), split=4, workers=2)
    b2 = Batch((CHOLINE,), tmp_path / "runs", method="2000", parameters=None, split="auto")
    path = batch.save([b1, b2], tmp_path / "queue.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["batches"].append({**doc["batches"][1], "method": "1996"})
    path.write_text(json.dumps(doc), encoding="utf-8")
    got, problems = batch.load(path)
    assert got == [b1, b2] and [b.jobs() for b in got] == [b1.jobs(), b2.jobs()]
    assert problems == ["queued batch 3: not a batch: no method is named '1996'; the methods "
                        "are current, 2012, 2000"]
    assert got[0].title() == "Custom (from MOBCAL 2012)" and got[1].title() == "MOBCAL 2000"


def test_a_batch_refuses_what_cannot_run(tmp_path):
    with pytest.raises(BatchError, match="for He only"):
        Batch((CHOLINE,), tmp_path, gases=("n2",), method="2000")
    with pytest.raises(BatchError, match="split must be"):
        Batch((CHOLINE,), tmp_path, split="sometimes")
    with pytest.raises(BatchError, match="no shipped N2 set is named '2000'"):
        Batch((CHOLINE,), tmp_path, gases=("n2",), parameters="2000").jobs()


# --- the estimate and the allocation -------------------------------------------------------

def test_the_model_reproduces_its_own_points():
    for gas, points in estimate.COSTS.items():
        for atoms, prologue, tau in points:
            c = estimate.cost(atoms, 1, gas)
            assert c.prologue == pytest.approx(prologue)
            assert c.trajectories == pytest.approx(tau * settings.DEFAULTS.points)


def test_a_split_pays_the_prologue_twice():
    c = estimate.Cost(10.0, 400.0)
    assert c.wall() == 410.0 and c.wall(1) == 410.0 and c.wall(40) == 30.0


def test_allocation(tmp_path):
    jobs = [Job(CHOLINE, "he", s, tmp_path) for s in range(4)]
    one = estimate.allocate(jobs[:1], cpus=80)
    assert one.workers == 1 and one.jobs[0].split == estimate.MAX_SPLIT
    four = estimate.allocate(jobs, cpus=80)
    assert four.workers == 4 and {j.split for j in four.jobs} == {20}
    many = estimate.allocate(jobs, cpus=4)
    assert many.workers == 4 and {j.split for j in many.jobs} == {None}
    two_cores = estimate.allocate(jobs[:1], cpus=2)
    assert two_cores.jobs[0].split == 2  # 2 * 2.25 + 192 / 2 is well under 0.8 * 194.6
    # The prologue dominating, as in the 2000 release's example at imp 25 with its projection
    # pass per set: no split however many cores.
    st = settings.resolve(None, imp=1)
    lean = estimate.allocate([Job(CHOLINE, "he", 1, tmp_path, settings=st)], cpus=80)
    assert lean.jobs[0].split is None
    # A split never exceeds the blocks there are to deal.
    st = settings.resolve(None, itn=1, inp=5)
    assert estimate.allocate([Job(CHOLINE, "n2", 1, tmp_path, settings=st)],
                             cpus=80).jobs[0].split == 5


def test_the_estimate_follows_the_queue(tmp_path):
    p = estimate.plan([Job(CHOLINE, "he", s, tmp_path) for s in range(3)], workers=2)
    one = estimate.cost(21, 1, "he").wall()
    assert p.seconds == pytest.approx(2 * one) and p.walls == (pytest.approx(one),) * 3
    assert estimate.describe(p) == "3 runs on 2 workers; about 6 min"
    missing = estimate.plan([Job(tmp_path / "nothing.mfj", "he", 1, tmp_path)], workers=1)
    assert missing.walls == (None,) and "no estimate" in estimate.describe(missing)


def test_a_large_ion_shows_its_prologue(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    import synthetic
    big = synthetic.write(tmp_path / "big.mfj", synthetic.globule(3000), "globule")
    p = estimate.allocate([Job(big, "he", 1, tmp_path)], cpus=80)
    assert "per process before its first trajectory" in estimate.describe(p)


@pytest.mark.parametrize("seconds, text", [(4, "4 s"), (37, "40 s"), (185, "3 min"),
                                           (4190, "70 min"), (5331, "89 min"), (6000, "1.7 h"),
                                           (36 * 3600, "36 h"), (37 * 86400, "37.0 days")])
def test_durations(seconds, text):
    assert estimate.duration(seconds) == text


# --- the methods text ----------------------------------------------------------------------

def test_the_methods_text(tmp_path, capsys):
    out = tmp_path / "runs"
    a = write_input(tmp_path / "a.mfj", "ok")
    jobs = [Job(a, "he", s, out, generator="ranlux") for s in (1, 2, 3)]
    jobs += [Job(a, "n2", 1, out)]
    jobs += [Job(write_input(tmp_path / "bad.mfj", "refuse"), "he", 1, out)]
    run_many(jobs, 5, launcher=launcher).write(out)
    text = methods.text(methods.read_records([out]))
    para, refs = text.split("\n\n")
    assert "—" not in text and "–" not in para
    assert para.startswith("Collision cross sections were calculated by the trajectory method "
                           "(1, 2, 3, 4) in helium and nitrogen with MOBCAL ")
    assert ("The helium calculations used the method of the MOBCAL 2012 release: the MOBCAL "
            "2012 helium element table, 301 K, 400,000 trajectories per structure") in para
    assert "at 3 seeds per structure, and each cross section is the mean and standard " \
           "deviation over its 3 runs." in para
    assert "RANLUX at luxury level 3 (5, 6)" in para and "Philox4x32-10 (7), at seed 1." in para
    assert "The nitrogen calculations used the default method of this version" in para
    assert refs.splitlines()[0].startswith("1. Mesleh, M. F.")
    assert len(refs.splitlines()) == 7
    assert cli.main(["methods-text", str(jobs[0].run_dir)]) == 0
    one = capsys.readouterr().out
    assert "at seed 1." in one and "nitrogen" not in one
    assert cli.main(["methods-text", str(tmp_path / "nothing")]) == 2
