"""The methods, the batch, the estimate and the study folder: the Qt-free half of the window.

Through the stand-in binary where a run is needed. A shipped method is held to the jobs the
version before methods carried their gas made for the same calculation, and to a command line
that spells its fields out, by the jobs they make and the bytes they stage: the program reads
nothing else, so equal staged directories are equal outputs at the same seed.
"""

from __future__ import annotations

import dataclasses
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
    run._prepare(job, d, None, pset, run.stage(job.input, pset))
    return {p.name: p.read_bytes() for p in sorted(d.iterdir())}


# --- the methods ----------------------------------------------------------------------------

def test_the_five_methods():
    assert list(methods.METHODS) == ["2012-he", "2012-n2", "2012-philox-he", "2012-philox-n2",
                                     "2000-he"]
    assert [m.title for m in methods.METHODS.values()] == [
        "MOBCAL 2012 (He)", "MOBCAL 2012 (N2)", "MOBCAL 2012 with Philox (He)",
        "MOBCAL 2012 with Philox (N2)", "MOBCAL 2000 (He)"]
    fields = {k: (m.gas, m.parameters, m.generator, m.overrides())
              for k, m in methods.METHODS.items()}
    assert fields == {"2012-he": ("he", "2012", "ranlux", {}),
                      "2012-n2": ("n2", "2012", "ranlux", {}),
                      "2012-philox-he": ("he", "2012", "philox", {}),
                      "2012-philox-n2": ("n2", "2012", "philox", {}),
                      "2000-he": ("he", "2000", "ranlux", {"temperature": 298.0, "imp": 25})}
    assert methods.DEFAULT == "2012-philox-he" and methods.verify() == []
    assert all(m.shipped and m.key == m.ref == k for k, m in methods.METHODS.items())


# Each shipped method, and the jobs the version before it made for the same calculation: the
# default job of a gas (--gas he|n2), with --rng ranlux, or --method 2000.
OLD = {
    "2012-he": dict(gas="he", generator="ranlux"),
    "2012-n2": dict(gas="n2", generator="ranlux"),
    "2012-philox-he": dict(gas="he"),
    "2012-philox-n2": dict(gas="n2"),
    "2000-he": dict(gas="he", generator="ranlux",
                    parameters=parameters.shipped_path("he", "2000"),
                    settings=settings.resolve(None, temperature=298.0, imp=25)),
}
# The same, as a command line of today that spells the fields out over another method.
SPELLED = {
    "2012-he": ["--rng", "ranlux"],
    "2012-n2": ["--method", "2012-philox-n2", "--rng", "ranlux"],
    "2012-philox-he": ["--method", "2012-he", "--rng", "philox"],
    "2012-philox-n2": ["--method", "2012-n2", "--rng", "philox"],
    "2000-he": ["--parameters", "2000", "--temperature", "298", "--imp", "25", "--rng",
                "ranlux"],
}


@pytest.mark.parametrize("key", list(methods.METHODS))
def test_a_shipped_method_is_its_old_command_line_run_for_run(tmp_path, key):
    seeds = ["--seeds", "5013489,5013490"]
    by_method = from_cli(tmp_path, str(CHOLINE), "--method", key, *seeds)
    old = [Job(CHOLINE, seed=s, out_dir=tmp_path / "runs", **OLD[key])
           for s in (5013489, 5013490)]
    spelled = from_cli(tmp_path, str(CHOLINE), *SPELLED[key], *seeds)
    a = by_method.jobs()
    for other in (old, spelled.jobs()):
        assert a == other and [j.label for j in a] == [j.label for j in other]
        for ja, jb in zip(a, other, strict=True):
            assert staged(ja, tmp_path / "a" / ja.label) == \
                staged(jb, tmp_path / "b" / jb.label)
            assert ja.method == jb.method == key
    assert by_method.title() == spelled.title() == methods.TITLES[key]
    assert by_method.resolved_gas == methods.METHODS[key].gas


def test_the_2000_method_names_its_run_directory_as_the_docs_say(tmp_path):
    b = from_cli(tmp_path, str(CHOLINE), "--method", "2000-he", "--seeds", "5013486")
    assert [j.label for j in b.jobs()] == ["Choline-he-5013486-ranlux-lj2000-t298-imp25"]


