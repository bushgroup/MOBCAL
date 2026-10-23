"""The atom bound: an ion of exactly ``len`` atoms is read whole and computed with atom 1 intact.

``mobil4`` keeps the incidence vector of each projection trajectory in slot ``inatom+1`` of
``fx``, ``fy``, ``fz`` and rotates it with the atoms. The 2012 arrays were ``len`` long, so at
``inatom = len``, which the reader accepts, the slot was ``fy(1), fz(1), ox(1)`` of the common
block and the first atom was overwritten in the PA/EHS pass. ``fortran/mobcal_arrays.inc`` now
dimensions the three ``len+1``.

The observable: an ion at the bound whose first atom is an outlier along +x, and the same atoms
with the outlier last. They are one ion, so with atom 1 intact the two print the same lines from
MOBIL4's header to MOBIL2's ``t*`` (PA, EHS, the reflection orders, the orientation, the
potential scans); with atom 1 overwritten a different atom is lost in each and the PA cross
section falls by a third to a half (lab record, task 19: 91 of 114 lines differ at 1,000 atoms
with the 2012 layout). Each run is stopped at ``t*``, before the trajectories.

The PA/EHS pass is linear in the atom count, about a minute per 1,000 atoms on a workstation,
so at the shipped bound of 200,000 it is hours. Two tests, then:

- **Every session**: the order-swap pair on a binary built from a copy of the sources whose
  include sets ``len`` to 1,000, every other line the shipped code. A minute or two.
- **Weekly** (marker ``bound``): the shipped binary on a 200,000-atom ion, stopped once the
  reader has finished (the structural asymmetry line, a quarter of an hour): the count is
  echoed, nothing is refused, and the arrays at the bound are filled without a fault.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import synthetic
from mobcal import fortran
from mobcal.io.mfj import MAX_ATOMS

REBUILT = 1000
INCLUDE = "mobcal_arrays.inc"
_LEN = re.compile(r"^      parameter \(len=(\d+)\)$", re.M)


def _compile(gfortran: str, src: Path, out: Path) -> Path:
    exe = out / fortran.binary_name("he")
    cmd = [gfortran, *fortran.flags(), "-o", str(exe), str(src / fortran.SOURCE["he"])]
    proc = subprocess.run(cmd, env=fortran._env(gfortran), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace")
    assert proc.returncode == 0 and fortran.count_warnings(proc.stdout) == 0, proc.stdout
    return exe


def _pair(d: Path, n: int) -> dict[str, Path]:
    core = synthetic.globule(n - 1)
    outlier = (max(abs(x) for x, _, _ in core) + 8.0, 0.0, 0.0)
    return {"first": synthetic.write(d / "first.mfj", [outlier, *core], "outlier first"),
            "last": synthetic.write(d / "last.mfj", [*core, outlier], "outlier last")}


def _from_mobil4(lines: list[str]) -> list[str]:
    """MOBIL4's header to MOBIL2's ``t*`` line, inclusive. The program may have written past
    ``t*`` before it was stopped, by a different number of lines in each run."""
    i = next(i for i, s in enumerate(lines) if "mobility calculation by MOBIL4" in s)
    j = next(j for j, s in enumerate(lines) if s.startswith(" t*="))
    return lines[i:j + 1]


@pytest.fixture(scope="module")
def rebuilt(gfortran, tmp_path_factory) -> Path:
    """The helium binary with the include's bound set to ``REBUILT``, built from a copy."""
    src = tmp_path_factory.mktemp("rebuilt-src")
    for p in fortran.FORTRAN_DIR.glob("*.[fi]*"):
        shutil.copy(p, src / p.name)
    text, n = _LEN.subn(f"      parameter (len={REBUILT})", (src / INCLUDE).read_text())
    assert n == 1
    (src / INCLUDE).write_text(text, encoding="ascii", newline="\n")
    return _compile(gfortran, src, tmp_path_factory.mktemp("rebuilt-bin"))


def test_the_include_declares_the_bound_the_reader_mirrors():
    text = (fortran.FORTRAN_DIR / INCLUDE).read_text()
    assert [int(m) for m in _LEN.findall(text)] == [MAX_ATOMS]
    assert "fx(len+1),fy(len+1),fz(len+1)" in text


def test_atom_1_is_intact_at_the_bound(rebuilt, tmp_path):
    inputs = _pair(tmp_path, REBUILT)
    with ThreadPoolExecutor(2) as pool:
        runs = dict(zip(inputs, pool.map(
            lambda k: synthetic.run_until(rebuilt, tmp_path / k, inputs[k], " t*=",
                                          timeout=1800), inputs), strict=True))
    for k, r in runs.items():
        assert r.returncode is None, (k, r.lines[-3:])  # stopped at t*, not ended
        assert f" number of atoms ={REBUILT:7d}" in r.lines
    first, last = (_from_mobil4(runs[k].lines) for k in ("first", "last"))
    assert any(s.startswith(" average PA cross section") for s in first)
    assert first == last


@pytest.mark.bound
def test_an_ion_at_the_shipped_bound_is_read(gfortran, tmp_path):
    exe = _compile(gfortran, fortran.FORTRAN_DIR, tmp_path)
    mfj = synthetic.write(tmp_path / "bound.mfj", synthetic.globule(MAX_ATOMS), "at the bound")
    r = synthetic.run_until(exe, tmp_path / "run", mfj, " structural asymmetry parameter",
                            timeout=7200)
    assert r.returncode is None, r.lines[-3:]  # stopped there, not refused
    assert f" number of atoms ={MAX_ATOMS:7d}" in r.lines
    assert not any("exceeds" in s or "not defined" in s for s in r.lines)
