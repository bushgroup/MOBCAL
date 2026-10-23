"""Every row of both element tables, read from ``parameters.tab``, against the 2012 chains.

Choline sees four rows of each table and one coordinate set, so the regression gate alone
cannot show that the reader gives every element the number its ``if(imass(iatom).eq.NN)``
block gave. ``tests/elements/`` holds what the programs built from those chains computed, captured
before the chains left the source (its README says how), and this file holds the reader to it
two ways:

- **Every row at full precision.** ``ljprobe.f``, compiled with the program's own
  ``mobcal_ljread.inc`` under the recorded flags, reads the rendered table and prints the mass,
  well depth, radius and hard-sphere radius an atom of each key is assigned, as 64-bit
  patterns. ``rows.json`` holds the patterns the compiled chains gave: the same evaluation,
  term for term, from the literals as the source spelled them. Each must match to the bit,
  which is what the kind rule exists for: nitrogen's literals are single precision, and a
  well depth read as double would differ in its eighth digit.

- **Whole outputs through the real binaries.** The all-elements inputs of ``probe.py``, one atom
  per row and two identical coordinate sets, run as worker 400 of 400 so that both sets reach
  the SUMMARY in seconds, must reproduce the captured outputs byte for byte: helium, and
  nitrogen without silicon. Nitrogen with silicon differs in set 2 and nowhere else, because the
  2012 ``ncoord`` gave silicon iron's well depth and radius and the table gives ``fcoord``'s;
  those lines are the one difference the change was meant to make.
"""

from __future__ import annotations

import json
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import probe
from mobcal import fortran, parameters
from mobcal.io.outfile import OutFile

FIXTURES = Path(__file__).resolve().parent / "elements"
LJPROBE = Path(__file__).resolve().parent / "ljprobe.f"
ROWS = json.loads((FIXTURES / "rows.json").read_text(encoding="utf-8"))["rows"]

# The lines of the captured nitrogen output that the silicon fix moves: set 2's trajectory
# result, in its own block and in the SUMMARY (the average with it).
SILICON_LINES = [
    " average (second order) TM mobility = 9.5389E-02",
    " inverse average (second order) TM mobility = 1.0483E+01",
    " average TM cross section = 2.3316E-01",
    "     2    2.3316E-01    1.0483E+01",
    "   AVGE   2.5908E-01    1.1527E+01",
]


def _fixture(stem: str) -> str:
    return (FIXTURES / f"{stem}.out").read_text(encoding="latin-1")


# --- the fixtures themselves ----------------------------------------------------------------

@pytest.mark.parametrize("stem", probe.INPUTS)
def test_the_captured_input_is_the_generated_one(stem):
    gas, drop = probe.INPUTS[stem]
    assert (FIXTURES / f"{stem}.mfj").read_text(encoding="ascii") == probe.all_elements(gas, drop)
    out = OutFile(_fixture(stem))
    assert out.ok and out.coordinate_sets == 2 and out.input_name == probe.INPUT
    assert out.seed == probe.SEED and len(out.conformers) == 2
    assert out.generator == probe.GENERATOR


@pytest.mark.parametrize("gas", fortran.GASES)
def test_the_captured_rows_are_every_row_of_the_table(gas):
    # The chains are in the source's order, the files in ascending key; the sets must agree.
    keys = {str(k) for k in parameters.shipped(gas).keys}
    assert set(ROWS[gas]["fcoord"]) == keys and set(ROWS[gas]["ncoord"]) == keys


def test_the_captured_chains_differ_only_at_nitrogens_silicon_which_held_iron():
    he, n2 = ROWS["he"], ROWS["n2"]
    assert he["fcoord"] == he["ncoord"]
    assert {k for k in n2["fcoord"] if n2["fcoord"][k] != n2["ncoord"][k]} == {"28"}
    for col in ("epsilon", "sigma"):
        assert n2["ncoord"]["28"]["bits"][col] == n2["fcoord"]["56"]["bits"][col]
    for col in ("mass", "rhs"):
        assert n2["ncoord"]["28"]["bits"][col] == n2["fcoord"]["28"]["bits"][col]


# --- every row at full precision, through the reader -----------------------------------------

