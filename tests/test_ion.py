"""mobcal.io.ion: the ion file, ``docs/ion-file.md``.

Every ``.mfj`` the repository ships or keeps as a fixture converts to an ion file and back to the
same input for every table that holds its elements; a ``.mfj`` that ``Mfj.text`` wrote comes back
byte for byte; the stored choline pair under ``tests/data/ion/`` pins both writers. Each refusal
the page lists is shown once, and the schema is checked to refuse the structural ones too.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import random
from pathlib import Path

import jsonschema
import pytest

from mobcal import cli, fortran, parameters
from mobcal.io import ion, structure
from mobcal.io.ion import Ion, IonError
from mobcal.io.mfj import MAX_ATOMS, MAX_SETS, Atom, Mfj

TESTS = Path(__file__).resolve().parent
DATA = TESTS / "data" / "ion"
CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"
MFJ_FIXTURES = [CHOLINE, *sorted((TESTS / "elements").glob("*.mfj"))]
TABLES = [parameters.shipped(g, n) for g in ("he", "n2") for n in parameters.names(g)]
QM = TESTS / "data" / "qm"


def holds(table: parameters.ParameterSet, m: Mfj) -> bool:
    return set(m.keys) <= set(table.keys)


@pytest.mark.parametrize("path", MFJ_FIXTURES, ids=lambda p: p.name)
def test_every_fixture_mfj_round_trips(path):
    original = Mfj.read(path)
    i = ion.from_mfj(path)
    assert Ion.parse(i.text()) == i
    tables = [t for t in TABLES if holds(t, original)]
    assert tables
    for t in tables:
        assert i.mfj(t) == original, t.name
    assert i.import_record["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_shipped_tables_name_every_key_alike():
    names = ion.key_symbols()
    assert names == {1: "H", 12: "C", 14: "N", 16: "O", 19: "F", 23: "Na", 28: "Si", 31: "P",
                     32: "S", 56: "Fe"}
    for t in TABLES:
        assert all(names[e.key] == e.symbol for e in t.elements)


def test_the_choline_reference_pins_both_writers():
    stored = (DATA / "choline.ion.json").read_text(encoding="utf-8")
    i = Ion.parse(stored)
    assert i.text() == stored
    mfj_bytes = (DATA / "choline.mfj").read_bytes()
    for gas in ("he", "n2"):
        assert i.mfj(parameters.shipped(gas)).text().encode("latin-1") == mfj_bytes
    assert Mfj.parse(mfj_bytes.decode("latin-1")) == Mfj.read(CHOLINE)
    fresh = ion.from_mfj(CHOLINE)
    for k in ("label", "molecular_charge", "units", "correction_factor", "charge_mode",
              "symbols", "conformers", "columns"):
        assert getattr(fresh, k) == getattr(i, k), k
    assert fresh.import_record["source"]["sha256"] == i.import_record["source"]["sha256"]
    assert i.molecular_charge == 1 and i.import_record["charges"]["net_charge_from"] == "charges"


def written_mfjs() -> list[Mfj]:
    rng = random.Random(48)

    def atom(key, charge=True):
        return Atom(rng.uniform(-20, 20), rng.uniform(-20, 20), rng.gauss(0, 1e-3), key,
                    rng.uniform(-1, 1) if charge else None)

    keys = [1, 12, 14, 16, 19, 23, 28, 32, 56]
    calc = Mfj(" leading blank", "ang", "calc", 1.0,
               tuple(tuple(atom(k) for k in keys) for _ in range(3)))
    equal = Mfj("equal four fields", "au", "equal", 0.987654321,
                (tuple(atom(k, charge=False) for k in keys),
                 tuple(atom(k, charge=bool(j % 2)) for j, k in enumerate(keys))))
    permuted = Mfj("permuted", "ang", "none", 1.0,
                   (tuple(atom(k) for k in keys), tuple(atom(k) for k in reversed(keys))))
    return [calc, equal, permuted]


@pytest.mark.parametrize("m", written_mfjs(), ids=lambda m: m.label.strip())
def test_a_file_mfj_text_wrote_comes_back_byte_for_byte(tmp_path, m):
    path = m.write(tmp_path / "x.mfj")
    i = Ion.parse(ion.from_mfj(path).text())
    table = parameters.shipped("he")
    assert i.mfj(table).text().encode("latin-1") == path.read_bytes()


def test_a_permuted_set_keeps_its_own_symbols_and_null_charges_stay_null():
    calc, equal, permuted = written_mfjs()
    p = ion.from_mfj(permuted)
    assert p.conformers[0].symbols is None and p.conformers[1].symbols == p.symbols[::-1]
    e = ion.from_mfj(equal)
    assert e.conformers[0].charges is None and None in e.conformers[1].charges
    assert e.molecular_charge is None and "charges" in e.columns
    assert e.units == "bohr" and e.correction_factor == 0.987654321
    assert ion.from_mfj(calc).label == " leading blank"
    assert e.import_record is None  # an Mfj object has no source to record


@pytest.mark.parametrize("source,choice", [
    (QM / "orca" / "choline_sp" / "choline_sp.out", "chelpg"),
    (QM / "gaussian" / "choline_2012_mk" / "choline_2012_mk.log", "mk"),
])
def test_an_imported_mfj_comes_back_byte_for_byte(tmp_path, source, choice):
    out = structure.convert(structure.read(source), choice).mfj.write(tmp_path / "imp.mfj")
    i = ion.from_mfj(out)
    assert i.molecular_charge == 1
    for gas in ("he", "n2"):
        assert i.mfj(parameters.shipped(gas)).text().encode("latin-1") == out.read_bytes()


def test_the_tolerance_is_the_imports():
    assert ion.TOLERANCE == structure.TOLERANCE


def test_z_is_null_when_the_sets_disagree_or_a_charge_is_missing():
    a = (Atom(0, 0, 0, 14, 0.6), Atom(1, 0, 0, 1, 0.4))
    b = (Atom(0, 0, 0, 14, 1.6), Atom(1, 0, 0, 1, 0.4))
    assert ion.from_mfj(Mfj("x", "ang", "calc", 1.0, (a, a))).molecular_charge == 1
    assert ion.from_mfj(Mfj("x", "ang", "calc", 1.0, (a, b))).molecular_charge is None
    c = (Atom(0, 0, 0, 14, 0.6), Atom(1, 0, 0, 1, None))
    assert ion.from_mfj(Mfj("x", "ang", "none", 1.0, (c,))).molecular_charge is None


# --- writing the .mfj: the two refusals ------------------------------------------------------

def fluoride() -> Ion:
    return ion.from_mfj(Mfj("fluoride", "ang", "calc", 1.0,
                            ((Atom(0, 0, 0, 19, -0.5), Atom(1.4, 0, 0, 1, -0.5)),)))


def test_an_element_the_table_lacks_is_refused_naming_it_and_the_table():
    i = fluoride()
    with pytest.raises(IonError, match=r"F \(1 atom\) not in the element table 'MOBCAL 2000 "
                                       r"helium' \(mobcal_He_2000.toml\)"):
        i.mfj(parameters.shipped("he", "2000"))
    assert i.mfj(parameters.shipped("he")).keys == (1, 19)


def test_nitrogen_refuses_a_first_conformer_without_every_charge():
    m = Mfj("none", "ang", "none", 1.0, ((Atom(0, 0, 0, 12, None), Atom(1, 0, 0, 1, None)),))
    i = ion.from_mfj(m)
    assert i.mfj(parameters.shipped("he")) == m
    with pytest.raises(IonError, match="2 atom.*conformers\\[0\\].*nitrogen"):
        i.mfj(parameters.shipped("n2"))


# --- what a reader refuses -------------------------------------------------------------------

def base() -> dict:
    return json.loads((DATA / "choline.ion.json").read_text(encoding="utf-8"))


def edit(fn):
    d = base()
    fn(d)
    return d


def setter(path: str, value):
    def fn(d):
        *head, last = path.split(".")
        for k in head:
            d = d[int(k)] if isinstance(d, list) else d[k]
        if isinstance(d, list):
            d[int(last)] = value
        else:
            d[last] = value
    return fn


def drop(key: str):
    return lambda d: d.pop(key)


def with_columns(d):
    n = len(d["symbols"])
    d["masses"] = [1.0] * n
    d["columns"]["masses"] = {"unit": "u", "source": "test"}


# (id, edit, message, the schema refuses it too)
REFUSALS = [
    ("format", setter("format", "mobcal-ions"), r"^format: 'mobcal-ions'", True),
    ("version 2", setter("version", 2), r"^version: 2; this version", True),
    ("version true", setter("version", True), r"^version: True", True),
    ("unknown key", setter("weights", [1.0]), r"^weights: not a field", True),
    ("unknown conformer key", setter("conformers.0.weight", 1.0),
     r"^conformers\[0\]\.weight: not a field", True),
    ("unknown import key", setter("import.charges.scheme", "x"),
     r"^import\.charges\.scheme: not a field", True),
    ("unknown column", setter("columns.spin", {"unit": "1", "source": "x"}),
     r"^columns\.spin: not a field", True),
    ("missing required", drop("units"), r"^units: missing", True),
    ("missing written_by", drop("written_by"), r"^written_by: missing", True),
    ("wrong type", setter("correction_factor", "1.0"), r"^correction_factor: must be a number",
     True),
    ("bool as number", setter("correction_factor", True), r"must be a number, not true", True),
    ("z not integer", setter("molecular_charge", 1.5), r"^molecular_charge: must be an integer",
     True),
    ("label too long", setter("label", "x" * 31), r"^label: 31 characters", True),
    ("label line break", setter("label", "a\x0cb"), r"^label: holds a line break", True),
    ("label not latin-1", setter("label", "Ω"), r"^label: holds a character outside", True),
    ("label trailing blank", setter("label", "choline "), r"^label: ends in a blank", True),
    ("symbol case", setter("symbols.0", "CL"), r"^symbols\[0\]: 'CL' is not", True),
    ("symbol lower", setter("symbols.0", "n"), r"^symbols\[0\]: 'n' is not", True),
    ("units", setter("units", "ang"), r"^units: 'ang'", True),
    ("charge mode", setter("charge_mode", "CALC"), r"^charge_mode: 'CALC'", True),
    ("no conformers", setter("conformers", []), r"^conformers: 0 conformers", True),
    ("too many conformers", lambda d: d.update(conformers=d["conformers"] * (MAX_SETS + 1)),
     r"^conformers: 101 conformers", True),
    ("no atoms", lambda d: d.update(symbols=[]), r"^symbols: 0 atoms", True),
    ("geometry length", lambda d: d["conformers"][0]["geometry"].pop(),
     r"^conformers\[0\]\.geometry: 20 entries for 21 atoms", False),
    ("charges length", lambda d: d["conformers"][0]["charges"].pop(),
     r"^conformers\[0\]\.charges: 20 entries for 21 atoms", False),
    ("conformer symbols length", setter("conformers.0.symbols", ["H"]),
     r"^conformers\[0\]\.symbols: 1 entries for 21 atoms", False),
    ("column length", lambda d: (with_columns(d), d["masses"].pop()),
     r"^masses: 20 entries for 21 atoms", False),
    ("two coordinates", setter("conformers.0.geometry.3", [0.0, 1.0]),
     r"^conformers\[0\]\.geometry\[3\]: 2 coordinates", True),
    ("column undeclared", lambda d: d["columns"].pop("charges"),
     r"^charges: present without a declaration", False),
    ("column absent", lambda d: (with_columns(d), d.pop("masses")),
     r"^columns\.masses: declared, and the file carries no masses", False),
    ("column unit", setter("columns.charges.unit", "C"), r"^columns\.charges\.unit: 'C'", True),
    ("column source empty", setter("columns.charges.source", ""),
     r"^columns\.charges\.source: empty", True),
    ("calc without charges",
     lambda d: d["conformers"].append({"geometry": d["conformers"][0]["geometry"]}),
     r"^conformers\[1\]\.charges: missing; calc mode", False),
    ("calc null charge", setter("conformers.0.charges.4", None),
     r"^conformers\[0\]\.charges\[4\]: null; calc mode", False),
    ("charge sum", setter("molecular_charge", 2),
     r"^conformers\[0\]\.charges: sum to \+0\.999998, -1\.00e\+00 e from molecular_charge \+2",
     False),
    ("own symbols beside a column",
     lambda d: (with_columns(d), d["conformers"][0].update(symbols=list(d["symbols"]))),
     r"^conformers\[0\]\.symbols: a conformer with its own atom order makes masses", False),
    ("bond atom", setter("connectivity", [[0, 21, 1]]), r"^connectivity\[0\]: names atom 21",
     False),
    ("bond order of atoms", setter("connectivity", [[2, 1, 1]]),
     r"^connectivity\[0\]: \[2, 1\]: the lower atom comes first", False),
    ("commit", setter("written_by.commit", "d1306d7"), r"^written_by\.commit: 'd1306d7'", True),
    ("written", setter("written", "yesterday"), r"^written: 'yesterday'", None),
    ("sha256", setter("import.source.sha256", "ABC"), r"^import\.source\.sha256", True),
]


@pytest.mark.parametrize("fn,message,schema", [r[1:] for r in REFUSALS],
                         ids=[r[0] for r in REFUSALS])
def test_the_reader_refuses(fn, message, schema):
    d = edit(fn)
    if "connectivity" in d:
        d["columns"]["connectivity"] = {"unit": "1", "source": "test"}
    with pytest.raises(IonError, match=message):
        Ion.from_dict(d)
    if schema:
        assert not validator().is_valid(d)


def test_source_keys_are_kept_not_refused():
    d = edit(setter("import.source.route", "#P B3LYP"))
    assert Ion.from_dict(d).import_record["source"]["route"] == "#P B3LYP"
    assert validator().is_valid(d)


def test_nan_infinity_duplicates_and_non_json_are_refused():
    text = (DATA / "choline.ion.json").read_text(encoding="utf-8")
    with pytest.raises(IonError, match="NaN is not a JSON number"):
        Ion.parse(text.replace('"correction_factor": 1.0', '"correction_factor": NaN'))
    with pytest.raises(IonError, match="not a finite double"):
        Ion.parse(text.replace('"correction_factor": 1.0', '"correction_factor": 1e999'))
    with pytest.raises(IonError, match="'units' appears twice"):
        Ion.parse(text.replace('"units": "angstrom",', '"units": "angstrom", "units": "bohr",'))
    with pytest.raises(IonError, match="not JSON"):
        Ion.parse(text[:-3])


def test_a_file_name_is_given_with_a_refusal(tmp_path):
    p = tmp_path / "bad.ion.json"
    p.write_text(json.dumps(edit(setter("version", 2))), encoding="utf-8")
    with pytest.raises(IonError, match=r"^bad\.ion\.json: version: 2"):
        Ion.read(p)


def test_optional_columns_and_bonds_are_read_and_written_back():
    d = base()
    n = len(d["symbols"])
    for name, unit, value in (("masses", "u", 1.008), ("mmff94_types", "1", 5),
                              ("mmff94_alpha", "angstrom^3", 0.25), ("mmff94_n", "1", 0.8),
                              ("mmff94_a", "1", 4.2), ("mmff94_g", "1", 1.2)):
        d[name] = [value] * n
        d["columns"][name] = {"unit": unit, "source": "test"}
    d["connectivity"] = [[0, 1, 1], [0, 2, 1.5]]
    d["columns"]["connectivity"] = {"unit": "1", "source": "test"}
    d["comment"] = "a comment"
    i = Ion.from_dict(d)
    assert i.per_atom["mmff94_types"] == (5,) * n and i.connectivity[1] == (0, 2, 1.5)
    assert Ion.parse(i.text()) == i
    assert validator().is_valid(json.loads(i.text()))
    # masses never set a key
    assert i.mfj(parameters.shipped("he")) == Mfj.read(CHOLINE)


def test_written_by_carries_a_null_commit_where_none_is_known(monkeypatch):
    monkeypatch.setattr(fortran, "_commit", lambda *a: "")
    assert ion.written_by()["commit"] is None
    i = ion.from_mfj(CHOLINE)
    assert Ion.parse(i.text()).written_by["commit"] is None


def test_the_bound_is_the_programs():
    assert ion.MAX_ATOMS == MAX_ATOMS


def test_write_refuses_to_replace_a_file(tmp_path):
    i = ion.from_mfj(CHOLINE)
    p = i.write(tmp_path / "c.ion.json")
    with pytest.raises(IonError, match="exists"):
        i.write(p)
    assert i.write(p, overwrite=True) == p
    assert p.read_bytes().count(b"\r") == 0


# --- the schema ------------------------------------------------------------------------------

def validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(ion.SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)


def test_the_stored_example_and_a_conversion_are_valid():
    v = validator()
    v.validate(base())
    for path in MFJ_FIXTURES:
        v.validate(json.loads(ion.from_mfj(path).text()))
    for m in written_mfjs():
        v.validate(json.loads(ion.from_mfj(m).text()))


def test_the_page_example_matches_the_stored_file():
    page = (TESTS.parent / "docs" / "ion-file.md").read_text(encoding="utf-8")
    d = base()
    for k in ("label", "molecular_charge", "units", "charge_mode"):
        assert f'"{k}": {json.dumps(d[k])}' in page, k
    assert copy.deepcopy(d)["import"]["source"]["sha256"][:8] in page


# --- mobcal export ---------------------------------------------------------------------------

def test_export_writes_the_mfj_a_run_stages_beside_the_ion_file(tmp_path, capsys):
    src = tmp_path / "choline.ion.json"
    src.write_bytes((DATA / "choline.ion.json").read_bytes())
    assert cli.main(["export", str(src)]) == 0
    out = tmp_path / "choline.mfj"
    assert ("21 atoms, 1 conformer, keys of the 'MOBCAL 2012 helium' and 'MOBCAL 2012 "
            "nitrogen' tables") in capsys.readouterr().out
    assert out.read_bytes() == (DATA / "choline.mfj").read_bytes()
    assert Mfj.read(out) == Mfj.read(CHOLINE)
    assert cli.main(["export", str(src)]) == 2
    assert "exists; not replacing it" in capsys.readouterr().err
    assert cli.main(["export", str(src), "--force", "--gas", "he", "--parameters", "2000",
                     "-o", str(tmp_path / "c2000.mfj")]) == 0
    assert "keys of the 'MOBCAL 2000 helium' table" in capsys.readouterr().out
    assert (tmp_path / "c2000.mfj").read_bytes() == out.read_bytes()


def test_export_refuses_an_element_a_table_lacks_and_a_bad_file(tmp_path, capsys):
    i = Ion.read(DATA / "choline.ion.json")
    p = dataclasses.replace(i, symbols=("P", *i.symbols[1:]))
    src = p.write(tmp_path / "p.ion.json")
    assert cli.main(["export", str(src)]) == 2
    assert "P (1 atom) not in the element table" in capsys.readouterr().err
    assert cli.main(["export", str(src), "--gas", "n2"]) == 0
    assert Mfj.read(tmp_path / "p.mfj").sets[0][0].key == 31
    bad = tmp_path / "bad.ion.json"
    bad.write_text('{"format": "mobcal-ion", "version": 2}', encoding="utf-8")
    assert cli.main(["export", str(bad)]) == 2
    assert "bad.ion.json: version: 2" in capsys.readouterr().err
    assert not (tmp_path / "bad.mfj").exists()
