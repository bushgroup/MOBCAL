"""The result file, NAME.result.json (docs/result-file.md): written for every run that reaches
its directory, valid against src/mobcal/io/result.schema.json, holding the output's values to
the printed digit and both inputs, through the stand-in binary."""

import dataclasses
import hashlib
import json
import time
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from mobcal import fortran, methods, parameters, run, settings
from mobcal.io import ion
from mobcal.io.mfj import Mfj
from mobcal.io.outfile import OutFile
from mobcal.run import Job, Stop, run_many, run_one
from test_run import CHOLINE_ION, launcher, write_input

SRC = Path(run.__file__).resolve().parent
SCHEMA = SRC / "io" / "result.schema.json"


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    """The result schema with the ion and method schemas registered under their $id, so its
    relative $refs resolve with no network."""
    docs = [json.loads(p.read_text(encoding="utf-8"))
            for p in (SCHEMA, ion.SCHEMA, methods.SCHEMA)]
    jsonschema.Draft202012Validator.check_schema(docs[0])
    registry = Registry().with_resources((d["$id"], Resource.from_contents(d)) for d in docs)
    return jsonschema.Draft202012Validator(docs[0], registry=registry)


def result(job: Job) -> dict:
    return json.loads(job.result_path.read_text(encoding="utf-8"))


def valid(validator, doc: dict) -> None:
    errors = [f"{list(e.path)}: {e.message[:160]}" for e in validator.iter_errors(doc)]
    assert not errors, errors


def ion_file(path: Path, label: str) -> Path:
    return dataclasses.replace(ion.Ion.read(CHOLINE_ION), label=label).write(path)


# --- an ok run --------------------------------------------------------------------------------

def test_an_ok_run_writes_a_valid_result_beside_the_record(tmp_path, validator):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "he", 5013489, tmp_path / "runs")
    r = run_one(job, launcher)
    assert r.ok and r.message == ""
    assert job.result_path == job.run_dir / "ok-he-5013489.result.json"
    raw = job.result_path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"}\n")
    doc = result(job)
    valid(validator, doc)
    assert list(doc) == ["format", "version", "status", "message", "software", "started",
                         "finished", "seconds", "gas", "temperature", "seed", "inputs",
                         "results", "mobcal"]
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert doc["status"] == "ok" and doc["message"] is None
    assert doc["started"] == rec["started"] and doc["seconds"] == rec["seconds"]
    assert doc["gas"] == "He" and doc["seed"] == 5013489
    assert doc["temperature"] == {"value": 301, "unit": "K"}
    assert doc["software"]["version"] == rec["mobcal_version"]
    assert doc["software"]["build"] == rec["binary"]["build"]

    # the results are the output's and the record's, to the printed digit
    o = OutFile.read(r.output)
    cs = doc["results"]["cross_sections"]
    assert {k: v["value"] for k, v in cs.items()} == o.cross_sections == rec["cross_sections"]
    assert {v["unit"] for v in cs.values()} == {"angstrom^2"}
    assert cs["TM"]["standard_deviation"] == {"value": 0.92, "unit": "percent"}
    assert doc["results"]["conformers"] == [{"set": 1, **cs}]
    assert doc["results"]["trajectories"] == {"total": 400000, "failed": 3}

    m = doc["mobcal"]
    assert m["generator"] == "philox" and m["split"] is None
    assert m["settings"] == {"temperature": 301, "imp": 1000, "itn": 10, "inp": 40,
                             "inum": 250000, "inor": 30}
    assert m["parameters"] == {"name": "MOBCAL 2012 helium",
                               "sha256": parameters.SHA256[parameters.FILES["he"]],
                               "shipped": True}
    assert m["staged_input"] == {"name": "ok.mfj",
                                 "sha256": hashlib.sha256(inp.read_bytes()).hexdigest()}
    assert m["files"] == {"output": "mobcal.out", "record": "record.json",
                          "console_log": "stdout.log"}
    s = m["summary"]
    assert s["lines"] == o.summary_lines and s["program_version"] == "junkn.f"
    assert s["input_file_name"] == "ok.mfj" and s["input_label"] == "ok"
    assert s["hard_sphere"] == {"trajectories": 250000, "minimum_reflections": None,
                                "maximum_reflections": 4}
    assert s["trajectory_parameters"] == {"sw1": 5e-5, "sw2": 5e-3, "dtsf1": 0.5, "dtsf2": 0.1}
    assert {k: v["value"] for k, v in s["inverse_mobilities"].items()} == o.inverse_mobilities
    assert {v["unit"] for v in s["inverse_mobilities"].values()} == {"V s m^-2"}
    assert s["asymmetry_parameter"] == 1.2982
    assert s["conformers"] == [{"set": 1, "inverse_mobilities": s["inverse_mobilities"],
                                "asymmetry_parameter": 1.2982}]


