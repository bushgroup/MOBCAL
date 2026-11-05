"""The methods, the batch, the estimate and the study folder: the Qt-free half of the window.

Through the stand-in binary where a run is needed. A shipped method is held to the jobs the
version before methods carried their gas made for the same calculation, and to a command line
that spells its fields out, by the jobs they make and the bytes they stage: the program reads
nothing else, so equal staged directories are equal outputs at the same seed.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import time
from pathlib import Path

import jsonschema
import pytest

from mobcal import batch, cli, estimate, fortran, methods, parameters, run, settings
from mobcal.batch import Batch, BatchError
from mobcal.io.infile import GENERATORS, MAX_SEED
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
                    settings=settings.resolve(temperature=298.0, imp=25)),
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


def test_run_has_no_settings_file_a_method_carries_the_settings(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["run", str(CHOLINE), "--settings", "s.toml"])
    capsys.readouterr()


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
    st = settings.resolve(temperature=298.15, itn=5)
    mine = tmp_path / "mine.method.json"
    m = methods.save(mine, "Mine at 298.15 K", "he", "2000", "ranlux", st)
    again = methods.load(mine)
    assert m == again and not m.shipped and m.key == "Mine at 298.15 K"
    assert (m.gas, m.parameters, m.table, m.generator) == ("he", "2000", None, "ranlux")
    assert m.settings.values() == st.values() and m.ref == str(mine)
    assert m.description is None
    text = mine.read_text(encoding="utf-8")
    assert text.startswith('{\n  "format": "mobcal-method",\n  "version": 1,\n'
                           '  "name": "Mine at 298.15 K",\n  "gas": "he",\n'
                           '  "parameters": "2000",\n  "generator": "ranlux",\n'
                           '  "temperature": 298.15,\n  "imp": 1000,\n  "itn": 5,\n')
    assert text.endswith('  "inor": 30\n}\n') and "\r" not in text
    assert list(json.loads(text)) == [k for k in methods.KEYS if k in json.loads(text)]
    # The batch the method makes is the batch the fields make, with the file's name recorded.
    by_file = from_cli(tmp_path, str(CHOLINE), "--method", str(mine))
    by_fields = from_cli(tmp_path, str(CHOLINE), "--method", "2000-he", "--temperature",
                         "298.15", "--imp", "1000", "--itn", "5")
    assert by_file.jobs() == by_fields.jobs()
    assert {j.method for j in by_file.jobs()} == {"Mine at 298.15 K"}
    assert by_file.jobs()[0].method_file == {"path": str(mine), "sha256": m.sha256}
    assert by_file.title() == "Mine at 298.15 K" and by_fields.method_now == "custom"
    # A field set over it is no longer the file's method.
    over = from_cli(tmp_path, str(CHOLINE), "--method", str(mine), "--imp", "25")
    assert over.method_now == "custom" and over.jobs()[0].method_file is None
    assert over.title() == "Custom (from Mine at 298.15 K)"


@pytest.mark.parametrize("key", list(methods.METHODS))
def test_save_writes_a_shipped_method_byte_for_byte(tmp_path, key):
    """The shipped files are in the form save writes: the same fields and description saved
    again are the same bytes, so one writer makes every method file."""
    m = methods.METHODS[key]
    again = methods.save(tmp_path / key, m.name, m.gas, m.parameters, m.generator, m.settings,
                         description=m.description)
    assert again.path == tmp_path / f"{key}.method.json"
    assert again.path.read_bytes() == methods.shipped_path(key).read_bytes()


@pytest.mark.parametrize("given, named", [("mine", "mine.method.json"),
                                          ("mine.json", "mine.method.json"),
                                          ("mine.method.json", "mine.method.json"),
                                          ("Mine.Method.JSON", "Mine.Method.JSON")])
def test_a_saved_method_file_is_named_name_method_json(tmp_path, given, named):
    m = methods.save(tmp_path / given, "Mine", "he", "2012", "philox", settings.DEFAULTS)
    assert m.path == tmp_path / named and m.path.is_file()
    assert methods.stem(m.path) == ("mine" if named.islower() else "Mine")


def test_a_method_file_names_its_own_table_by_path_and_sha256(tmp_path):
    (tmp_path / "tables").mkdir()
    table = own_table(tmp_path / "tables" / "mine_he.toml")
    f = tmp_path / "m.method.json"
    m = methods.save(f, "Mine", "he", table, "philox", settings.DEFAULTS)
    sha = run.hashlib.sha256(table.read_bytes()).hexdigest()
    assert m.table == table.resolve() and m.table_sha256 == sha and m.parameters is None
    assert json.loads(f.read_text("utf-8"))["parameters"] == {
        "path": table.resolve().as_posix(), "sha256": sha}
    jobs = Batch((CHOLINE,), tmp_path / "runs", method=str(f)).jobs()
    assert jobs[0].parameters == table.resolve() and jobs[0].method == "Mine"
    assert jobs[0].label == f"Choline-he-5013489-lj{sha[:8]}"
    # A relative path is the method file's folder's.
    rel = tmp_path / "rel.method.json"
    rel.write_text(body(name="Rel", parameters={"path": "tables/mine_he.toml", "sha256": sha}),
                   encoding="utf-8")
    assert methods.load(rel).table == table.resolve()
    # Changed: refused, saying which.
    table.write_bytes(table.read_bytes() + b"\n")
    with pytest.raises(methods.MethodError, match="mine_he.toml has changed since the method "
                                                  "was saved"):
        methods.load(f)
    with pytest.raises(BatchError, match="has changed"):
        Batch((CHOLINE,), tmp_path / "runs", method=str(f))
    # Moved: refused, saying which.
    table.rename(tmp_path / "elsewhere.toml")
    with pytest.raises(methods.MethodError, match="mine_he.toml is not there; it has moved"):
        methods.load(f)
    with pytest.raises(cli.UsageError, match="is not there"):
        from_cli(tmp_path, str(CHOLINE), "--method", str(f))


BASE = {"format": "mobcal-method", "version": 1, "name": "X", "gas": "he", "parameters": "2012",
        "generator": "philox"}


def body(drop: tuple[str, ...] = (), **fields) -> str:
    """A method file's text: ``BASE`` without ``drop``, with ``fields`` set or added."""
    return json.dumps({**{k: v for k, v in BASE.items() if k not in drop}, **fields}, indent=2)


