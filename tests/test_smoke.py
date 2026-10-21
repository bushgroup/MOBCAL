"""Founding tests: the version, the 2012 pins, and the build recipe's one mandatory flag."""

import tomllib
from pathlib import Path

import mobcal
from mobcal import cli, fortran

ROOT = Path(__file__).resolve().parent.parent


def test_version_declarations_agree():
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert proj["version"] == mobcal.__version__


def test_fortran_is_the_2012_code():
    assert fortran.verify_sources() == []


def test_fno_automatic_is_mandatory():
    assert "-fno-automatic" in fortran.FFLAGS
    assert "-std=legacy" in fortran.FFLAGS


# What gfortran 16.2.0 (MSYS2) writes for mobcal_He.f without -std=legacy, first of 64.
_DELETED_FEATURE = """\
fortran/mobcal_He.f:417:72:

  417 |      ?ehsc(i)*1.0d20,1.d0/ehsm(i),asympp(i)/10.d0
      |                                                                        1
Warning: Fortran 2018 deleted feature: DO termination statement which is not END DO or \
CONTINUE with label 1010 at (1)
"""


def test_warning_count():
    assert fortran.count_warnings("") == 0
    assert fortran.count_warnings(_DELETED_FEATURE) == 1
    assert fortran.count_warnings(_DELETED_FEATURE * 64) == 64
    assert fortran.count_warnings("ld: warning: object file was built for newer macOS\n") == 1
    # The word in a source excerpt or a path is not a diagnostic.
    assert fortran.count_warnings("  12 |      c Warning: in a comment\nwarnings/x.f\n") == 0


def test_cli_version(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == mobcal.__version__
