"""MOBIL2's x-axis orientation holds the farthest atom to 1e-10 of rmax off the axis, not 1e-20 m.

Before the trajectories, MOBIL2 rotates the atom farthest from the centre of mass onto +x and
stops with ``Problem orientating along x axis`` unless it lands there: ``fx/rmax`` within 1e-10
of 1, and ``fy``, ``fz`` within a tolerance. The 2012 tolerance was an absolute 1.0d-20 m. When
the farthest atom already lies almost on +x, the last rotation is almost nothing and the binary
computes it to ~1e-11 rad, so an ion of large radius was refused after its PA/EHS pass for no
physical reason: a 200,000-atom globule with an outlier on +x (rmax 106 Å, fy -7.7e-20 m), and
a 200-atom ion with an atom 100 Å out on +x (fz -1.79e-20 m), on the workstation the change was
made on. The tolerance is now ``max(1.0d-20, 1.0d-10*rmax)``: never tighter than 2012, so every
ion the 2012 code accepted it still accepts, and the same relative precision as the fx test.

Whether the old check refuses the small ion depends on the platform's ``dacos`` at the 1e-20 m
level, so the test asserts only what the new one guarantees: both programs orient it and go on.
The check passes silently for choline, so no output line moves.
"""

from __future__ import annotations

import pytest

import synthetic
from mobcal import fortran

TOLERANCE = "      tolxy=dmax1(1.0d-20,1.0d-10*rmax)"
PROBLEM = " Problem orientating along x axis"


@pytest.fixture(scope="module")
def binaries(gfortran, tmp_path_factory):
    d = tmp_path_factory.mktemp("orientation-bin")
    return {g: fortran.build(g, d, gfortran).binary for g in fortran.GASES}


@pytest.mark.parametrize("gas", fortran.GASES)
def test_the_off_axis_tolerance_is_relative(gas):
    text = (fortran.FORTRAN_DIR / fortran.SOURCE[gas]).read_text(encoding="latin-1")
    assert text.count(TOLERANCE) == 1
    assert "?fy(ihold).gt.tolxy.or.fz(ihold).gt.tolxy.or." in text
    assert "?fy(ihold).lt.-tolxy.or.fz(ihold).lt.-tolxy) then" in text
    assert "1.0d-20.or." not in text


@pytest.mark.parametrize("gas", fortran.GASES)
def test_an_ion_with_its_farthest_atom_on_x_is_oriented(binaries, tmp_path, gas):
    atoms = [(100.0, 0.0, 0.0), *synthetic.globule(199)]
    mfj = synthetic.write(tmp_path / "onaxis.mfj", atoms, "farthest atom on +x")
    r = synthetic.run_until(binaries[gas], tmp_path / "run", mfj, " t*=", gas=gas, timeout=600)
    assert PROBLEM not in r.lines, r.lines[r.lines.index(PROBLEM):][:4]
    assert r.returncode is None, r.lines[-3:]  # stopped at t*, not ended
    assert any(s.startswith(" t*=") for s in r.lines)