# A method file the reader refuses, and the start of what it says; the schema refuses each too.
REFUSED = [
    (body(drop=("generator",)), "no generator"),
    (body(drop=("version",)), "no version; a method file begins"),
    (body(drop=("format",)), "no format; a method file begins"),
    (body(sead=1), "unknown key 'sead'"),
    (body(seed=0), "seed is 0; a seed is a positive integer up to 2147483647"),
    (body(seed=2147483648), "seed is 2147483648"),
    (body(seed="42"), "seed is '42'"),
    (body(seed=4.2), "seed is 4.2"),
    (body(seed=True), "seed is True"),
    (body(format=1), "format is 1; this reader reads 'mobcal-method'"),
    (body(format="mobcal-ion"), "format is 'mobcal-ion'"),
    (body(version=2), "version is 2; this version of MOBCAL reads version 1 of mobcal-method"),
    (body(version=True), "version is True"),
    (body(version="1"), "version is '1'"),
    (body(gas="ar"), "gas is 'ar'"),
    (body(gas=["he"]), r"gas is \['he'\]"),
    (body(gas="n2", parameters="2000"), "the shipped N2 tables are 2012"),
    (body(generator="rand"), "generator is 'rand'"),
    (body(name=""), "name must be 1 to 60"),
    (body(name="X "), "name must be 1 to 60"),
    (body(name="A\tB"), "name must be 1 to 60"),
    (body(name="x" * 61), "name must be 1 to 60"),
    (body(name=7), "name must be 1 to 60"),
    (body(description=42), "description must be a string, not 42"),
    (body(description=None), "description must be a string, not None"),
    (body(itn=0), "itn is 0"),
    (body(temperature=0), "temperature 0 is not a positive number"),
    (body(temperature="301"), "temperature must be a number"),
    (body().replace('"generator": "philox"', '"generator": "philox", "temperature": 1e400'),
     "temperature inf is not a positive number"),
    (body(imp=1.5), "imp must be an integer"),
    (body(inor=101), "inor is 101; 1 to 100"),
    (body(parameters={"path": "t.toml", "sha256": "A" * 64}), "64 lowercase hex digits"),
    (body(parameters={"path": "t.toml", "sha256": "a" * 64, "kind": 1}),
     "a table with path and sha256"),
    ("[]", "not a method file: the file must be one JSON object"),
]


