"""mobcal.io.infile: the three records, the a30 limit on the two names, the seed, the split."""

import pytest

from mobcal import fortran
from mobcal.io.infile import MAX_SEED, InFile, InFileError


def test_the_shipped_run_file():
    i = InFile.read(fortran.FORTRAN_DIR / "mobcal.in")
    assert i == InFile("Choline.mfj", "temp.choline.n2.out", 5013489)
    assert i.split is None


def test_write_and_read_back(tmp_path):
    i = InFile("Choline_pop.mfj", "mobcal.out", 5013489)
    p = i.write(tmp_path)
    assert p == tmp_path / "mobcal.in"
    assert p.read_bytes() == b"Choline_pop.mfj\nmobcal.out\n5013489\n"
    assert InFile.read(p) == i


def test_the_fourth_record(tmp_path):
    i = InFile("Choline_pop.mfj", "mobcal.out", 5013489, (3, 2))
    p = i.write(tmp_path)
    assert p.read_bytes() == b"Choline_pop.mfj\nmobcal.out\n5013489\n3 2\n"
    assert InFile.read(p) == i
    assert InFile.parse("a\nb\n1\n\n4 0 trailing\n").split == (4, 0)
    assert InFile.parse("a\nb\n1\n\n\n").split is None
    with pytest.raises(InFileError, match="not two integers"):
        InFile.parse("a\nb\n1\n3 x\n")


@pytest.mark.parametrize("split", [(0, 0), (3, 4), (3, -1), (-1, 0), (3,), (1.0, 0), "3 1"])
def test_splits_the_program_would_refuse(split):
    with pytest.raises(InFileError, match="split"):
        InFile("x.mfj", "x.out", 1, split)


def test_names_longer_than_the_field_are_refused():
    name = "a" * 31
    with pytest.raises(InFileError, match="31 characters; the program reads 30"):
        InFile(name, "x.out", 1)
    with pytest.raises(InFileError, match="output file name"):
        InFile("x.mfj", name, 1)
    assert InFile("a" * 30, "b" * 30, 1).text().count("\n") == 3


@pytest.mark.parametrize("name", ["", " x.mfj", "x.mfj ", "x\ny"])
def test_names_the_field_would_mangle(name):
    with pytest.raises(InFileError):
        InFile(name, "x.out", 1)


@pytest.mark.parametrize("seed", [0, -1, MAX_SEED + 1, 1.5, "7"])
def test_seeds_outside_a_default_integer(seed):
    with pytest.raises(InFileError, match="seed"):
        InFile("x.mfj", "x.out", seed)


def test_parse_takes_the_first_thirty_characters_and_the_first_token():
    i = InFile.parse("a" * 35 + "\nout.out   \n 42 trailing\n")
    assert i == InFile("a" * 30, "out.out", 42)
    with pytest.raises(InFileError, match="three"):
        InFile.parse("a\nb\n")
    with pytest.raises(InFileError, match="not an integer"):
        InFile.parse("a\nb\nseed\n")