@pytest.fixture(scope="module")
def ljprobe(gfortran, tmp_path_factory) -> Path:
    """``ljprobe.f`` compiled with the pinned include under the recorded flags, no warnings."""
    d = tmp_path_factory.mktemp("ljprobe")
    exe = d / ("ljprobe.exe" if sys.platform == "win32" else "ljprobe")
    cmd = [gfortran, *fortran.flags(), "-I", str(fortran.FORTRAN_DIR), "-o", str(exe),
           str(LJPROBE)]
    proc = subprocess.run(cmd, env=fortran._env(gfortran), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace")
    assert proc.returncode == 0, proc.stdout
    assert fortran.count_warnings(proc.stdout) == 0, proc.stdout
    return exe


def _probe(exe: Path, d: Path, gas: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    proc = subprocess.run([str(exe)], cwd=d, input=parameters.GAS[gas] + "\n",
                          capture_output=True, text=True, timeout=60)
    text = (d / "probe.txt").read_text(encoding="ascii") if (d / "probe.txt").exists() else ""
    return proc, [s.rstrip("\r") for s in text.splitlines()]


@pytest.mark.parametrize("gas", fortran.GASES)
def test_every_row_reads_back_bit_identical_to_the_compiled_chain(ljprobe, tmp_path, gas):
    ps = parameters.shipped(gas)
    ps.render(tmp_path)
    proc, lines = _probe(ljprobe, tmp_path, gas)
    assert proc.returncode == 0, (proc.stdout, lines)
    assert proc.stdout.split() == ["parameter", "set", ps.name.replace(" ", "_"), ps.sha256]
    got = {}
    for line in lines:
        key, found, *bits = line.split()
        assert found == "1", line
        got[key] = dict(zip(parameters.COLUMNS, [b.lower() for b in bits], strict=True))
    want = {k: row["bits"] for k, row in ROWS[gas]["fcoord"].items()}
    assert got == want


def test_a_nitrogen_well_depth_is_the_single_precision_one(ljprobe, tmp_path):
    # Silicon's epsilon token is 0.4020, a REAL(4) literal. Read as REAL(8) it would be a
    # different number from the eighth digit on; the reader converts it by its declared kind.
    bits = ROWS["n2"]["fcoord"]["28"]["bits"]["epsilon"]
    eolj = struct.unpack(">d", bytes.fromhex(bits))[0]
    single = struct.unpack(">f", struct.pack(">f", 0.4020))[0]
    xe = 1.60217733e-19
    eogas, conve = 0.06900, parameters.evaluate("4.2d0*0.01036427d0")
    assert eolj == math.sqrt(eogas * single) * conve * xe
    assert eolj != math.sqrt(eogas * 0.4020) * conve * xe
    assert ROWS["n2"]["fcoord"]["28"]["digits"]["epsilon"] == "1.1615453442535021E-021"


def test_the_probe_refuses_a_table_for_the_other_gas(ljprobe, tmp_path):
    parameters.shipped("n2").render(tmp_path)
    proc, lines = _probe(ljprobe, tmp_path, "he")
    assert proc.returncode == 1
    assert lines == [" parameters.tab is a table for N2; this program is for He"]


# --- whole outputs through the real binaries -------------------------------------------------

@pytest.fixture(scope="module")
def binaries(gfortran, tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("elements-bin")
    return {g: fortran.build(g, d, gfortran).binary for g in fortran.GASES}


def _run(binary: Path, d: Path, gas: str, text: str) -> tuple[subprocess.CompletedProcess, OutFile]:
    (d / probe.INPUT).write_text(text, encoding="ascii", newline="\n")
    (d / "mobcal.in").write_text(probe.run_file(), encoding="ascii", newline="\n")
    parameters.shipped(gas).render(d)
    proc = subprocess.run([str(binary)], cwd=d, capture_output=True, text=True, timeout=600,
                          stdin=subprocess.DEVNULL)
    return proc, OutFile.read(d / probe.OUTPUT)


@pytest.mark.parametrize("stem", ["he", "n2-no-si"])
def test_the_probe_output_is_byte_identical_to_the_2012_chains(binaries, tmp_path, stem):
    gas, drop = probe.INPUTS[stem]
    proc, out = _run(binaries[gas], tmp_path, gas, probe.all_elements(gas, drop))
    assert proc.returncode == 0, out.last_line
    assert out.generator == probe.GENERATOR and out.text == _fixture(stem)


def test_nitrogen_with_silicon_differs_from_2012_in_set_2_only(binaries, tmp_path):
    proc, out = _run(binaries["n2"], tmp_path, "n2", probe.all_elements("n2"))
    assert proc.returncode == 0, out.last_line
    ref = _fixture("n2").splitlines()
    new = out.lines
    assert len(new) == len(ref)
    differing = [(a, b) for a, b in zip(ref, new, strict=True) if a != b]
    assert [a for a, _ in differing] == SILICON_LINES
    second = ref.index(" coordinate set =    2")
    assert ref[:second] == new[:second]
    # Set 1's result stands; set 2's is silicon's now, not iron's.
    assert out.conformers[0] == OutFile(_fixture("n2")).conformers[0]
    assert out.conformers[1]["TM"] != OutFile(_fixture("n2")).conformers[1]["TM"]
    assert re.fullmatch(r"\s+2\s+\d\.\d{4}E[+-]\d\d\s+\d\.\d{4}E[+-]\d\d", differing[3][1])