@pytest.mark.parametrize("text, match", REFUSED)
def test_a_method_file_that_cannot_be_used_is_refused_by_key(tmp_path, text, match):
    f = tmp_path / "bad.method.json"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(methods.MethodError, match=match):
        methods.load(f)


def test_a_key_left_out_takes_the_2012_value(tmp_path):
    f = tmp_path / "short.method.json"
    f.write_text(body(name="Short", gas="n2", generator="ranlux", imp=500), encoding="utf-8")
    m = methods.load(f)
    assert m.settings.values() == {**settings.DEFAULTS.values(), "imp": 500}


@pytest.mark.parametrize("text, match", [
    (body().replace('"name": "X"', '"name": "X",\n  "name": "Y"'),
     "key 'name' appears twice in one object"),
    (body().replace('"generator": "philox"', '"generator": "philox", "temperature": NaN'),
     "NaN is not a JSON number"),
    (body().replace('"generator": "philox"', '"generator": "philox", "imp": Infinity'),
     "Infinity is not a JSON number"),
    (body()[:-2], "not JSON: "),
    ("﻿" + body(seed=3), None),  # a byte-order mark, as some editors write, is read
])
def test_a_method_file_is_read_as_strict_json(tmp_path, text, match):
    """As the ion file is read: a key twice in one object, or a constant JSON does not have,
    is refused by name rather than read one way."""
    f = tmp_path / "m.method.json"
    f.write_text(text, encoding="utf-8")
    if match is None:
        assert methods.load(f).seed == 3
        return
    with pytest.raises(methods.MethodError, match=match):
        methods.load(f)


TOML_METHOD = ('format = 1\nname = "Old"\ngas = "he"\nparameters = "2012"\n'
               'generator = "philox"\n')


def test_a_toml_method_file_is_refused_naming_the_json_form(tmp_path):
    """The TOML method files of 2.0 were converted to JSON when the format changed; a TOML
    method file is refused with a message that says what a method file is now."""
    f = tmp_path / "old.toml"
    f.write_text(TOML_METHOD, encoding="utf-8")
    want = "a TOML method file, which this version of MOBCAL does not read; a method file is " \
        "JSON, NAME.method.json"
    with pytest.raises(methods.MethodError, match=want):
        methods.load(f)
    with pytest.raises(methods.MethodError, match=want):
        methods.get(str(f))
    with pytest.raises(cli.UsageError, match=want):
        from_cli(tmp_path, str(CHOLINE), "--method", str(f))
    with pytest.raises(BatchError, match="a TOML method file"):
        Batch((CHOLINE,), tmp_path / "runs", method=str(f))
    # Gone is refused the same way, never read as a method's key.
    with pytest.raises(methods.MethodError, match="gone.toml: a TOML method file"):
        methods.get(str(tmp_path / "gone.toml"))
    with pytest.raises(methods.MethodError, match="gone.method.json: cannot read"):
        methods.get(str(tmp_path / "gone.method.json"))