def test_a_method_and_a_table_of_another_gas_are_refused(tmp_path, capsys):
    n2 = str(parameters.default_path("n2"))
    with pytest.raises(cli.UsageError, match="is a table for N2 and MOBCAL 2000 \\(He\\) is a "
                                             "method for He"):
        from_cli(tmp_path, str(CHOLINE), "--method", "2000-he", "--parameters", n2)
    with pytest.raises(cli.UsageError, match="no shipped N2 set is named '2000'"):
        from_cli(tmp_path, str(CHOLINE), "--method", "2012-n2", "--parameters", "2000")
    with pytest.raises(cli.UsageError, match="no method is named '2000'; the methods are "
                                             "2012-he, 2012-n2"):
        from_cli(tmp_path, str(CHOLINE), "--method", "2000")
    assert cli.main(["run", str(CHOLINE), "--method", "current"]) == 2
    capsys.readouterr()
    with pytest.raises(SystemExit):  # run has no --gas: the method carries it
        cli.parser().parse_args(["run", str(CHOLINE), "--gas", "n2"])


@pytest.mark.parametrize("argv, want, title", [
    ([], "2012-philox-he", "MOBCAL 2012 with Philox (He)"),
    (["--rng", "ranlux"], "2012-he", "MOBCAL 2012 (He)"),
    (["--imp", "25"], "custom", "Custom (from MOBCAL 2012 with Philox (He))"),
    (["--method", "2012-n2", "--rng", "philox"], "2012-philox-n2",
     "MOBCAL 2012 with Philox (N2)"),
    (["--method", "2012-he", "--temperature", "300"], "custom",
     "Custom (from MOBCAL 2012 (He))"),
    (["--parameters", "2000", "--rng", "ranlux"], "custom",
     "Custom (from MOBCAL 2012 with Philox (He))"),
    (["--method", "2000-he", "--imp", "1000"], "custom", "Custom (from MOBCAL 2000 (He))"),
])
def test_a_run_records_the_method_its_fields_make(tmp_path, argv, want, title):
    b = from_cli(tmp_path, str(CHOLINE), *argv)
    assert b.method_now == want and b.title() == title


