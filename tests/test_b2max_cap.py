"""The b2max search runs to 10,000 steps of ro^2, not 500; a run the 2012 cap passed is unchanged.

MOBIL2 finds b2max at each velocity point by walking b^2 upward in steps of ro^2 (ro = 3.043 Å)
until five deflections in a row are under ``cmin``. The 2012 program stopped with ``ibst greater
than 500`` past 500 steps, b = 68 Å, and dimensioned ``cosx(0:500)`` for it. That is a charge
limit as much as a size limit: b2max at the slowest point grows with the net charge (the
ion-induced-dipole tail of the potential), so choline's 21 atoms with every charge times 13 are
refused in nitrogen at 301 K. The cap is now the parameter ``ibstmx`` = 10,000 (b = 304 Å), which
also dimensions ``cosx``, and the refusal prints it.

A run the 2012 cap passed executes the same statements as before, the comparison with the cap
included, so its output is unchanged; the choline gates hold that for the 2012 ion, and here a
copy of the sources with ``ibstmx`` set back to 500 prints, for choline at 12+ in nitrogen, the
last charge the 2012 cap passed, exactly what the shipped program prints. At 13+ the copy stops
on the old cap and the shipped program prints the b2max table and finishes. The runs use one
trajectory per velocity point and cycle and a short projection pass, so the search is what they
pay for, a little under a minute each in nitrogen on a workstation; the four run at once.
"""

from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mobcal import fortran, parameters, settings
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile

CAP = 10000
OLD_CAP = 500
PARAMETER = f"      parameter (ibstmx={CAP})"
REFUSAL = "ibst greater than{:6d}"
TABLE = "b2max/ro2"


def _scaled_choline(z: int) -> str:
    """``fortran/Choline.mfj`` with every charge of its ``calc`` column multiplied by ``z``."""
    lines = (fortran.FORTRAN_DIR / "Choline.mfj").read_text(encoding="latin-1").splitlines()
    rows = []
    for s in lines[6:]:
        f = s.split()
        if f:
            rows.append(f" {f[0]} {f[1]} {f[2]} {f[3]} {float(f[4]) * z:.8f}")
    return "\n".join([f"Choline x{z}", *lines[1:6], *rows]) + "\n"


def _run(binary: Path, d: Path, z: int) -> tuple[int, list[str]]:
    d.mkdir(parents=True)
    (d / "ion.mfj").write_text(_scaled_choline(z), encoding="latin-1", newline="\n")
    InFile("ion.mfj", "out.txt", 5013489, None, "philox").write(d)
    parameters.shipped("n2").render(d)
    settings.resolve(imp=1, itn=1, inum=1000).render(d)
    proc = subprocess.run([str(binary)], cwd=d, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=1800)
    return proc.returncode, OutFile.read(d / "out.txt").lines


def _last(lines: list[str]) -> str:
    return next(s for s in reversed(lines) if s.strip()).strip()


def _slowest_b2max(lines: list[str]) -> float:
    i = next(i for i, s in enumerate(lines) if TABLE in s)
    return float(lines[i + 2].split()[1])


@pytest.mark.parametrize("gas", fortran.GASES)
def test_the_cap_is_one_parameter(gas):
    text = (fortran.FORTRAN_DIR / fortran.SOURCE[gas]).read_text(encoding="latin-1")
    for line in (PARAMETER, "      dimension q1st(100),q2st(100),cosx(0:ibstmx)",
                 "      if(ibst.gt.ibstmx) then", "      write(8,653) ibstmx",
                 "  653 format(1x,'ibst greater than',i6)"):
        assert text.count(line + "\n") == 1, line
    assert "cosx(0:500)" not in text and "ibst.gt.500" not in text


@pytest.fixture(scope="module")
def runs(gfortran, tmp_path_factory) -> dict[tuple[str, int], tuple[int, list[str]]]:
    """Choline at 12+ and 13+ in nitrogen through the shipped program and through a copy of the
    sources with the 2012 cap, all four at once."""
    src = tmp_path_factory.mktemp("cap500-src")
    for p in fortran.FORTRAN_DIR.glob("*.[fi]*"):
        shutil.copy(p, src / p.name)
    text = (src / fortran.SOURCE["n2"]).read_text(encoding="latin-1")
    assert text.count(PARAMETER) == 1
    (src / fortran.SOURCE["n2"]).write_text(
        text.replace(PARAMETER, f"      parameter (ibstmx={OLD_CAP})"), encoding="latin-1",
        newline="\n")
    old_dir = tmp_path_factory.mktemp("cap500-bin")
    old = old_dir / fortran.binary_name("n2")
    cmd = [gfortran, *fortran.flags(), "-o", str(old), str(src / fortran.SOURCE["n2"])]
    proc = subprocess.run(cmd, env=fortran._env(gfortran), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace")
    assert proc.returncode == 0 and fortran.count_warnings(proc.stdout) == 0, proc.stdout
    new = fortran.build("n2", tmp_path_factory.mktemp("cap-bin"), gfortran).binary
    work = tmp_path_factory.mktemp("cap-runs")
    cases = [(b, z) for b in ("shipped", "2012 cap") for z in (12, 13)]
    binaries = {"shipped": new, "2012 cap": old}
    with ThreadPoolExecutor(len(cases)) as pool:
        done = pool.map(lambda c: _run(binaries[c[0]], work / f"{c[0][:4]}-{c[1]}", c[1]), cases)
        return dict(zip(cases, done, strict=True))


def test_the_2012_cap_refuses_13_plus(runs):
    rc, lines = runs[("2012 cap", 13)]
    assert rc == 1 and _last(lines) == REFUSAL.format(OLD_CAP), lines[-3:]
    assert not any(TABLE in s for s in lines)


def test_the_shipped_cap_runs_13_plus(runs):
    rc, lines = runs[("shipped", 13)]
    assert rc == 0, lines[-3:]
    assert OLD_CAP - 5 < _slowest_b2max(lines) < CAP  # past the last step 2012 could pass
    assert not any(s.strip().startswith("ibst greater than") for s in lines)


def test_12_plus_prints_the_same_under_either_cap(runs):
    rc_new, new = runs[("shipped", 12)]
    rc_old, old = runs[("2012 cap", 12)]
    assert rc_new == rc_old == 0
    assert _slowest_b2max(new) < OLD_CAP - 5
    assert new == old
