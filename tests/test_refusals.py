"""Every refusal of the program exits 1, the normal end exits 0, and the array bounds are guarded.

The 2012 program ended every termination with a bare ``stop``, which exits 0, so a refusal and a
finished calculation looked the same to a caller. Each refusal is now ``stop 1``. The static test
reads both sources and requires one bare ``stop`` in each, the normal end, and ``stop 1`` at every
other. The rest drive the refusals that a small input reaches in well under a second, on the
binary itself and outside the driver, and require exit 1 with the refusal as the output's last
line. The refusals they cannot reach quickly (``masses do not add up`` in a second coordinate set,
``Problem orientating along x axis``, ``ibst greater than 500``) the static test covers; the
``ifail`` cap is driven in ``test_split.py``, and the normal end's exit 0 by the regression gate's
choline runs.

The element table's refusals come first: before the input is opened, the program reads
``parameters.tab`` from its working directory, and a table that is missing, not of its format,
for the other gas, of a kind it does not read, longer than its arrays or not readable to the end
is refused with status 1, the refusal being the output's only line and echoed to the screen.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from mobcal import fortran, parameters
from mobcal.io.outfile import OutFile

_STOP = re.compile(r"\bstop\b(.*)$")

# Hydrogen bromide, two atoms. Bromine (key 35) is in neither gas's element table, but the units
# and the charge distribution are read and refused first.
_HBR = "HBr+\n1\n2\n{unit}\n{charge}\n1.0000\n 0 0 0 {key} 0.5\n 1.41 0 0 1 0.5\n"
_OK = {"unit": "ang", "charge": "calc", "key": 35}


def _chain(sets: int, atoms: int) -> str:
    """``atoms`` hydrogens on a line, the last of them bromine; ``sets`` declared, one given.

    The program reads the coordinate-set count, then the atom count, then the first set, and
    refuses the bromine before it needs the other sets, so the counts alone decide what happens.
    """
    rows = [f" {1.1 * i:.2f} 0 0 {35 if i == atoms else 1} 0.001" for i in range(1, atoms + 1)]
    return "\n".join(["chain", str(sets), str(atoms), "ang", "calc", "1.0000", *rows]) + "\n"


# (input, the records of mobcal.in after the two names, the output's last non-blank line)
REFUSALS = {
    # The array bounds: 100 coordinate sets (the main program's dimension tmc(100)) and 200,000
    # atoms (parameter len, mobcal_arrays.inc). At both bounds the input is accepted and runs on
    # to the bromine, which is atom 200000 and prints as such under format 602's i7.
    "sets over": (_chain(101, 2), ["1"], "number of coordinate sets exceeds the limit of 100"),
    "atoms over": (_chain(1, 200001), ["1"], "number of atoms exceeds the limit of 200000"),
    "both at bound": (_chain(100, 200000), ["1"], "type not defined for atom number 200000"),
    "units": (_HBR.format(**{**_OK, "unit": "nm"}), ["1"],
              "units not specified"),
    "charge": (_HBR.format(**{**_OK, "charge": "some"}), ["1"],
               "charge distribution not specified"),
    "element": (_HBR.format(**_OK), ["1"], "type not defined for atom number      1"),
    "split record": (_HBR.format(**_OK), ["1", "2 3"],
                     "bad split record in mobcal.in:       2       3"),
    # The generator word on the seed record: ranlux or philox, nothing else, and it is refused
    # before the element table or the input is read.
    "generator word": (_HBR.format(**_OK), ["1 mersenne"],
                       "random number generator mersenne in mobcal.in is not ranlux or philox"),
    "generator case": (_HBR.format(**_OK), ["1 Philox"],
                       "random number generator Philox in mobcal.in is not ranlux or philox"),
    "generator long": (_HBR.format(**_OK), ["1 philox4x32-10"],
                       "random number generator philox4x in mobcal.in is not ranlux or philox"),
}


def _table(gas: str, edit=None) -> str:
    """The rendered shipped table for ``gas``, with an optional edit of its lines."""
    lines = parameters.shipped(gas).lines()
    return "\n".join(edit(lines) if edit else lines) + "\n"


def _line(i: int, old: str, new: str):
    def edit(lines):
        assert old in lines[i], lines[i]
        lines[i] = lines[i].replace(old, new)
        return lines
    return edit


# (the parameters.tab written beside the input, None for no file; the refusal)
TABLE_REFUSALS = {
    "missing": (None, "parameter table parameters.tab not found in the working directory; "
                      "mobcal run writes it"),
    "other gas": (_table("n2"), "parameters.tab is a table for N2; this program is for He"),
    "magic": (_table("he", _line(0, "MOBCAL-LJ", "MOBCAL-XX")),
              "parameters.tab is not a MOBCAL-LJ 1 table"),
    "rendered format": (_table("he", _line(0, "MOBCAL-LJ 1 ", "MOBCAL-LJ 2 ")),
                        "parameters.tab is not a MOBCAL-LJ 1 table"),
    "empty": ("", "parameters.tab is not a MOBCAL-LJ 1 table"),
    "kind": (_table("he", _line(1, "8 8 8 8", "8 2 8 8")),
             "parameters.tab declares a kind of   2 bytes; 4 or 8 are read"),
    "rows over": (_table("he", lambda ls: ls[:2] + ["101"]
                         + [f"{k} 1.0d0 1.0d0 1.0d0 1.0d0" for k in range(1, 102)]),
                  "parameters.tab has   101 rows; 1 to 100 are allowed"),
    "rows at bound": (_table("he", lambda ls: ls[:2] + ["100"]
                             + [f"{k} 1.0d0 1.0d0 1.0d0 1.0d0" for k in range(101, 201)]),
                      "type not defined for atom number      1"),  # read; no key of HBr in it
    "short": (_table("he", lambda ls: ls[:5]),
              "parameters.tab cannot be read as a MOBCAL-LJ 1 table"),
    "token": (_table("he", _line(3, "1.008d0", "1.0x8d0")),
              "parameters.tab cannot be read as a MOBCAL-LJ 1 table"),
}


def _statements(name: str) -> list[str]:
    """The source's lines, comment lines (``c``, ``C`` or ``*`` in column 1) blanked."""
    lines = (fortran.FORTRAN_DIR / name).read_text(encoding="latin-1").splitlines()
    return ["" if s[:1] in ("c", "C", "*") else s for s in lines]