def test_a_settings_file_over_a_method_replaces_its_settings(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text("format = 1\nitn = 5\n", encoding="utf-8")
    b = from_cli(tmp_path, str(CHOLINE), "--method", "2000-he", "--settings", str(f))
    assert b.resolved_settings.values() == {**settings.DEFAULTS.values(), "itn": 5}
    assert b.method_now == "custom"


def test_the_gas_changed_over_a_method_makes_its_other_gas_or_custom(tmp_path):
    b = Batch((CHOLINE,), tmp_path, method="2012-he", gas="n2")
    assert b.method_now == "2012-n2" and [j.label for j in b.jobs()] == \
        ["Choline-n2-5013489-ranlux"]
    b = Batch((CHOLINE,), tmp_path, method="2000-he", gas="n2")
    assert b.method_now == "custom" and b.table() is None  # nitrogen has no 2000 table
    assert b.title() == "Custom (from MOBCAL 2000 (He))"


# --- method files ------------------------------------------------------------------------------

def own_table(path: Path, gas: str = "he") -> Path:
    path.write_bytes(parameters.default_path(gas).read_bytes().replace(
        b'name = "MOBCAL 2012 helium"', b'name = "my helium"'))
    return path


def test_a_saved_method_loads_back_as_the_fields_it_came_from(tmp_path):
    st = settings.resolve(None, temperature=298.15, itn=5)
    m = methods.save(tmp_path / "mine.toml", "Mine at 298.15 K", "he", "2000", "ranlux", st)
    again = methods.load(tmp_path / "mine.toml")
    assert m == again and not m.shipped and m.key == "Mine at 298.15 K"
    assert (m.gas, m.parameters, m.table, m.generator) == ("he", "2000", None, "ranlux")
    assert m.settings.values() == st.values() and m.ref == str(tmp_path / "mine.toml")
    text = (tmp_path / "mine.toml").read_text(encoding="utf-8")
    assert text.startswith('format = 1\nname = "Mine at 298.15 K"\ngas = "he"\n'
                           'parameters = "2000"\ngenerator = "ranlux"\n'
                           "temperature = 298.15\nimp = 1000\nitn = 5\n")
    # The batch the method makes is the batch the fields make, with the file's name recorded.
    by_file = from_cli(tmp_path, str(CHOLINE), "--method", str(tmp_path / "mine.toml"))
    by_fields = from_cli(tmp_path, str(CHOLINE), "--method", "2000-he", "--temperature",
                         "298.15", "--imp", "1000", "--itn", "5")
    assert by_file.jobs() == by_fields.jobs()
    assert {j.method for j in by_file.jobs()} == {"Mine at 298.15 K"}
    assert by_file.jobs()[0].method_file == {"path": str(tmp_path / "mine.toml"),
                                             "sha256": m.sha256}
    assert by_file.title() == "Mine at 298.15 K" and by_fields.method_now == "custom"
    # A field set over it is no longer the file's method.
    over = from_cli(tmp_path, str(CHOLINE), "--method", str(tmp_path / "mine.toml"), "--imp",
                    "25")
    assert over.method_now == "custom" and over.jobs()[0].method_file is None
    assert over.title() == "Custom (from Mine at 298.15 K)"


def test_a_method_file_names_its_own_table_by_path_and_sha256(tmp_path):
    (tmp_path / "tables").mkdir()
    table = own_table(tmp_path / "tables" / "mine_he.toml")
    m = methods.save(tmp_path / "m.toml", "Mine", "he", table, "philox", settings.DEFAULTS)
    sha = run.hashlib.sha256(table.read_bytes()).hexdigest()
    assert m.table == table.resolve() and m.table_sha256 == sha and m.parameters is None
    assert f'path = "{table.resolve().as_posix()}"' in (tmp_path / "m.toml").read_text("utf-8")
    jobs = Batch((CHOLINE,), tmp_path / "runs", method=str(tmp_path / "m.toml")).jobs()
    assert jobs[0].parameters == table.resolve() and jobs[0].method == "Mine"
    assert jobs[0].label == f"Choline-he-5013489-lj{sha[:8]}"
    # A relative path is the method file's folder's.
    rel = tmp_path / "rel.toml"
    rel.write_text(f'format = 1\nname = "Rel"\ngas = "he"\ngenerator = "philox"\n'
                   f'[parameters]\npath = "tables/mine_he.toml"\nsha256 = "{sha}"\n',
                   encoding="utf-8")
    assert methods.load(rel).table == table.resolve()
    # Changed: refused, saying which.
    table.write_bytes(table.read_bytes() + b"\n")
    with pytest.raises(methods.MethodError, match="mine_he.toml has changed since the method "
                                                  "was saved"):
        methods.load(tmp_path / "m.toml")
    with pytest.raises(BatchError, match="has changed"):
        Batch((CHOLINE,), tmp_path / "runs", method=str(tmp_path / "m.toml"))
    # Moved: refused, saying which.
    table.rename(tmp_path / "elsewhere.toml")
    with pytest.raises(methods.MethodError, match="mine_he.toml is not there; it has moved"):
        methods.load(tmp_path / "m.toml")
    with pytest.raises(cli.UsageError, match="is not there"):
        from_cli(tmp_path, str(CHOLINE), "--method", str(tmp_path / "m.toml"))


@pytest.mark.parametrize("body, match", [
    ('format = 1\nname = "X"\ngas = "he"\nparameters = "2012"\n', "no generator"),
    ('format = 1\nname = "X"\ngas = "he"\nparameters = "2012"\ngenerator = "philox"\n'
     "seed = 1\n", "unknown key 'seed'"),
    ('format = 2\nname = "X"\ngas = "he"\nparameters = "2012"\ngenerator = "philox"\n',
     "format is 2"),
    ('format = 1\nname = "X"\ngas = "ar"\nparameters = "2012"\ngenerator = "philox"\n',
     "gas is 'ar'"),
    ('format = 1\nname = "X"\ngas = "n2"\nparameters = "2000"\ngenerator = "philox"\n',
     "the shipped N2 tables are 2012"),
    ('format = 1\nname = "X"\ngas = "he"\nparameters = "2012"\ngenerator = "rand"\n',
     "generator is 'rand'"),
    ('format = 1\nname = ""\ngas = "he"\nparameters = "2012"\ngenerator = "philox"\n',
     "name must be 1 to 60"),
    ('format = 1\nname = "X"\ngas = "he"\nparameters = "2012"\ngenerator = "philox"\n'
     "itn = 0\n", "itn is 0"),
])
def test_a_method_file_that_cannot_be_used_is_refused_by_key(tmp_path, body, match):
    f = tmp_path / "bad.toml"
    f.write_text(body, encoding="utf-8")
    with pytest.raises(methods.MethodError, match=match):
        methods.load(f)


def test_a_key_left_out_takes_the_2012_value(tmp_path):
    f = tmp_path / "short.toml"
    f.write_text('format = 1\nname = "Short"\ngas = "n2"\nparameters = "2012"\n'
                 'generator = "ranlux"\nimp = 500\n', encoding="utf-8")
    m = methods.load(f)
    assert m.settings.values() == {**settings.DEFAULTS.values(), "imp": 500}


# --- the record, the summary and the study folder ------------------------------------------

def test_the_record_and_the_summary_carry_the_method(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    jobs = [Job(inp, "he", 1, tmp_path / "runs"),
            Job(inp, "he", 1, tmp_path / "runs", generator="ranlux")]
    s = run_many(jobs, 2, launcher=launcher)
    csv_path, json_path = s.write(tmp_path / "runs")
    recs = [json.loads((j.run_dir / "record.json").read_text(encoding="utf-8")) for j in jobs]
    assert [r["method"] for r in recs] == ["2012-philox-he", "2012-he"]
    assert [r["method_file"] for r in recs] == [None, None]
    assert [r["method"] for r in json.loads(json_path.read_text(encoding="utf-8"))["runs"]] \
        == ["2012-philox-he", "2012-he"]
    assert [line.split(",")[5] for line in csv_path.read_text().splitlines()] == \
        ["method", "2012-philox-he", "2012-he"]


def test_a_run_from_a_method_file_records_its_name_and_sha256(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    m = methods.save(tmp_path / "m.toml", "My method", "n2", "2012", "philox",
                     settings.resolve(None, itn=2))
    b = Batch((inp,), tmp_path / "runs", method=m.ref, seeds=(1,), split=None)
    s = run_many(b.jobs(), 1, launcher=launcher)
    _, json_path = s.write(tmp_path / "runs")
    rec = json.loads((b.jobs()[0].run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["method"] == "My method" and rec["binary"]["gas"] == "n2"
    assert rec["method_file"] == {"path": str(tmp_path / "m.toml"), "sha256": m.sha256}
    assert json.loads(json_path.read_text(encoding="utf-8"))["runs"][0]["method_file"] == \
        rec["method_file"]
    para = methods.text(methods.read_records([tmp_path / "runs"]))
    assert "The nitrogen calculations used the method My method: the MOBCAL 2012 nitrogen" in para


@pytest.mark.parametrize("old, gas, new", [("current", "he", "2012-philox-he"),
                                           ("current", "n2", "2012-philox-n2"),
                                           ("2012", "n2", "2012-n2"), ("2000", "he", "2000-he"),
                                           ("custom", "he", "custom")])
def test_a_record_from_before_methods_carried_their_gas_still_reads(tmp_path, old, gas, new):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, gas, 1, tmp_path / "runs")
    run_many([job], 1, launcher=launcher)
    f = job.run_dir / "record.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    del doc["method_file"]  # as the version before wrote it
    doc["method"] = old
    f.write_text(json.dumps(doc), encoding="utf-8")
    assert methods.record_method(doc) == new
    assert run.read_records(tmp_path / "runs")[job.label]["method"] == new
    methods.text(methods.read_records([job.run_dir]))  # reads, whatever the old name


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


def test_drain_lets_the_runs_in_flight_finish_and_starts_nothing_more(tmp_path):
    out = tmp_path / "runs"
    jobs = [Job(write_input(tmp_path / f"s{i}.mfj", "sleep 2"), "he", i, out) for i in (1, 2)]
    jobs += [Job(write_input(tmp_path / f"later{i}.mfj", "ok"), "he", i, out) for i in (3, 4)]
    stop = Stop()
    started = []

    def on_start(job):
        started.append(job)
        if len(started) == 2:
            stop.drain()
    s = run_many(jobs, workers=2, launcher=launcher, stop=stop, on_start=on_start)
    assert [r.status for r in s.results] == ["ok", "ok", "waiting", "waiting"]
    assert s.results[2].message == "not started: the batch was paused"
    assert not jobs[2].run_dir.exists() and not s.failed and not s.stopped
    assert [r.job for r in s.waiting] == jobs[2:] and "2 waiting" in str(s)
    _, json_path = s.write(out)
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert [r["name"] for r in doc["runs"]] == sorted(j.label for j in jobs[:2])
    assert doc["batch"] == [j.label for j in jobs[:2]]


def test_a_waiting_run_leaves_an_earlier_record_of_its_name_in_the_summary(tmp_path):
    out = tmp_path / "runs"
    job = Job(write_input(tmp_path / "a.mfj", "ok"), "he", 1, out)
    run_many([job], 1, launcher=launcher).write(out)
    stop = Stop()
    stop.drain()
    s = run_many([job], 1, launcher=launcher, stop=stop)
    assert s.results[0].waiting
    _, json_path = s.write(out)
    assert [r["status"] for r in json.loads(json_path.read_text())["runs"]] == ["ok"]


def test_stop_ends_a_split_run_before_its_combining_run(tmp_path):
    job = Job(write_input(tmp_path / "s.mfj", "sleep 30"), "he", 1, tmp_path / "runs", split=3)
    stop = Stop()
    run.threading.Timer(1.5, stop).start()
    t0 = time.perf_counter()
    r = run_many([job], 1, launcher=launcher, stop=stop).results[0]
    assert time.perf_counter() - t0 < 15
    assert r.status == "stopped" and not (job.run_dir / "mobcal.out").exists()


def test_no_process_opens_a_console_window(tmp_path, monkeypatch):
    # The window's mobcal-gui.exe has no console, and Windows gives each console program it
    # starts a console window of its own unless told not to: one per run, and one per taskkill.
    seen = []
    popen, sub_run = run.subprocess.Popen, run.subprocess.run

    def spy_popen(*a, **kw):
        seen.append(("Popen", kw))
        return popen(*a, **kw)

    def spy_run(*a, **kw):
        seen.append(("run", kw))
        return sub_run(*a, **kw)

    monkeypatch.setattr(run.subprocess, "Popen", spy_popen)
    monkeypatch.setattr(run.subprocess, "run", spy_run)
    job = Job(write_input(tmp_path / "s.mfj", "sleep 30"), "he", 1, tmp_path / "runs", split=2)
    stop = Stop()
    run.threading.Timer(1.5, stop).start()
    assert run_many([job], 1, launcher=launcher, stop=stop).results[0].status == "stopped"
    kinds = [k for k, _ in seen]
    assert kinds.count("Popen") >= 2  # the two workers, and on Windows taskkill's own Popen
    if sys.platform == "win32":
        assert kinds.count("run") >= 2  # taskkill, once per worker at least
        assert all(kw.get("creationflags", 0) & run.subprocess.CREATE_NO_WINDOW
                   for _, kw in seen)
    else:
        assert all(kw.get("start_new_session") for k, kw in seen if k == "Popen")


def test_an_interrupt_kills_the_program_it_was_waiting_for(tmp_path, monkeypatch):
    # Ctrl+C in a terminal does not reach a program with no console or its own process group.
    job = Job(write_input(tmp_path / "s.mfj", "sleep 30"), "he", 1, tmp_path / "runs")
    procs = []
    start = run._start

    def interrupted(command, d, running):
        proc = start(command, d, running)
        procs.append(proc)
        monkeypatch.setattr(proc, "wait", _interrupt_once(proc.wait))
        return proc

    monkeypatch.setattr(run, "_start", interrupted)
    t0 = time.perf_counter()
    with pytest.raises(KeyboardInterrupt):
        run.run_one(job, launcher)
    assert procs and procs[0].wait(timeout=15) is not None
    assert time.perf_counter() - t0 < 15


def _interrupt_once(wait):
    calls = []

    def fake(timeout=None):
        if not calls:
            calls.append(1)
            raise KeyboardInterrupt
        return wait(timeout)

    return fake


# --- the batch as data -------------------------------------------------------------------

def test_a_batch_round_trips_through_the_queue_file(tmp_path):
    b1 = Batch((CHOLINE,), tmp_path / "runs", method="2012-he", gas="n2", seeds=(1, 2),
               settings=settings.resolve(None, imp=25), split=4, workers=2)
    b2 = Batch((CHOLINE,), tmp_path / "runs", method="2000-he", parameters=None, split="auto")
    m = methods.save(tmp_path / "m.toml", "Mine", "he", "2012", "ranlux", settings.DEFAULTS)
    b3 = Batch((CHOLINE,), tmp_path / "runs", method=m.ref)
    path = batch.save([b1, b2, b3], tmp_path / "queue.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["batches"].append({**doc["batches"][1], "method": "1996"})
    path.write_text(json.dumps(doc), encoding="utf-8")
    got, problems = batch.load(path)
    assert got == [b1, b2, b3] and [b.jobs() for b in got] == [b1.jobs(), b2.jobs(), b3.jobs()]
    assert problems == ["queued batch 4: no method is named '1996'; the methods are 2012-he, "
                        "2012-n2, 2012-philox-he, 2012-philox-n2, 2000-he, or a method file's "
                        "path"]
    assert [b.title() for b in got] == ["Custom (from MOBCAL 2012 (He))", "MOBCAL 2000 (He)",
                                        "Mine"]


def test_a_queue_file_from_before_one_method_a_batch_loads_one_batch_per_gas(tmp_path):
    old = {"format": 1, "inputs": [str(CHOLINE)], "out_dir": str(tmp_path / "runs"),
           "seeds": [1], "parameters": None, "generator": None, "settings": None,
           "split": "auto", "workers": None, "skip_done": False}
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"format": 1, "batches": [
        {**old, "gases": ["he", "n2"], "method": "current"},
        {**old, "gases": ["n2"], "method": "2012"},
        {**old, "gases": ["he"], "method": "2000"},
        {**old, "gases": ["he"], "method": "1996"}]}), encoding="utf-8")
    got, problems = batch.load(path)
    assert [(b.method, b.gas, b.method_now) for b in got] == [
        ("2012-philox-he", None, "2012-philox-he"), ("2012-philox-n2", None, "2012-philox-n2"),
        ("2012-n2", None, "2012-n2"), ("2000-he", None, "2000-he")]
    assert problems == ["queued batch 4: no method was named '1996'; the methods were current, "
                        "2012, 2000"]


def test_a_paused_batch_runs_only_its_remaining_runs_and_keeps_them_in_the_file(tmp_path):
    out = tmp_path / "runs"
    a = write_input(tmp_path / "a.mfj", "ok")
    full = Batch((a,), out, seeds=(1, 2, 3))
    run_many(full.jobs(), 3, launcher=launcher)  # every run complete in the folder
    labels = [j.label for j in full.jobs()]
    # Queued to run them again and paused after the first: the other two are complete in the
    # folder from the earlier calculation, and skip_done would skip exactly those.
    paused = Batch((a,), out, seeds=(1, 2, 3), remaining=labels[1:])
    assert [j.label for j in paused.to_run()] == labels[1:]
    assert dataclasses.replace(paused, skip_done=True).to_run() == paused.to_run()
    assert Batch((a,), out, seeds=(1, 2, 3), skip_done=True).to_run() == []
    path = batch.save([paused, full], tmp_path / "queue.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["format"] == 3 and doc["batches"][0]["remaining"] == labels[1:]
    assert doc["batches"][1]["remaining"] is None
    assert batch.load(path) == ([paused, full], [])


def test_a_queue_file_of_format_2_still_loads(tmp_path):
    b = Batch((CHOLINE,), tmp_path / "runs", method="2012-n2", seeds=(1, 2))
    entry = b.to_dict()
    del entry["remaining"]
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"format": 2, "batches": [{**entry, "format": 2}]}),
                    encoding="utf-8")
    assert batch.load(path) == ([b], [])