def test_a_mfj_input_is_embedded_as_the_ion_document_it_reads_as(tmp_path, validator):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    job = Job(inp, "he", 7, tmp_path)
    run_one(job, launcher)
    entry = result(job)["inputs"]["ion"]
    assert entry["format"] == "mobcal-ion" and entry["converted_from"] == "mfj"
    assert entry["embedded"] is True
    assert entry["file"] == {"name": "ok.mfj",
                             "sha256": hashlib.sha256(inp.read_bytes()).hexdigest()}
    assert entry["document"]["import"]["source"]["sha256"] == entry["file"]["sha256"]
    # the embedded document writes back the input the program read
    back = ion.Ion.parse(json.dumps(entry["document"]))
    table = parameters.load(parameters.default_path("he"), gas="he")
    assert Mfj.parse(back.mfj(table).text()) == Mfj.read(inp)


def test_an_ion_file_is_embedded_as_its_document(tmp_path, validator):
    inp = ion_file(tmp_path / "chol.ion.json", "ok")
    job = Job(inp, "n2", 8, tmp_path)
    r = run_one(job, launcher)
    doc = result(job)
    valid(validator, doc)
    entry = doc["inputs"]["ion"]
    assert entry["converted_from"] is None and entry["embedded"] is True
    assert entry["document"] == json.loads(inp.read_text(encoding="utf-8"))
    assert entry["file"] == {"name": "chol.ion.json",
                             "sha256": hashlib.sha256(inp.read_bytes()).hexdigest()}
    staged = job.run_dir / job.staged
    assert doc["mobcal"]["staged_input"] == {
        "name": "chol.mfj", "sha256": hashlib.sha256(staged.read_bytes()).hexdigest()}
    # nitrogen: TM only, no hard-sphere pass
    assert list(doc["results"]["cross_sections"]) == ["TM"] and r.cross_sections == {"TM": 51.5}
    assert doc["gas"] == "N2" and doc["mobcal"]["summary"]["hard_sphere"] is None
    assert list(doc["mobcal"]["summary"]["inverse_mobilities"]) == ["TM"]


def test_reference_records_the_ion_by_its_file_alone(tmp_path, validator):
    inp = ion_file(tmp_path / "chol.ion.json", "ok")
    job = Job(inp, "he", 9, tmp_path, result_ion="reference")
    run_one(job, launcher)
    doc = result(job)
    valid(validator, doc)
    entry = doc["inputs"]["ion"]
    assert entry["embedded"] is False and entry["document"] is None
    assert entry["file"]["sha256"] == hashlib.sha256(inp.read_bytes()).hexdigest()
    assert doc["inputs"]["method"]["embedded"] is True  # the method always is
    assert job == Job(inp, "he", 9, tmp_path)  # not a setting of the calculation
    with pytest.raises(ValueError, match="result_ion"):
        Job(inp, "he", 9, tmp_path, result_ion="maybe")


def test_several_coordinate_sets(tmp_path, validator):
    job = Job(write_input(tmp_path / "three.mfj", "sets 3"), "he", 7, tmp_path)
    run_one(job, launcher)
    doc = result(job)
    valid(validator, doc)
    res, s = doc["results"], doc["mobcal"]["summary"]
    assert [c["set"] for c in res["conformers"]] == [1, 2, 3]
    assert "standard_deviation" not in res["cross_sections"]["TM"]  # not printed for several
    assert all("standard_deviation" not in c["TM"] for c in res["conformers"])
    assert s["hard_sphere"]["minimum_reflections"] == 3
    assert [c["set"] for c in s["conformers"]] == [1, 2, 3]
    assert s["asymmetry_parameter"] is not None


def test_a_divided_run_records_its_split(tmp_path, validator):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    serial = Job(inp, "he", 7, tmp_path / "serial")
    split = Job(inp, "he", 7, tmp_path / "split", split=2)
    run_one(serial, launcher)
    r = run_one(split, launcher)
    assert r.ok
    a, b = result(serial), result(split)
    valid(validator, b)
    assert b["mobcal"]["split"] == 2 and a["mobcal"]["split"] is None
    assert a["results"] == b["results"]


# --- runs that did not end ok ----------------------------------------------------------------

@pytest.mark.parametrize("label", ["refuse", "crash", "silent"])
def test_a_failed_run_has_no_results_and_every_other_key(tmp_path, validator, label):
    job = Job(write_input(tmp_path / f"{label}.mfj", label), "he", 3, tmp_path)
    r = run_one(job, launcher)
    assert not r.ok
    doc = result(job)
    valid(validator, doc)
    assert doc["status"] == "failed" and doc["message"] == r.message
    assert doc["results"] is None and doc["mobcal"]["summary"] is None
    assert doc["inputs"]["ion"]["document"] is not None
    assert doc["inputs"]["method"]["name"] == "2012-philox-he"