@pytest.mark.parametrize("gas", fortran.GASES)
def test_the_normal_end_is_the_only_bare_stop(gas):
    lines = _statements(fortran.SOURCE[gas])
    stops = {i: m.group(1).strip() for i, s in enumerate(lines) if (m := _STOP.search(s[6:]))}
    bare = [i for i, code in stops.items() if code == ""]
    assert len(bare) == 1, [lines[i] for i in bare]
    i = bare[0]
    assert [s.strip() for s in lines[i - 2:i + 2]] == ["9999 continue", "close (8)", "stop", "end"]
    assert {code for j, code in stops.items() if j != i} == {"1"}


def test_every_stop_of_the_includes_exits_1():
    stops = {}
    for inc in fortran.INCLUDES:
        lines = _statements(inc)
        stops[inc] = [m.group(1).strip() for s in lines if (m := _STOP.search(s[6:]))]
    assert stops["mobcal_ljread.inc"] and set(stops["mobcal_ljread.inc"]) == {"1"}
    assert stops["mobcal_rng.inc"] == []  # the generator refuses nothing


@pytest.mark.parametrize("case", REFUSALS)
def test_a_refusal_exits_1(pool, tmp_path, case):
    text, records, last = REFUSALS[case]
    for gas, binary in pool.binaries.items():
        d = tmp_path / gas
        d.mkdir()
        (d / "in.mfj").write_text(text, encoding="latin-1", newline="\n")
        run = ["in.mfj", "out.txt", *records]
        (d / "mobcal.in").write_text("\n".join(run) + "\n", encoding="latin-1", newline="\n")
        parameters.shipped(gas).render(d)
        proc = subprocess.run([str(binary)], cwd=d, capture_output=True, timeout=60,
                              stdin=subprocess.DEVNULL)
        out = OutFile.read(d / "out.txt")
        assert proc.returncode == 1, (gas, proc.returncode, out.last_line)
        assert out.last_line == last and not out.ok, (gas, out.lines[-3:])
        if case.startswith("generator"):
            assert out.lines == [" " + last]  # before the table and the input are read


@pytest.mark.parametrize("case", TABLE_REFUSALS)
def test_a_bad_table_is_refused_before_the_input_is_read(pool, tmp_path, case):
    table, last = TABLE_REFUSALS[case]
    binary = pool.binaries["he"]
    (tmp_path / "in.mfj").write_text(_HBR.format(**_OK), encoding="latin-1", newline="\n")
    (tmp_path / "mobcal.in").write_text("in.mfj\nout.txt\n1\n", encoding="latin-1",
                                        newline="\n")
    if table is not None:
        (tmp_path / parameters.RENDERED).write_text(table, encoding="ascii", newline="\n")
    proc = subprocess.run([str(binary)], cwd=tmp_path, capture_output=True, text=True,
                          timeout=60, stdin=subprocess.DEVNULL)
    out = OutFile.read(tmp_path / "out.txt")
    assert proc.returncode == 1, (proc.returncode, out.last_line)
    assert out.last_line == last and not out.ok, out.lines[-3:]
    if case == "rows at bound":
        assert out.lines[0].startswith(" input file name")
    else:
        assert out.lines == [" " + last]  # the refusal precedes everything
        assert " " + last in proc.stdout.replace("\r", "").splitlines()


def test_the_set_count_is_refused_before_the_atom_count_is_read(pool, tmp_path):
    binary = next(iter(pool.binaries.values()))
    (tmp_path / "in.mfj").write_text(_chain(101, 2), encoding="latin-1", newline="\n")
    (tmp_path / "mobcal.in").write_text("in.mfj\nout.txt\n1\n", encoding="latin-1",
                                        newline="\n")
    parameters.shipped(next(iter(pool.binaries))).render(tmp_path)
    subprocess.run([str(binary)], cwd=tmp_path, capture_output=True, timeout=60,
                   stdin=subprocess.DEVNULL)
    lines = OutFile.read(tmp_path / "out.txt").lines
    assert lines[-2:] == [" number of coordinate sets =  101",
                          " number of coordinate sets exceeds the limit of 100"]
