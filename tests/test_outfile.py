"""mobcal.io.outfile: the one normalization, on its own terms, and the SUMMARY reader."""

import subprocess
import sys
from pathlib import Path

from mobcal import fortran, parameters
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile, normalize, read_text
from mobcal.settings import DEFAULTS

REFS = fortran.FORTRAN_DIR / "sample-output"
ELEMENTS = Path(__file__).resolve().parent / "elements"
FAKE = Path(__file__).resolve().parent / "fake_mobcal.py"


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
# sets (an 80-thread Windows 11 workstation, MSYS2 gfortran 16.2.0, the recorded flags, seed
# 5013489, 2026-10-21; lab record, task 05). Set 1 repeats the single-set reference to every
# printed digit; set 2 continues the same random stream.
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


# --- every line of the SUMMARY, typed: the printed digits, never rounded or derived ----------

def test_helium_reference_types_every_summary_line():
    o = OutFile.read(REFS / "Choline_He.out")
    assert o.program_version == "junkn.f"
    assert o.input_label == "Choline_631G++dp_pop"
    assert o.temperature == 301.0
    assert o.asymmetry_parameter == 1.2982 and o.conformer_asymmetry == [1.2982]
    assert o.hard_sphere_trajectories == 250000
    assert o.maximum_reflections == 4 and o.minimum_reflections is None
    assert o.inverse_mobilities == {"PA": 1123.9, "EHS": 1168.0, "TM": 1019.5}
    assert o.conformer_inverse_mobilities == [o.inverse_mobilities]
    assert o.trajectory_parameters == {"sw1": 5e-5, "sw2": 5e-3, "dtsf1": 0.5, "dtsf2": 0.1}
    assert (o.itn, o.inp, o.imp, o.total_points) == (10, 40, 1000, 400000)
    assert o.failed_trajectories == 3
    assert o.tm_standard_deviation == 0.92127
    assert o.summary_lines[0] == " SUMMARY"
    assert o.summary_lines[-1] == " number of failed trajectories =   3"
    assert len(o.summary_lines) == 35


def test_nitrogen_reference_types_every_summary_line():
    o = OutFile.read(REFS / "Choline_N2.out")
    assert o.input_label == "Choline_631G++dp_pop" and o.temperature == 301.0
    assert o.asymmetry_parameter == 1.2982
    assert o.hard_sphere_trajectories is None
    assert o.maximum_reflections is None and o.minimum_reflections is None
    assert o.inverse_mobilities == {"TM": 5104.9}
    assert o.trajectory_parameters == {"sw1": 5e-5, "sw2": 5e-3, "dtsf1": 0.5, "dtsf2": 0.1}
    assert o.total_points == 400000 and o.failed_trajectories == 0
    assert o.tm_standard_deviation == 1.0948


def test_no_summary_types_nothing():
    o = OutFile(" mass of ion = 1.0417E+02\n")
    assert o.summary_lines == [] and o.inverse_mobilities == {}
    assert o.conformer_inverse_mobilities == [] and o.conformer_asymmetry == []
    for name in ("program_version", "input_label", "temperature", "asymmetry_parameter",
                 "hard_sphere_trajectories", "maximum_reflections", "minimum_reflections",
                 "trajectory_parameters", "itn", "inp", "imp", "total_points",
                 "failed_trajectories", "tm_standard_deviation"):
        assert getattr(o, name) is None, name


def test_two_coordinate_sets_type_every_column():
    o = OutFile(_TWO_SETS)
    assert o.hard_sphere_trajectories == 250000
    assert (o.minimum_reflections, o.maximum_reflections) == (4, 4)
    assert o.conformer_inverse_mobilities == [{"PA": 1123.9, "EHS": 1168.0, "TM": 1019.5},
                                              {"PA": 1122.1, "EHS": 1167.3, "TM": 1020.4}]
    assert o.inverse_mobilities == {"PA": 1123.0, "EHS": 1167.7, "TM": 1020.0}
    assert o.conformer_asymmetry == [1.2982, 1.2982] and o.asymmetry_parameter == 1.2982
    assert o.failed_trajectories == 7 and o.total_points == 400000
    assert o.tm_standard_deviation is None  # several sets: the program prints none
    assert o.conformers[0] == {"PA": 61.075, "EHS": 63.473, "TM": 55.402}  # no 1/ or ASYMP keys


def test_probe_outputs_with_two_sets():
    # The real programs' outputs for the two-set all-elements probe: the ASYMP column is the
    # quantity the body prints per set (the program's /10 undone by the 1P scale factor), and
    # nitrogen with several sets prints no asymmetry parameter in its SUMMARY.
    he = OutFile.read(ELEMENTS / "he.out")
    assert he.conformer_asymmetry == [1.3912, 1.3912] and he.asymmetry_parameter == 1.3912
    assert [line for line in he.lines[:he.lines.index(" SUMMARY")]
            if "structural asymmetry parameter" in line] == \
        [" structural asymmetry parameter =  1.3912"] * 2
    assert (he.minimum_reflections, he.maximum_reflections) == (3, 4)
    assert he.conformers == [{"PA": 61.959, "EHS": 62.483, "TM": 0.16775},
                             {"PA": 62.005, "EHS": 62.698, "TM": 0.17778}]
    assert he.inverse_mobilities == {"PA": 1150.9, "EHS": 1162.2, "TM": 3.2009}
    n2 = OutFile.read(ELEMENTS / "n2.out")
    assert n2.asymmetry_parameter is None and n2.conformer_asymmetry == [None, None]
    assert n2.hard_sphere_trajectories is None and n2.maximum_reflections is None
    assert n2.conformer_inverse_mobilities == [{"TM": 12.802}, {"TM": 10.483}]
    assert n2.failed_trajectories == 0


def test_the_stand_in_prints_every_line_the_parser_types(tmp_path):
    # tests/fake_mobcal.py, for one set and for three, in each gas: every property is set
    # where the real program's output of that shape sets it.
    body = (fortran.FORTRAN_DIR / "Choline.mfj").read_text(encoding="latin-1").split("\n", 1)[1]
    for gas in ("he", "n2"):
        for label, sets in (("ok", 1), ("sets 3", 3)):
            d = tmp_path / f"{gas}-{sets}"
            d.mkdir()
            (d / "in.mfj").write_text(f"{label}\n{body}", encoding="latin-1")
            InFile("in.mfj", "mobcal.out", 11).write(d)
            DEFAULTS.render(d)
            parameters.load(parameters.default_path(gas), gas=gas).render(d)
            subprocess.run([sys.executable, str(FAKE), gas], cwd=d, check=True)
            o = OutFile.read(d / "mobcal.out")
            methods = {"PA", "EHS", "TM"} if gas == "he" else {"TM"}
            assert o.ok and set(o.cross_sections) == methods
            assert set(o.inverse_mobilities) == methods
            assert len(o.conformers) == len(o.conformer_inverse_mobilities) == sets
            assert o.program_version == "junkn.f" and o.input_label == label
            assert o.temperature == 301.0 and o.trajectory_parameters is not None
            assert o.total_points == 400000 and o.failed_trajectories == 3
            assert (o.tm_standard_deviation is not None) == (sets == 1)
            assert (o.hard_sphere_trajectories == 250000) == (gas == "he")
            assert (o.maximum_reflections == 4) == (gas == "he")
            assert (o.minimum_reflections == 3) == (gas == "he" and sets > 1)
            assert (o.asymmetry_parameter is None) == (gas == "n2" and sets > 1)