def test_a_mfj_no_table_can_name_is_recorded_by_its_file(tmp_path, validator):
    # Bromide, key 35, which no shipped table defines: no ion document can be read from it, and
    # the real program refuses it after the run directory is made.
    inp = tmp_path / "hbr.mfj"
    inp.write_text("refuse\n1\n2\nang\ncalc\n1.0000\n 0.0 0.0 0.0 35 0.5\n 1.41 0.0 0.0 1 0.5\n",
                   encoding="latin-1", newline="\n")
    job = Job(inp, "he", 1, tmp_path)
    r = run_one(job, launcher)
    assert r.message == "exit 1: type not defined for atom number      1"
    doc = result(job)
    valid(validator, doc)
    assert doc["inputs"]["ion"]["embedded"] is False and doc["inputs"]["ion"]["document"] is None
    assert doc["inputs"]["ion"]["converted_from"] == "mfj"


def test_a_run_refused_before_its_directory_leaves_no_result(tmp_path):
    bad = tmp_path / "bad.mfj"
    bad.write_text("label\n1\n1\n ang\ncalc\n1.0\n0 0 0 1 1\n", encoding="latin-1")
    job = Job(bad, "he", 1, tmp_path / "runs")
    assert not run_one(job, launcher).ok and not job.run_dir.exists()


def test_a_stopped_run_writes_its_result(tmp_path, validator):
    out = tmp_path / "runs"
    job = Job(write_input(tmp_path / "s.mfj", "sleep 30"), "he", 1, out)
    later = Job(write_input(tmp_path / "later.mfj", "ok"), "he", 2, out)
    stop = Stop()
    run.threading.Timer(1.0, stop).start()
    t0 = time.perf_counter()
    s = run_many([job, later], workers=1, launcher=launcher, stop=stop)
    assert time.perf_counter() - t0 < 15
    assert [r.status for r in s.results] == ["stopped", "stopped"]
    doc = result(job)
    valid(validator, doc)
    assert doc["status"] == "stopped" and doc["message"].startswith("stopped")
    assert doc["results"] is None and doc["mobcal"]["summary"] is None
    assert not later.run_dir.exists()  # never started: no directory, no result


def test_a_stale_result_is_removed_before_the_run(tmp_path):
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path)
    job.run_dir.mkdir(parents=True)
    stale = job.run_dir / "old-name.result.json"
    stale.write_text("{}", encoding="utf-8")
    run_one(job, launcher)
    assert not stale.exists() and job.result_path.is_file()


def test_a_result_that_cannot_be_written_is_reported_and_the_record_stands(tmp_path,
                                                                           monkeypatch):
    def refuse(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(run, "write_result", refuse)
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path)
    r = run_one(job, launcher)
    assert r.ok and r.message == "result file not written: disk full"
    assert "result file not written" in str(r)
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["status"] == "ok" and rec["message"] == ""
    assert not job.result_path.exists()


# --- the embedded method: always a method document that makes the run's jobs again ----------

def reload(doc: dict, tmp_path: Path, name: str) -> methods.Method:
    path = tmp_path / f"{name}.method.json"
    path.write_text(json.dumps(doc | {"name": name}), encoding="utf-8")
    return methods.load(path)


def same_calculation(m: methods.Method, job: Job) -> bool:
    return m.matches(job.gas, job.set_name, job.table_sha256, job.generator, job.settings)


def test_a_shipped_method_embeds_its_file(tmp_path, validator):
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path, generator="ranlux",
              method_from=methods.METHODS["2012-he"])
    run_one(job, launcher)
    entry = result(job)["inputs"]["method"]
    shipped = methods.METHODS["2012-he"]
    assert entry["source"] == "shipped" and entry["name"] == "2012-he"
    assert entry["file"] == {"name": "2012-he.method.json", "sha256": shipped.sha256}
    assert entry["from"] is None and entry["overrides"] == {}
    assert entry["document"] == json.loads(shipped.path.read_text(encoding="utf-8"))
    assert same_calculation(reload(entry["document"], tmp_path, "Again"), job)


def test_a_method_file_embeds_its_document(tmp_path, validator):
    st = settings.DEFAULTS.replace(temperature=298.15, imp=25)
    m = methods.save(tmp_path / "mine", "Mine at 298.15 K", "he", "2000", "ranlux", st,
                     seed=42, description="ours")
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 42, tmp_path / "runs",
              parameters=m.table_path(), generator="ranlux", settings=st, method_from=m)
    run_one(job, launcher)
    doc = result(job)
    valid(validator, doc)
    entry = doc["inputs"]["method"]
    assert entry["source"] == "file" and entry["name"] == "Mine at 298.15 K"
    assert entry["file"] == {"name": "mine.method.json", "sha256": m.sha256}
    assert entry["document"] == json.loads(m.path.read_text(encoding="utf-8"))
    assert entry["document"]["seed"] == 42 and doc["seed"] == 42
    assert doc["temperature"] == {"value": 298.15, "unit": "K"}
    assert same_calculation(reload(entry["document"], tmp_path, "Again"), job)