def test_a_batch_refuses_what_cannot_run(tmp_path):
    with pytest.raises(BatchError, match="no method is named '2000'"):
        Batch((CHOLINE,), tmp_path, method="2000")
    with pytest.raises(BatchError, match="gas must be one of"):
        Batch((CHOLINE,), tmp_path, gas="ar")
    with pytest.raises(BatchError, match="split must be"):
        Batch((CHOLINE,), tmp_path, split="sometimes")
    with pytest.raises(BatchError, match="no shipped N2 set is named '2000'"):
        Batch((CHOLINE,), tmp_path, method="2012-n2", parameters="2000").jobs()


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


def test_a_split_waits_on_its_costliest_block():
    c = estimate.Cost(10.0, 400.0, floor=30.0)
    assert c.wall(10) == 60.0 and c.wall(40) == 50.0  # 2 * 10 + max(400 / W, 30)
    assert c.widest == pytest.approx(400 / 30) and c.efficiency(10) == pytest.approx(410 / 600)
    assert estimate.Cost(10.0, 400.0).widest == float("inf")
    # The floor is the slowest velocity point's block: SLOWEST times the mean block, per set.
    two = estimate.cost(21, 2, "n2")
    assert two.floor == pytest.approx(2 * 3.4 * settings.DEFAULTS.imp * 1.148e-2)


