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


def test_cli_version(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == mobcal.__version__