def test_a_custom_run_embeds_the_method_its_fields_make(tmp_path, validator):
    base = methods.METHODS["2012-philox-he"]
    st = settings.DEFAULTS.replace(temperature=298, imp=25)
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path, settings=st,
              method_from=base)
    assert job.method == "custom"
    run_one(job, launcher)
    doc = result(job)
    valid(validator, doc)
    entry = doc["inputs"]["method"]
    assert entry["source"] == "custom" and entry["name"] == "custom" and entry["file"] is None
    assert entry["from"] == "2012-philox-he"
    assert entry["overrides"] == {"temperature": 298, "imp": 25}
    assert entry["document"]["name"] == "Custom" and "seed" not in entry["document"]
    assert same_calculation(reload(entry["document"], tmp_path, "Again"), job)


def test_a_custom_table_of_ones_own_is_named_by_path_and_sha256(tmp_path, validator):
    mine = tmp_path / "mine.toml"
    mine.write_bytes(parameters.default_path("he").read_bytes() + b"\n# a copy of my own\n")
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path / "runs",
              parameters=mine)
    run_one(job, launcher)
    doc = result(job)
    valid(validator, doc)
    entry = doc["inputs"]["method"]
    assert entry["source"] == "custom" and entry["from"] is None and entry["overrides"] == {}
    assert entry["document"]["parameters"] == {
        "path": mine.resolve().as_posix(), "sha256": hashlib.sha256(mine.read_bytes()).hexdigest()}
    assert doc["mobcal"]["parameters"]["shipped"] is False
    assert same_calculation(reload(entry["document"], tmp_path, "Again"), job)


# --- the schema holds the writer's constants -------------------------------------------------

def test_the_schema_holds_the_writers_constants():
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    d = s["$defs"]
    assert s["properties"]["format"]["const"] == run.RESULT_FORMAT
    assert s["properties"]["version"]["const"] == run.RESULT_VERSION
    assert s["properties"]["gas"]["enum"] == sorted(run.GAS_FORMULA.values())
    assert set(s["properties"]["gas"]["enum"]) == {run.GAS_FORMULA[g] for g in fortran.GASES}
    assert d["area"]["properties"]["unit"]["const"] == "angstrom^2"
    assert d["inverse_mobility"]["properties"]["unit"]["const"] == "V s m^-2"
    assert d["mobcal"]["properties"]["generator"]["enum"] == list(run.GENERATORS)
    assert d["ion_input"]["properties"]["format"]["const"] == ion.FORMAT
    assert d["method_input"]["properties"]["format"]["const"] == methods.FORMAT
    assert d["method_input"]["properties"]["overrides"]["propertyNames"]["enum"] == \
        list(run._METHOD_KEYS)
    assert d["mobcal"]["properties"]["settings"]["required"] == list(settings.NAMES)
    assert s["$id"].endswith("/src/mobcal/io/result.schema.json")
    # the two relative references resolve to exactly the input schemas' $id
    from urllib.parse import urljoin
    ion_id = json.loads(ion.SCHEMA.read_text(encoding="utf-8"))["$id"]
    method_id = json.loads(methods.SCHEMA.read_text(encoding="utf-8"))["$id"]
    assert urljoin(s["$id"], "ion.schema.json") == ion_id
    assert urljoin(s["$id"], "../methods/method.schema.json") == method_id


def test_the_schema_refuses_what_the_format_refuses(tmp_path, validator):
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 1, tmp_path)
    run_one(job, launcher)
    good = result(job)

    def bad(change) -> bool:
        doc = json.loads(json.dumps(good))
        change(doc)
        return not validator.is_valid(doc)

    assert bad(lambda d: d.update(extra=1))
    assert bad(lambda d: d.update(gas="N2"))  # nitrogen with PA and EHS
    assert bad(lambda d: d["results"]["cross_sections"]["TM"].update(unit="nm^2"))
    assert bad(lambda d: d.update(message="why"))  # ok with a message
    assert bad(lambda d: d.update(status="failed"))  # failed without one
    assert bad(lambda d: d["inputs"]["ion"].update(embedded=False))  # yet a document
    assert bad(lambda d: d["inputs"]["ion"]["document"].update(units="parsec"))
    assert bad(lambda d: d["inputs"]["method"]["document"].update(gas="ar"))
    assert bad(lambda d: d["results"]["cross_sections"].update(
        XX=d["results"]["cross_sections"]["PA"]))  # a method the format does not name