def test_allocation(tmp_path):
    """The throughput mode is the rule --split auto had before the modes."""
    jobs = [Job(CHOLINE, "he", s, tmp_path) for s in range(4)]
    most = estimate.THROUGHPUT
    one = estimate.allocate(jobs[:1], cpus=80, mode=most)
    assert one.workers == 1 and one.jobs[0].split == estimate.MAX_SPLIT
    four = estimate.allocate(jobs, cpus=80, mode=most)
    assert four.workers == 4 and {j.split for j in four.jobs} == {20}
    many = estimate.allocate(jobs, cpus=4, mode=most)
    assert many.workers == 4 and {j.split for j in many.jobs} == {None}
    two_cores = estimate.allocate(jobs[:1], cpus=2, mode=most)
    assert two_cores.jobs[0].split == 2  # 2 * 2.25 + 192 / 2 is well under 0.8 * 194.6
    # The prologue dominating, as in the 2000 release's example at imp 25 with its projection
    # pass per set: no split however many cores, in any mode.
    st = settings.resolve(None, imp=1)
    for mode in estimate.MODES:
        lean = estimate.allocate([Job(CHOLINE, "he", 1, tmp_path, settings=st)], cpus=80,
                                 mode=mode)
        assert lean.jobs[0].split is None
    # A split never exceeds what its costliest block lets it use, which is never more than
    # the blocks there are to deal: 5 blocks, the slowest twice the mean in helium, so 3.
    st = settings.resolve(None, itn=1, inp=5, imp=100_000)
    assert estimate.allocate([Job(CHOLINE, "he", 1, tmp_path, settings=st)],
                             cpus=80).jobs[0].split == 3
    with pytest.raises(ValueError, match="mode must be one of"):
        estimate.allocate(jobs, cpus=8, mode="fastest")


