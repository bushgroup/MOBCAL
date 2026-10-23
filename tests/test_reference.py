"""The derivation test: the gate's references are the 2012 outputs and two documented changes.

``tests/reference/`` holds choline in helium and in nitrogen as the current programs print it,
at the 2012 seed, staged input name and generator. ``fortran/sample-output/`` holds the 2012
originals, which are never edited. The two differ by exactly two changes to how the programs
print, made in one commit:

- **The atom count** (format 612) is printed ``i7``, where 2012 printed ``i4``, so that any count
  the bound allows fits. One line per output, the same number.
- **The q1st column** of the ``average values for q1st`` table is printed divided by ``itn``, the
  number of cycles it was summed over, where 2012 divided by ``inp``, the number of velocity
  points: 4x the 2012 values at the shipped ``itn = 10``, ``inp = 40``. Forty lines per output.
  The gst2 and wgst columns beside it are unchanged.

Every other line is byte-identical, so every cross section, mobility and moment is the 2012
number. ``gate.underived`` states the rule, the q1st values within what two roundings allow of
4x the 2012 values (``gate.q1st_bound``), and the corrected column must satisfy the identity that
shows the divisor is right: the wgst-weighted sum of q1st is the printed mean OMEGA*(1,1). The
2012 column gives a quarter of it.
"""

from __future__ import annotations

import re

import pytest

import gate
from mobcal.io.outfile import OutFile

Q1ST_ROWS = 40  # inp, the velocity points
MEAN = re.compile(r"^ mean OMEGA\*\(1,1\) = (\S+)$")


@pytest.fixture(params=sorted(gate.REFERENCE))
def pair(request) -> tuple[OutFile, OutFile]:
    name = gate.REFERENCE[request.param]
    return OutFile.read(gate.ORIGINALS / name), OutFile.read(gate.REFS / name)


def test_the_references_are_the_2012_outputs_printed_now(pair):
    old, new = pair
    assert gate.underived(old.lines, new.lines) == []


def test_exactly_the_two_changes_were_made(pair):
    old, new = pair
    rows = gate.q1st_rows(old.lines)
    assert len(rows) == Q1ST_ROWS
    differ = [i for i, (a, b) in enumerate(zip(old.lines, new.lines, strict=True)) if a != b]
    atoms = [i for i, s in enumerate(old.lines) if gate.ATOMS.match(s)]
    assert differ == sorted(atoms + rows) and len(atoms) == 1


def test_the_corrected_q1st_sums_to_the_mean_collision_integral(pair):
    old, new = pair
    mean = next(m.group(1) for s in new.lines if (m := MEAN.match(s)))
    rows = [new.lines[i].split() for i in gate.q1st_rows(new.lines)]
    total = sum(float(w) * float(q) for _, w, q in rows)
    # Each product carries the rounding of both printed factors; the mean its own.
    slack = gate.ulp(mean) / 2 + sum(float(w) * gate.ulp(q) / 2 + float(q) * gate.ulp(w) / 2
                                     for _, w, q in rows)
    assert abs(total - float(mean)) <= slack
    assert f"{total:.4E}" == mean  # and, on these two outputs, to every printed digit
    rows = [old.lines[i].split() for i in gate.q1st_rows(old.lines)]
    total = sum(float(w) * float(q) for _, w, q in rows)
    assert f"{gate.Q1ST_FACTOR * total:.4E}" == mean


def test_the_rule_sees_a_moved_line():
    old = OutFile.read(gate.ORIGINALS / gate.REFERENCE["he"]).lines
    new = OutFile.read(gate.REFS / gate.REFERENCE["he"]).lines
    i = gate.q1st_rows(new)[0]
    g, w, q = new[i].split()
    moved = f"  {g}  {w}  {float(q) + 10 * gate.ulp(q):.4E}"
    assert gate.underived(old, new[:i] + [moved] + new[i + 1:]) == [(old[i], moved)]
    j = new.index(" average TM cross section = 5.5402E+01")
    assert gate.underived(old, new[:j] + [" average TM cross section = 5.5403E+01"]
                          + new[j + 1:]) != []