def test_a_description_is_carried_and_is_not_part_of_the_method(tmp_path):
    assert all(m.description for m in methods.METHODS.values())
    plain = methods.save(tmp_path / "plain", "Plain", "he", "2012", "ranlux", settings.DEFAULTS)
    said = methods.save(tmp_path / "said", "Said", "he", "2012", "ranlux", settings.DEFAULTS,
                        description="The 2012 release in helium, saved with a note.")
    assert "description" not in json.loads(plain.path.read_text(encoding="utf-8"))
    assert said.description == "The 2012 release in helium, saved with a note."
    assert list(json.loads(said.path.read_text(encoding="utf-8")))[3] == "description"
    for m in (plain, said):  # both are the 2012 helium calculation
        assert m.matches("he", "2012", None, "ranlux", settings.DEFAULTS)
        assert methods.identify(m.gas, m.parameters, m.generator, m.settings) == "2012-he"
    a, b = (from_cli(tmp_path, str(CHOLINE), "--method", str(m.path)).jobs()[0]
            for m in (plain, said))
    assert a.label == b.label and staged(a, tmp_path / "a") == staged(b, tmp_path / "b")
    # A shipped method says what it is; verify says so of one that does not.
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    for key in methods.SHA256:
        (shipped / f"{key}.method.json").write_bytes(methods.shipped_path(key).read_bytes())
    f = shipped / "2012-he.method.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    del doc["description"]
    f.write_text(methods.dumps(doc), encoding="utf-8", newline="\n")
    assert "2012-he.method.json: carries no description; a shipped method says what it is" in \
        methods.verify(shipped)


# --- the schema ----------------------------------------------------------------------------

def schema() -> dict:
    return json.loads(methods.SCHEMA.read_text(encoding="utf-8"))


def validator() -> jsonschema.Draft202012Validator:
    s = schema()
    jsonschema.Draft202012Validator.check_schema(s)
    return jsonschema.Draft202012Validator(s)


def test_every_shipped_and_saved_method_is_valid_against_the_schema(tmp_path):
    v = validator()
    for key in methods.SHA256:
        v.validate(json.loads(methods.shipped_path(key).read_text(encoding="utf-8")))
    table = own_table(tmp_path / "mine_he.toml")
    st = settings.resolve(temperature=298.15, itn=5)
    for i, (t, seed, said) in enumerate([("2012", None, None), ("2000", 42, "A note."),
                                         (table, 7, None)]):
        m = methods.save(tmp_path / f"m{i}", f"Mine {i}", "he", t, "ranlux", st, seed=seed,
                         description=said)
        v.validate(json.loads(m.path.read_text(encoding="utf-8")))


def test_the_schema_holds_the_readers_keys_bounds_and_defaults():
    s, v = schema(), validator()
    p = s["properties"]
    assert tuple(p) == methods.KEYS and tuple(s["required"]) == methods.REQUIRED
    assert p["format"]["const"] == methods.FORMAT
    assert (p["version"]["const"],) == methods.VERSIONS and methods.VERSION in methods.VERSIONS
    assert p["name"]["maxLength"] == methods.MAX_NAME
    assert p["gas"]["enum"] == list(parameters.SETS)
    assert tuple(p["generator"]["enum"]) == GENERATORS
    names = {n for sets in parameters.SETS.values() for n in sets}
    assert set(p["parameters"]["oneOf"][0]["enum"]) == names
    for gas, sets in parameters.SETS.items():  # a shipped table is one the gas has
        for n in names:
            doc = {**BASE, "gas": gas, "parameters": n}
            assert v.is_valid(doc) == (n in sets), (gas, n)
    for k, (lo, hi) in settings.BOUNDS.items():
        assert (p[k]["minimum"], p[k]["maximum"]) == (lo, hi), k
    assert p["temperature"]["exclusiveMaximum"] == settings.MAX_TEMPERATURE
    assert p["seed"]["maximum"] == MAX_SEED
    for k in settings.NAMES:  # the default each description states
        said = re.search(r"(\d+) when left out", p[k]["description"]).group(1)
        assert int(said) == getattr(settings.DEFAULTS, k), k
    assert f"{methods.DEFAULT_SEED}, the 2012 seed" in p["seed"]["description"]


@pytest.mark.parametrize("text, match", REFUSED)
def test_the_schema_refuses_what_the_reader_refuses(text, match):
    assert not validator().is_valid(json.loads(text))


