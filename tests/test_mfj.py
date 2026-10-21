"""mobcal.io.mfj: the shipped input, the a30 rules, the bounds, and what is refused."""

import pytest

from mobcal import fortran
from mobcal.io.mfj import MAX_ATOMS, MAX_SETS, Atom, Mfj, MfjError

CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"

HEADER = "label\n1\n2\nang\ncalc\n1.0000\n"
ATOMS = " 0.0 0.0 0.0 14 0.25\n 1.0 0.0 0.0 1 0.75\n"


def test_choline():
    m = Mfj.read(CHOLINE)
    assert m.label == "Choline_631G++dp_pop"
    assert m.coordinate_sets == 1 and m.atoms == 21
    assert m.units == "ang" and m.charge_mode == "calc" and m.correct == 1.0
    assert m.keys == (1, 12, 14, 16)
    assert m.has_charge_column
    assert m.net_charge() == pytest.approx(1.0, abs=1e-5)
    assert m.sets[0][0] == Atom(-0.878, 0.022, 0.0, 14, -0.021059)
    assert m.sets[0][-1] == Atom(3.633, -0.154, 0.0, 1, 0.463592)


def test_two_sets_with_any_separator_line():
    m = Mfj.parse("two\n2\n2\nau\nequal\n0.99\n" + ATOMS + "conformer 2\n" + ATOMS)
    assert m.coordinate_sets == 2 and m.atoms == 2 and m.units == "au"
    assert m.correct == 0.99
    assert m.sets[0] == m.sets[1]


def test_four_columns_outside_calc_mode():
    m = Mfj.parse("x\n1\n2\nang\nnone\n1\n 0 0 0 12\n 1 1 1 1\n")
    assert [a.charge for a in m.sets[0]] == [None, None]
    assert not m.has_charge_column and m.net_charge() is None
    assert m.keys == (1, 12)


def test_list_directed_fields_and_d_exponents():
    m = Mfj.parse("x\n1\n1\nang\ncalc\n1.d0\n1.5d0,2.0D-1,-3,12.0,1.0\n")
    assert m.correct == 1.0
    assert m.sets[0][0] == Atom(1.5, 0.2, -3.0, 12, 1.0)


def test_label_is_the_first_thirty_characters():
    long = "a" * 40
    assert Mfj.parse(f"{long}\n1\n1\nang\nnone\n1\n0 0 0 1\n").label == "a" * 30


def test_key_is_rounded_like_nint():
    m = Mfj.parse("x\n1\n2\nang\nnone\n1\n0 0 0 12.4\n0 0 0 2.014\n")
    assert [a.key for a in m.sets[0]] == [12, 2]


@pytest.mark.parametrize("units", [" ang", "angstrom", "AU", "Ang", ""])
def test_units_the_program_stops_on(units):
    with pytest.raises(MfjError, match="line 4: units"):
        Mfj.parse(f"x\n1\n1\n{units}\nnone\n1\n0 0 0 1\n")


@pytest.mark.parametrize("mode", [" calc", "CALC", "uniform", ""])
def test_charge_modes_the_program_stops_on(mode):
    with pytest.raises(MfjError, match="line 5: charge mode"):
        Mfj.parse(f"x\n1\n1\nang\n{mode}\n1\n0 0 0 1\n")


def test_trailing_blanks_do_not_matter():
    m = Mfj.parse("x   \n1\n1\nang   \ncalc \n1\n0 0 0 1 1\n")
    assert m.units == "ang" and m.charge_mode == "calc" and m.label == "x"


def test_bounds():
    ok = Mfj.parse(f"x\n1\n{MAX_ATOMS}\nang\nnone\n1\n" + "0 0 0 1\n" * MAX_ATOMS)
    assert ok.atoms == MAX_ATOMS
    with pytest.raises(MfjError, match=f"line 3: {MAX_ATOMS + 1} atoms"):
        Mfj.parse(f"x\n1\n{MAX_ATOMS + 1}\nang\nnone\n1\n" + "0 0 0 1\n" * (MAX_ATOMS + 1))
    with pytest.raises(MfjError, match=f"line 2: {MAX_SETS + 1} coordinate sets"):
        Mfj.parse(f"x\n{MAX_SETS + 1}\n1\nang\nnone\n1\n0 0 0 1\n")
    with pytest.raises(MfjError, match="line 3: 0 atoms"):
        Mfj.parse("x\n1\n0\nang\nnone\n1\n")


def test_short_atom_line():
    with pytest.raises(MfjError, match="line 7: 4 fields on an atom line; 5 are read in calc"):
        Mfj.parse(HEADER + " 0 0 0 14\n 1 0 0 1 0.75\n")


def test_file_ends_early():
    with pytest.raises(MfjError, match="line 8: file ends before the atom 2 of coordinate set 1"):
        Mfj.parse(HEADER + " 0 0 0 14 0.25\n")
    with pytest.raises(MfjError, match="line 10: file ends before the atom 1 of coordinate set 2"):
        Mfj.parse("x\n2\n2\nang\ncalc\n1\n" + ATOMS + "sep\n")
    with pytest.raises(MfjError, match="line 2: file ends before the number of coordinate sets"):
        Mfj.parse("x\n")


def test_non_numeric_fields():
    with pytest.raises(MfjError, match="line 2: number of coordinate sets is not an integer"):
        Mfj.parse("x\none\n1\nang\nnone\n1\n0 0 0 1\n")
    with pytest.raises(MfjError, match="line 7: coordinate y is not a number: 'y'"):
        Mfj.parse("x\n1\n1\nang\nnone\n1\n0 y 0 1\n")
    with pytest.raises(MfjError, match="line 6: correction factor is missing"):
        Mfj.parse("x\n1\n1\nang\nnone\n\n0 0 0 1\n")
