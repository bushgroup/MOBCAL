"""mobcal.io.outfile: the two normalizations, each on its own terms, and the SUMMARY reader."""

from mobcal import fortran
from mobcal.io.outfile import OutFile, normalize, read_text

REFS = fortran.FORTRAN_DIR / "sample-output"


def test_crlf_becomes_lf():
    assert normalize(" temperature = 3.0100E+02\r\n\r\n SUMMARY\r\n") == \
        " temperature = 3.0100E+02\n\n SUMMARY\n"


def test_trailing_blanks_before_cr_are_content():
    # The a30 filename fields: the blanks between the name and the CR stay.
    line = " input file name = Choline_pop.mfj               "
    assert normalize(line + "\r\n") == line + "\n"


def test_cr_is_stripped_at_end_of_line_only():
    assert normalize("a\rb\r\n") == "a\rb\n"
    assert normalize("last line\r") == "last line"
    assert normalize("one\r\r\n") == "one\r\n"


def test_d_exponent_on_the_mass_line():
    assert normalize(" mass of ion = 1.0417D+02\r\n") == " mass of ion = 1.0417E+02\n"
    assert normalize(" mass of ion = 1.0417D-02") == " mass of ion = 1.0417E-02"


def test_d_exponent_elsewhere_is_left_alone():
    for line in (" dipole constant = 2.3642D-59", " total charge = 1.0000D+00",
                 " input file label = Choline_631G++dp_pop", " mass of ion = HDD"):
        assert normalize(line) == line


def test_references_are_already_normal():
    for name in ("Choline_He.out", "Choline_N2.out"):
        text = read_text(REFS / name)
        assert "\r" not in text
        assert normalize(text) == text


def test_read_text_keeps_crlf(tmp_path):
    p = tmp_path / "x.out"
    p.write_bytes(b" a\r\n b\r\n")
    assert read_text(p) == " a\r\n b\r\n"
    assert OutFile.read(p).lines == [" a", " b"]


def test_helium_summary():
    o = OutFile.read(REFS / "Choline_He.out")
    assert o.cross_sections == {"PA": 61.075, "EHS": 63.473, "TM": 55.402}
    assert o.seed == 5013489
    assert o.input_name == "Choline_pop.mfj"
    assert o.summary["sw2"] == "5.0000E-03"
    assert o.summary["number of failed trajectories"] == "3"


def test_nitrogen_reports_tm_only():
    o = OutFile.read(REFS / "Choline_N2.out")
    assert o.cross_sections == {"TM": 115.92}
    assert o.seed == 5013489


def test_no_summary_block():
    o = OutFile(" mass of ion = 1.0417E+02\n average TM cross section = 5.5402E+01\n")
    assert o.summary == {}
    assert o.cross_sections == {}
    assert o.seed is None