@pytest.mark.parametrize("text, match", [
    (body(itn=100, inp=100), "at most 9999999 points"),
    (body(name="A​B"), "name must be 1 to 60 printable"),
    (body(parameters={"path": "gone.toml", "sha256": "a" * 64}), "gone.toml is not there"),
    (body(imp=1000.0), "imp must be an integer, not 1000.0"),
    (body(seed=42.0), "seed is 42.0"),
    (body(version=1.0), "version is 1.0"),
    (body().replace('"name": "X"', '"name": "X",\n  "name": "Y"'), "appears twice"),
])
def test_what_only_the_reader_refuses(tmp_path, text, match):
    """The rules the schema's description lists as the reader's: a document the schema accepts
    and ``load`` refuses."""
    assert validator().is_valid(json.loads(text))
    f = tmp_path / "bad.method.json"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(methods.MethodError, match=match):
        methods.load(f)


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


def test_a_method_seed_is_the_first_seed_and_seeds_wins(tmp_path):
    """A method's seed is where its runs start without --seeds; --seeds wins when given, and
    the run is still a run of the method, which the seed does not identify."""
    assert all(m.seed is None and m.first_seed == batch.DEFAULT_SEED
               for m in methods.METHODS.values())
    plain = methods.save(tmp_path / "plain", "Plain", "he", "2012", "ranlux",
                         settings.DEFAULTS)
    assert "seed" not in plain.path.read_text(encoding="utf-8") and plain.seed is None
    m = methods.save(tmp_path / "m", "Seeded", "he", "2012", "ranlux", settings.DEFAULTS,
                     seed=42)
    assert m.path.read_text(encoding="utf-8").endswith('  "inor": 30,\n  "seed": 42\n}\n')
    assert (m.seed, m.first_seed) == (42, 42) and methods.load(m.path).seed == 42
    by_method = from_cli(tmp_path, str(CHOLINE), "--method", str(m.path))
    assert [j.seed for j in by_method.jobs()] == [42]
    assert {j.method for j in by_method.jobs()} == {"Seeded"}
    given = from_cli(tmp_path, str(CHOLINE), "--method", str(m.path), "--seeds", "7,8")
    assert [j.seed for j in given.jobs()] == [7, 8]
    assert {j.method for j in given.jobs()} == {"Seeded"}
    assert [j.seed for j in from_cli(tmp_path, str(CHOLINE)).jobs()] == [batch.DEFAULT_SEED]
    # Shipped methods carry none; verify says so of one that does.
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    for key in methods.SHA256:
        (shipped / f"{key}.method.json").write_bytes(methods.shipped_path(key).read_bytes())
    f = shipped / "2012-he.method.json"
    f.write_text(methods.dumps({**json.loads(f.read_text(encoding="utf-8")), "seed": 42}),
                 encoding="utf-8", newline="\n")
    assert "2012-he.method.json: carries a seed; a shipped method carries none" in \
        methods.verify(shipped)


def test_a_batch_refuses_a_seed_the_program_cannot_take(tmp_path):
    with pytest.raises(BatchError, match="seed 0: a seed is a positive integer"):
        Batch((CHOLINE,), tmp_path / "runs", seeds=(0,))
    with pytest.raises(cli.UsageError, match="seed 2147483648"):
        from_cli(tmp_path, str(CHOLINE), "--seeds", "2147483648")


