"""Every refusal of the program exits 1, and the normal end exits 0.

The 2012 program ended every termination with a bare ``stop``, which exits 0, so a refusal and a
finished calculation looked the same to a caller. Each refusal is now ``stop 1``. The static test
reads both sources and requires one bare ``stop`` in each, the normal end, and ``stop 1`` at every
other. The rest drive the refusals that a small input reaches in well under a second, on the
binary itself and outside the driver, and require exit 1 with the refusal as the output's last
line. The refusals they cannot reach quickly (``masses do not add up`` in a second coordinate set,
``Problem orientating along x axis``, ``ibst greater than 500``) the static test covers; the
``ifail`` cap is driven in ``test_split.py``, and the normal end's exit 0 by the regression gate's
choline runs.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from mobcal import fortran
from mobcal.io.outfile import OutFile

_STOP = re.compile(r"\bstop\b(.*)$")

# Hydrogen bromide, two atoms. Bromine (key 35) is in neither gas's element table, but the units
# and the charge distribution are read and refused first.
_HBR = "HBr+\n1\n2\n{unit}\n{charge}\n1.0000\n 0 0 0 {key} 0.5\n 1.41 0 0 1 0.5\n"
_OK = {"unit": "ang", "charge": "calc", "key": 35}

# (input, fourth mobcal.in record or None, the output's last non-blank line, stripped)
REFUSALS = {
    "units": (_HBR.format(**{**_OK, "unit": "nm"}), None,
              "units not specified"),
    "charge": (_HBR.format(**{**_OK, "charge": "some"}), None,
               "charge distribution not specified"),
    "element": (_HBR.format(**_OK), None, "type not defined for atom number  1"),
    "split record": (_HBR.format(**_OK), "2 3",
                     "bad split record in mobcal.in:       2       3"),
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


@pytest.mark.parametrize("case", REFUSALS)
def test_a_refusal_exits_1(pool, tmp_path, case):
    text, split, last = REFUSALS[case]
    for gas, binary in pool.binaries.items():
        d = tmp_path / gas
        d.mkdir()
        (d / "in.mfj").write_text(text, encoding="latin-1", newline="\n")
        run = ["in.mfj", "out.txt", "1"] + ([split] if split else [])
        (d / "mobcal.in").write_text("\n".join(run) + "\n", encoding="latin-1", newline="\n")
        proc = subprocess.run([str(binary)], cwd=d, capture_output=True, timeout=60,
                              stdin=subprocess.DEVNULL)
        out = OutFile.read(d / "out.txt")
        assert proc.returncode == 1, (gas, proc.returncode, out.last_line)
        assert out.last_line == last and not out.ok, (gas, out.lines[-3:])