# (gas, cores, mode) -> (runs at once, split) for 1, 8, 40 and 80 choline runs at the 2012
# settings; None is one process per run.
MODES = {
    ("he", 8, "in-order"): [(1, 8)] * 4,
    ("he", 8, "balanced"): [(1, 8)] * 4,
    ("he", 8, "throughput"): [(1, 8), (8, None), (8, None), (8, None)],
    ("he", 40, "in-order"): [(1, 40)] * 4,
    ("he", 40, "balanced"): [(1, 40), (3, 13), (3, 13), (3, 13)],
    ("he", 40, "throughput"): [(1, 40), (8, 5), (40, None), (40, None)],
    ("n2", 8, "in-order"): [(1, 8)] * 4,
    ("n2", 8, "balanced"): [(1, 8)] * 4,
    ("n2", 8, "throughput"): [(1, 8), (8, None), (8, None), (8, None)],
    ("n2", 40, "in-order"): [(1, 40)] * 4,
    ("n2", 40, "balanced"): [(1, 40)] * 4,
    ("n2", 40, "throughput"): [(1, 40), (8, 5), (40, None), (40, None)],
}


@pytest.mark.parametrize("gas, cores, mode", list(MODES))
def test_each_mode_allocates(tmp_path, gas, cores, mode):
    for n, (workers, split) in zip((1, 8, 40, 80), MODES[(gas, cores, mode)], strict=True):
        p = estimate.allocate([Job(CHOLINE, gas, s, tmp_path) for s in range(n)], cpus=cores,
                              mode=mode)
        assert (p.workers, {j.split for j in p.jobs}) == (workers, {split}), n
        assert p.mode == mode and p.processes <= cores
        assert f"({estimate.MODE_TITLES[mode].lower()})" in estimate.describe(p)