def test_a_run_from_a_method_file_records_its_name_and_sha256(tmp_path):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    m = methods.save(tmp_path / "m.method.json", "My method", "n2", "2012", "philox",
                     settings.resolve(itn=2))
    b = Batch((inp,), tmp_path / "runs", method=m.ref, seeds=(1,), split=None)
    s = run_many(b.jobs(), 1, launcher=launcher)
    _, json_path = s.write(tmp_path / "runs")
    rec = json.loads((b.jobs()[0].run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["method"] == "My method" and rec["binary"]["gas"] == "n2"
    assert rec["method_file"] == {"path": str(tmp_path / "m.method.json"),
                                  "sha256": m.sha256}
    assert json.loads(json_path.read_text(encoding="utf-8"))["runs"][0]["method_file"] == \
        rec["method_file"]
    para = methods.text(methods.read_records([tmp_path / "runs"]))
    assert "The nitrogen calculations used the method My method: the MOBCAL 2012 nitrogen" in para


def test_a_record_holds_every_field_of_its_method(tmp_path):
    """The record needs no method file to say what the method was: the gas, the generator, the
    seed, the table by path and SHA-256 and the six settings are each in it, so a method file
    that moves, changes or goes leaves its runs described."""
    inp = write_input(tmp_path / "ok.mfj", "ok")
    table = own_table(tmp_path / "mine_he.toml")
    m = methods.save(tmp_path / "m.method.json", "Mine", "he", table, "ranlux",
                     settings.resolve(temperature=298.15, itn=2), seed=42)
    b = Batch((inp,), tmp_path / "runs", method=m.ref, split=None)
    run_many(b.jobs(), 1, launcher=launcher)
    rec = json.loads((b.jobs()[0].run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["binary"]["gas"] == m.gas
    assert (rec["mobcal_in"]["generator"], rec["mobcal_in"]["seed"]) == (m.generator, m.seed)
    assert (rec["parameters"]["path"], rec["parameters"]["sha256"]) == \
        (str(m.table), m.table_sha256)
    assert {k: rec["settings"][k] for k in settings.NAMES} == m.settings.values()


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
               settings=settings.resolve(imp=25), split=4, workers=2)
    b2 = Batch((CHOLINE,), tmp_path / "runs", method="2000-he", parameters=None, split="auto")
    m = methods.save(tmp_path / "m.method.json", "Mine", "he", "2012", "ranlux",
                     settings.DEFAULTS)
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
    st = settings.resolve(imp=1)
    for mode in estimate.MODES:
        lean = estimate.allocate([Job(CHOLINE, "he", 1, tmp_path, settings=st)], cpus=80,
                                 mode=mode)
        assert lean.jobs[0].split is None
    # A split never exceeds what its costliest block lets it use, which is never more than
    # the blocks there are to deal: 5 blocks, the slowest twice the mean in helium, so 3.
    st = settings.resolve(itn=1, inp=5, imp=100_000)
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
    st = settings.resolve(itn=1)
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


QM = Path(__file__).resolve().parent / "data" / "qm"


def import_ion(path: Path, source: Path, charges: str) -> Path:
    """An ion file imported from a quantum chemistry output, labelled for the stand-in."""
    from mobcal.io import structure
    return structure.convert(structure.read(source), charges, label="ok").ion.write(path)


@pytest.mark.parametrize("inp, said", [
    ({"charge_mode": "calc", "import": {"source": {"program": "ORCA", "version": "6.1.1",
                                                   "keywords": ["B3LYP", "def2-TZVP", "CHELPG"]},
                                        "charges": {"choice": "chelpg"}}},
     "the CHELPG charges from ORCA 6.1.1 (keywords B3LYP def2-TZVP CHELPG)"),
    ({"charge_mode": "calc", "import": {"source": {"program": "Gaussian", "version": "16",
                                                   "route": "#p B3LYP/6-31G(d) Pop=MK"},
                                        "charges": {"choice": "mk"}}},
     "the Merz-Kollman charges from Gaussian 16 (route #p B3LYP/6-31G(d) Pop=MK)"),
    ({"charge_mode": "calc", "import": {"source": {"program": "ORCA", "version": None},
                                        "charges": {"choice": "lowdin"}}},
     "the Löwdin charges from ORCA"),
    ({"charge_mode": "calc", "import": {"source": {"program": "ORCA", "version": "6.1.1"},
                                        "charges": {"choice": "uniform"}}},
     "the net charge divided equally among the atoms"),
    ({"charge_mode": "calc", "import": {"source": {"program": "xyz", "version": None},
                                        "charges": {"choice": "column"}}},
     "those given in the .xyz input"),
    ({"charge_mode": "calc", "import": {"source": {"program": "MobCal-MPI", "version": None},
                                        "charges": {"choice": "column"}}},
     "those given in the MobCal-MPI .mfj input"),
    ({"charge_mode": "equal", "import": {"source": {"program": "mfj", "version": None},
                                         "charges": {"choice": "column"}}},
     "+1 e divided equally among the atoms"),
    ({"charge_mode": "none", "import": {"source": {"program": "mfj", "version": None},
                                        "charges": {"choice": "column"}}},
     "not assigned"),
    ({"charge_mode": "calc"}, None),  # an ion file with no import record
    ({"path": "a.mfj", "sha256": "0" * 64}, None),  # a .mfj input
])
def test_what_a_record_says_the_charges_were(inp, said):
    assert methods.charges(inp) == said


def test_the_methods_text_names_the_charges_when_every_run_records_them(tmp_path):
    orca = import_ion(tmp_path / "orca.ion.json", QM / "orca" / "choline_sp" / "choline_sp.out",
                      "chelpg")
    gaussian = import_ion(tmp_path / "g.ion.json",
                          QM / "gaussian" / "choline_2012_mk" / "choline_2012_mk.log", "mk")
    out = tmp_path / "runs"
    run_many([Job(orca, "he", s, out) for s in (1, 2)], 2, launcher=launcher).write(out)
    rec = methods.read_records([out])
    assert rec[0]["input"]["charge_mode"] == "calc"
    assert rec[0]["input"]["import"] == {
        "source": {"program": "ORCA", "version": "6.1.1",
                   "keywords": ["B3LYP", "D3BJ", "def2-TZVP", "CHELPG", "Hirshfeld"]},
        "charges": {"choice": "chelpg"}}
    para = methods.text(rec).split("\n\n")[0]
    assert ("The partial charges on the atoms were the CHELPG charges from ORCA 6.1.1 (keywords "
            "B3LYP D3BJ def2-TZVP CHELPG Hirshfeld). The helium calculations used") in para

    run_many([Job(gaussian, "he", 1, out)], 1, launcher=launcher).write(out)
    para = methods.text(methods.read_records([out])).split("\n\n")[0]
    assert ("The partial charges on the atoms were the Merz-Kollman charges from Gaussian 16 "
            "Rev. B.01 (route # B3LYP/6-31++G(d,p) SP NoSymm Pop=(MK,Hirshfeld)) for 1 ion "
            "file and the CHELPG charges from ORCA 6.1.1 (keywords B3LYP D3BJ def2-TZVP CHELPG "
            "Hirshfeld) for 1 ion file.") in para  # in the records' order, by run name

    # one run whose record cannot say, and the paragraph says nothing of charges
    run_many([Job(write_input(tmp_path / "a.mfj", "ok"), "he", 1, out)], 1,
             launcher=launcher).write(out)
    assert "partial charges" not in methods.text(methods.read_records([out]))


# --- the result file's ion: embedded or named, from the command line and the queue file ---------

def test_result_ion_travels_from_the_command_line_and_the_queue_file(tmp_path):
    default = from_cli(tmp_path, str(CHOLINE))
    ref = from_cli(tmp_path, str(CHOLINE), "--result-ion", "reference")
    assert default.result_ion == "embed" and ref.result_ion == "reference"
    assert {j.result_ion for j in ref.jobs()} == {"reference"}
    assert {j.result_ion for j in default.jobs()} == {"embed"}
    assert ref.jobs() == default.jobs()  # not a field of the calculation
    path = batch.save([ref, default], tmp_path / "queue.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert [b["result_ion"] for b in doc["batches"]] == ["reference", "embed"]
    assert batch.load(path) == ([ref, default], [])
    del doc["batches"][0]["result_ion"]  # a queue file written before the key: embed
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert batch.load(path)[0][0].result_ion == "embed"
    with pytest.raises(BatchError, match="result_ion"):
        Batch((CHOLINE,), tmp_path, result_ion="maybe")
    with pytest.raises(SystemExit):
        from_cli(tmp_path, str(CHOLINE), "--result-ion", "maybe")
