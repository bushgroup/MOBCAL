"""mobcal.io.outfile: the one normalization, on its own terms, and the SUMMARY reader."""

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


def test_d_exponent_is_left_alone_even_on_the_mass_line():
    # Format 604 prints E now; a D there is a regressed format, and the comparison must see it.
    for line in (" mass of ion = 1.0417D+02", " dipole constant = 2.3642D-59",
                 " input file label = Choline_631G++dp_pop"):
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
    assert o.cross_sections == {} and o.conformers == []
    assert o.seed is None
    assert not o.ok
    assert o.last_line == "average TM cross section = 5.5402E+01"


def test_refusal_is_the_last_line():
    o = OutFile(" input file name = hbr.mfj\n total charge = 1.0000E+00\n"
                " type not defined for atom number  1\n\n")
    assert not o.ok and o.last_line == "type not defined for atom number  1"


def test_reference_runs_completed():
    for name in ("Choline_He.out", "Choline_N2.out"):
        o = OutFile.read(REFS / name)
        assert o.ok and o.coordinate_sets == 1
        assert o.last_line.startswith("number of failed trajectories =")


# The SUMMARY the helium binary wrote for Choline.mfj doubled into two identical coordinate
# sets (this workstation, MSYS2 gfortran 16.2.0, the recorded flags, seed 5013489, 2026-10-21;
# lab record, task 05). Set 1 repeats the single-set reference to every printed digit; set 2
# continues the same random stream.
_TWO_SETS = """\
 number of coordinate sets =    2
 number of atoms =  21



 SUMMARY

 program version = junkn.f
 input file name = Choline2.mfj
 input file label = Choline_631G++dp_pop
 temperature = 3.0100E+02
 using RANLUX with seed integer = 5013489

 mobility calculation by MOBIL4 (HS scattering)

 number of Monte Carlo trajectories = 250000

 minimum and maximum number of reflections =  4    4


    set     PA CS       PA MOB^-1      EHSS CS      EHSS MOB^-1    ASYMP
     1    6.1075E+01    1.1239E+03    6.3473E+01    1.1680E+03     1.2982
     2    6.0980E+01    1.1221E+03    6.3433E+01    1.1673E+03     1.2982

   AVGE   6.1027E+01    1.1230E+03    6.3453E+01    1.1677E+03     1.2982

 mobility calculation by MOBIL2 (trajectory method)

 trajectory parameters
 sw1 = 5.0000E-05       sw2 = 5.0000E-03
 dtsf1 = 5.0000E-01     dtsf2 = 1.0000E-01

 number of complete cycles (itn) =    10
 number of velocity points (inp) =    40
 number of random points (imp) =  1000
 total number of points = 400000

 total number of failed trajectories =   7


    set     TM CS       TM MOB^-1
     1    5.5402E+01    1.0195E+03
     2    5.5454E+01    1.0204E+03

   AVGE   5.5428E+01    1.0200E+03
"""


def test_two_coordinate_sets():
    o = OutFile(_TWO_SETS)
    assert o.ok and o.coordinate_sets == 2
    assert o.seed == 5013489 and o.input_name == "Choline2.mfj"
    assert o.conformers == [{"PA": 61.075, "EHS": 63.473, "TM": 55.402},
                            {"PA": 60.98, "EHS": 63.433, "TM": 55.454}]
    assert o.cross_sections == {"PA": 61.027, "EHS": 63.453, "TM": 55.428}


def test_two_coordinate_sets_nitrogen_shape():
    # The nitrogen binary has no MOBIL4 path: only the TM table.
    start = _TWO_SETS.index(" mobility calculation by MOBIL2")
    o = OutFile(_TWO_SETS[:_TWO_SETS.index(" mobility calculation by MOBIL4")] + _TWO_SETS[start:])
    assert o.conformers == [{"TM": 55.402}, {"TM": 55.454}]
    assert o.cross_sections == {"TM": 55.428}
