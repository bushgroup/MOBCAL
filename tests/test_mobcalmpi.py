"""MobCal-MPI's nine-column ``.mfj`` as an import source (``mobcal.io.mobcalmpi``), and
``mobcal import X.mfj`` for both layouts.

The fixture, ``tests/data/ion/choline_mobcalmpi.mfj``, is the 2012 choline input in MobCal-MPI
2.1's layout with its coordinates, charges and masses the 2012 file's, so the ion file read
from it must stage the same ``.mfj`` as ``fortran/Choline.mfj``, in either gas.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from mobcal import cli, fortran, parameters
from mobcal.io import ion, mobcalmpi, structure
from mobcal.io.ion import Ion, IonError
from mobcal.io.mfj import Mfj
from mobcal.io.mobcalmpi import MobcalMpiError, MobcalMpiMfj

TESTS = Path(__file__).resolve().parent
DATA = TESTS / "data" / "ion"
NINE = DATA / "choline_mobcalmpi.mfj"
CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"
TWELVE = [CHOLINE, DATA / "choline.mfj", *sorted((TESTS / "elements").glob("*.mfj"))]


def lines() -> list[str]:
    return NINE.read_text(encoding="latin-1").splitlines()


def text(ls: list[str]) -> str:
    return "\n".join(ls) + "\n"


def test_the_layout_is_told_from_the_2012_one():
    assert mobcalmpi.detect(NINE.read_text(encoding="latin-1"))
    for path in TWELVE:
        assert not mobcalmpi.detect(path.read_text(encoding="latin-1")), path.name


@pytest.mark.parametrize("gas", ["he", "n2"])
def test_the_choline_fixture_stages_the_2012_choline_input(gas):
    i = ion.from_mfj(NINE)
    assert i.mfj(parameters.shipped(gas)) == Mfj.read(CHOLINE)
    assert Ion.parse(i.text()) == i


def test_masses_and_the_mmff94_parameters_are_kept_as_declared_columns():
    i = ion.from_mfj(NINE)
    rows = [ln.split() for ln in lines()[7:]]
    assert i.symbols == tuple(ion.key_symbols()[a.key] for a in Mfj.read(CHOLINE).sets[0])
    assert i.per_atom["masses"] == tuple(float(r[3]) for r in rows)
    for col, n in (("mmff94_alpha", 5), ("mmff94_n", 6), ("mmff94_a", 7), ("mmff94_g", 8)):
        assert i.per_atom[col] == tuple(float(r[n]) for r in rows), col
        assert i.columns[col] == {"unit": ion.COLUMNS[col],
                                  "source": f"{NINE.name}, column {n + 1} (MobCal-MPI layout)"}
    assert "mmff94_types" not in i.columns  # the file does not name them
    assert i.conformers[0].charges == tuple(float(r[4]) for r in rows)
    assert i.molecular_charge == 1 and i.correction_factor == 1.0


def test_line_6_and_the_run_line_are_kept_in_the_source_record():
    s = ion.from_mfj(NINE).import_record["source"]
    assert s["program"] == "MobCal-MPI" and s["version"] is None
    assert s["line_6"] == "0" and s["run_line"] == "10 40 1000 2 5013489 301.0"
    assert s["path"] == str(NINE.resolve())


def test_the_ion_file_is_valid_against_the_schema():
    schema = json.loads(ion.SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(json.loads(ion.from_mfj(NINE).text()))


def test_monoisotopic_masses_name_the_same_elements():
    ls = lines()
    mono = {"14.01": "14.003", "12.01": "12.000", "16.00": "15.995"}  # MobCal-MPI's mass.prm
    for k, row in enumerate(ls[7:], 7):
        f = row.split()
        f[3] = mono.get(f[3], f[3])
        ls[k] = " ".join(f)
    m = MobcalMpiMfj.parse(text(ls))
    assert m.symbols() == ion.from_mfj(NINE).symbols


def test_a_mass_of_no_element_or_of_two_is_refused(monkeypatch):
    ls = lines()
    f = ls[7].split()
    f[3] = "35.453"  # chlorine, which no shipped table holds
    ls[7] = " ".join(f)
    with pytest.raises(MobcalMpiError, match=r"atom 1: mass 35.453 u is within 0.25 u of no "
                                             r"element of the shipped tables, which hold H "):
        MobcalMpiMfj.parse(text(ls)).symbols()
    monkeypatch.setattr(mobcalmpi, "element_masses", lambda: {"N": 14.01, "X": 14.2})
    with pytest.raises(MobcalMpiError, match="atom 1: mass 14.01 u is within 0.25 u of N and X"):
        MobcalMpiMfj.parse(NINE.read_text(encoding="latin-1")).symbols()


def _write(ls: list[str], d: Path) -> Path:
    p = d / "x.mfj"
    p.write_text(text(ls), encoding="latin-1", newline="\n")
    return p


def test_equal_mode_and_bohr_are_kept_with_the_charges_as_read(tmp_path):
    ls = lines()
    ls[3], ls[4] = "au", "equal"
    i = ion.from_mfj(_write(ls, tmp_path))
    assert i.units == "bohr" and i.charge_mode == "equal"
    assert i.conformers[0].charges == ion.from_mfj(NINE).conformers[0].charges
    assert i.columns["charges"]["source"].endswith("column 5 (equal mode)")


def _edit(i: int, new: str | None):
    def fn(ls):
        if new is None:
            del ls[i:]
        else:
            ls[i] = new
        return ls
    return fn


@pytest.mark.parametrize("fn, message", [
    (_edit(1, "2"), "line 2: 2 coordinate sets; MobCal-MPI reads one"),
    (_edit(3, "ANG"), "line 4: units 'ANG'"),
    (_edit(4, "calc2"), "line 5: charge mode 'calc2'"),
    (_edit(5, "on"), "line 6: line 6 is not a number"),
    (_edit(6, "10 40 1000 2 5013489"), "line 7: '10 40 1000 2 5013489' is not a run line"),
    (_edit(6, "10 40 1000.0 2 5013489 301"), "is not a run line"),
    (_edit(9, "1 2 3 12.01 0.1 1 2 3"), "line 10: 8 fields"),
    (_edit(12, "1 2 3 12.01 0.1 1 2 3 x"), "line 13: G is not a number: 'x'"),
    (_edit(20, None), "line 21: file ends before the atom 14"),
    (lambda ls: ls + ["1 2 3 12.01 0.1 1 2 3 4"], "line 29: more lines follow the 21 atoms"),
])
def test_the_reader_refuses(fn, message):
    with pytest.raises(MobcalMpiError, match=message.replace("(", r"\(").replace(")", r"\)")):
        MobcalMpiMfj.parse(text(fn(lines())))


def test_a_refusal_reaches_from_mfj_as_an_ion_error(tmp_path):
    ls = lines()
    ls[1] = "3"
    with pytest.raises(IonError, match="MobCal-MPI layout: line 2: 3 coordinate sets"):
        ion.from_mfj(_write(ls, tmp_path))


# --- mobcal import X.mfj ---------------------------------------------------------------------

def test_import_writes_the_ion_file_of_either_layout(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["import", str(NINE)]) == 0
    out = capsys.readouterr().out
    assert ("wrote choline_mobcalmpi.ion.json: 21 atoms, 1 conformer from "
            "choline_mobcalmpi.mfj (MobCal-MPI layout), calc mode, net charge +1, every element "
            "in the He and N2 tables") in out
    i = Ion.read(tmp_path / "choline_mobcalmpi.ion.json")
    assert i.mfj(parameters.shipped("n2")) == Mfj.read(CHOLINE)
    assert cli.main(["import", str(CHOLINE)]) == 0
    assert "from Choline.mfj, calc mode, net charge +1" in capsys.readouterr().out
    assert Ion.read(tmp_path / "Choline.ion.json").mfj(parameters.shipped("he")) == \
        Mfj.read(CHOLINE)


def test_import_of_a_mfj_refuses_a_charge_choice_and_checks_the_gases(tmp_path, capsys):
    assert cli.main(["import", str(CHOLINE), "--charges", "column", "--net-charge", "1",
                     "-o", str(tmp_path / "c.ion.json")]) == 2
    assert ("Choline.mfj: a .mfj carries its charges, which the ion file keeps as read; "
            "--charges and --net-charge are not taken") in capsys.readouterr().err
    n2 = TESTS / "elements" / "n2.mfj"  # carries phosphorus, which the helium table lacks
    assert cli.main(["import", str(n2), "-o", str(tmp_path / "n2.ion.json")]) == 2
    assert "P (1 atom) is not in the He element table" in capsys.readouterr().err
    assert cli.main(["import", str(n2), "--gas", "n2", "-o", str(tmp_path / "n2.ion.json")]) == 0
    assert Ion.read(tmp_path / "n2.ion.json").mfj(parameters.shipped("n2")) == Mfj.read(n2)


def test_structure_from_mfj_names_an_unreadable_file(tmp_path):
    bad = tmp_path / "bad.mfj"
    bad.write_text("label\n1\n2\nang\ncalc\n1.0\n0 0 0 12 0\n", encoding="latin-1")
    with pytest.raises(structure.StructureError, match=r"bad.mfj: line 8: file ends before"):
        structure.from_mfj(bad)
    with pytest.raises(structure.StructureError, match="cannot read"):
        structure.from_mfj(tmp_path / "missing.mfj")