def test_the_balanced_mode_keeps_its_efficiency(tmp_path):
    p = estimate.allocate([Job(CHOLINE, "he", s, tmp_path) for s in range(12)], cpus=40)
    c = estimate.cost(21, 1, "he")
    w = p.jobs[0].split
    assert p.mode == estimate.DEFAULT_MODE == estimate.BALANCED
    assert c.efficiency(w) >= estimate.BALANCE > c.efficiency(40 // (p.workers - 1))


def test_cores_a_run_cannot_use_take_another_run(tmp_path):
    """Finish in order, a run whose costliest block caps its split leaves cores over, and they
    take a further run at the same split: 40 blocks, the slowest 3.4 times the mean, so 12."""
    st = settings.resolve(None, itn=1)
    jobs = [Job(CHOLINE, "n2", s, tmp_path, settings=st) for s in range(4)]
    p = estimate.allocate(jobs, cpus=40, mode=estimate.IN_ORDER)
    assert p.workers == 3 and {j.split for j in p.jobs} == {12}


def test_cores_are_physical_with_a_fallback(monkeypatch):
    monkeypatch.setattr(run.psutil, "cpu_count", lambda logical=True: 40 if not logical else 80)
    monkeypatch.setattr(run.os, "cpu_count", lambda: 80)
    assert run.cores() == 40 and run.processors() == 80
    monkeypatch.setattr(run.psutil, "cpu_count", lambda logical=True: None)
    assert run.cores() == 80
    monkeypatch.setattr(run.os, "cpu_count", lambda: None)
    assert run.cores() == 1 and run.processors() == 1
    assert estimate.allocate([], mode=estimate.IN_ORDER).cpus == 1


def test_the_mode_on_the_command_line(tmp_path):
    def args(*argv):
        return cli.parser().parse_args(["run", str(CHOLINE), *argv])

    a = args("--mode", "in-order")
    assert cli.batch_from_args(a).split == batch.AUTO and a.mode == "in-order"
    assert cli.batch_from_args(args()).split is None  # no --mode, no --split: one process
    with pytest.raises(cli.UsageError, match="--mode chooses under --split auto"):
        cli.batch_from_args(args("--mode", "balanced", "--split", "4"))
    with pytest.raises(SystemExit):
        args("--mode", "fastest")


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
    assert ("The nitrogen calculations used the method of the MOBCAL 2012 release with its "
            "random number generator replaced") in para
    assert refs.splitlines()[0].startswith("1. Mesleh, M. F.")
    assert len(refs.splitlines()) == 7
    assert cli.main(["methods-text", str(jobs[0].run_dir)]) == 0
    one = capsys.readouterr().out
    assert "at seed 1." in one and "nitrogen" not in one
    assert cli.main(["methods-text", str(tmp_path / "nothing")]) == 2
