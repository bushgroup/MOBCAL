"""The regression gate: choline through the built binaries, compared with the 2012 references.

Each gas is built with the recorded recipe, run on ``fortran/Choline.mfj`` staged under the name
the reference echoes and at the seed it records, and compared in three tiers after the two
normalizations of ``mobcal.io.outfile``:

- **T1, deterministic lines.** Every line that no pattern in ``stochastic-lines.txt`` matches,
  character for character. An unlisted line must match, so a new output line fails here.
- **T2, cross sections.** Those the reference's SUMMARY block reports, within ``REL_TOL``.
- **T3, whole file.** Byte identity, gating on the platforms in ``strict-platforms.txt`` and
  reported as an expected failure elsewhere.

The runs go through the driver, ``mobcal.run.run_many``, from the session's ``pool`` fixture
(``conftest.py``): all the selected gases in one batch with one worker each, so a session that
asks for both gases waits for the longer one and not for their sum. Helium is minutes and runs
by default; nitrogen is about an hour and carries the ``nitrogen`` marker, deselected unless
asked for (``uv run pytest -m nitrogen``; ``-m ""`` for both).
"""

from __future__ import annotations

import difflib

import pytest

import gate
from mobcal.io.outfile import OutFile
from mobcal.run import Job, Result, run_one

REL_TOL = 1e-3
"""T2's relative tolerance on each reported cross section.

The cross sections are printed to five significant figures, so the last printed digit is worth
1e-4 relative at most (5.5402E+01: 2e-5). A platform that draws the same random stream and only
sums in another order would move a few chaotic trajectories out of 400,000, and the printed value
by a digit or two, well inside 1e-3; no platform has yet differed at all. The method's own
scatter is larger: the 2012 helium reference reports a per-cycle standard deviation of 0.92 %
over ten cycles, a standard error of 0.29 %; helium runs at three other seeds land 0.03 % to
0.27 % from the reference values, and nitrogen runs at two others 0.16 % and 0.19 % from its TM
value (this build, Windows, 2026-10-21; lab record, task 04). So T2 does not trip on rounding
and does trip on a gross change to a parameter, but it cannot be relied on to see a different
random stream; T1 carries the seed lines and T3 every digit, and those see it.
"""


@pytest.fixture(scope="module",
                params=["he", pytest.param("n2", marks=pytest.mark.nitrogen)])
def choline(request, pool) -> gate.GateRun:
    return pool.runs[request.param]


def _diff(a: list[str], b: list[str], n: int = 60) -> str:
    d = list(difflib.unified_diff(a, b, "reference", "this run", lineterm=""))
    return "\n".join(d[:n]) + (f"\n... {len(d) - n} more diff lines" if len(d) > n else "")


def test_t1_deterministic_lines(choline):
    patterns = gate.stochastic_patterns()
    ref = gate.deterministic(choline.ref.lines, patterns)
    new = gate.deterministic(choline.new.lines, patterns)
    assert new == ref, "deterministic lines differ:\n" + _diff(ref, new)


def test_t2_cross_sections(choline):
    ref, new = choline.ref.cross_sections, choline.new.cross_sections
    assert ref, "the reference reports no cross section, so T2 would check nothing"
    assert new.keys() == ref.keys(), f"reported {sorted(new)}, reference {sorted(ref)}"
    bad = {k: (ref[k], new[k]) for k in ref if abs(new[k] - ref[k]) > REL_TOL * abs(ref[k])}
    assert not bad, f"cross sections outside {REL_TOL:g} relative (reference, this run): {bad}"


def test_t3_whole_file(choline):
    if choline.new.text == choline.ref.text:
        return
    here = gate.platform_key()
    n = sum(1 for x in difflib.ndiff(choline.ref.lines, choline.new.lines) if x[:1] in "+-")
    if here not in gate.strict_platforms():
        pytest.xfail(f"{n} lines differ from the reference; T3 does not gate on {here}")
    pytest.fail(f"{n} lines differ from the reference on {here}, a strict platform. If this is "
                f"summation order and not physics, remove {here} from strict-platforms.txt in a "
                f"commit that says so.\n" + _diff(choline.ref.lines, choline.new.lines))


def test_an_undefined_element_is_reported_as_failed(pool, tmp_path):
    # Bromide, key 35, which neither element table defines: the program writes the header, the
    # refusal line and nothing else, and exits 0. The driver must report that as a failure.
    inp = tmp_path / "hbr.mfj"
    inp.write_text("HBr+\n1\n2\nang\ncalc\n1.0000\n 0.0 0.0 0.0 35 0.5\n 1.41 0.0 0.0 1 0.5\n",
                   encoding="latin-1", newline="\n")
    for gas in pool.binaries:
        r: Result = run_one(Job(inp, gas, 1, tmp_path), pool.launcher)
        assert not r.ok and r.returncode == 0, (gas, r)
        assert r.message == "no SUMMARY: type not defined for atom number  1", (gas, r.message)
        assert r.cross_sections == {} and r.conformers == []


def test_strict_platforms_are_known():
    assert gate.strict_platforms() <= set(gate.PLATFORMS)


def test_stochastic_patterns_spare_the_identifying_lines():
    # The seed, the input echo and the mass reach T1 whatever the list says.
    patterns = gate.stochastic_patterns()
    for name in gate.REFERENCE.values():
        ref = OutFile.read(gate.REFS / name)
        kept = gate.deterministic(ref.lines, patterns)
        for must in (" using RANLUX with seed integer = 5013489",
                     " input file name = Choline_pop.mfj               ",
                     " mass of ion = 1.0417E+02"):
            assert must in kept, (name, must)


def test_a_blank_line_goes_with_the_line_it_opens():
    patterns = gate.stochastic_patterns()
    lines = [" total number of points = 400000", "",
             " energy not conserved: e ratio = 9.6358E-01 v = 1.6836E+03 b = 2.9313E-10",
             " gst2 = 4.2253E+01 theta = 1.8793E+02 phi = 8.8605E+01 gamma = 3.5395E+02",
             "", " summary of mobility calculations"]
    assert gate.deterministic(lines, patterns) == [" total number of points = 400000", "",
                                                   " summary of mobility calculations"]


def test_t1_sees_what_it_should():
    # Against the helium reference itself: a new line, a moved potential minimum and a moved
    # b2max each change the deterministic lines; a moved cross section does not.
    patterns = gate.stochastic_patterns()
    ref = OutFile.read(gate.REFS / "Choline_He.out").lines
    kept = gate.deterministic(ref, patterns)

    def t1(lines):
        return gate.deterministic(lines, patterns) == kept

    def edit(old, new):
        assert old in ref, old
        return [new if x == old else x for x in ref]

    assert not t1(ref[:5] + [" a line the 2012 code never wrote"] + ref[5:])
    assert not t1(edit(" along x axis emax =-7.0434E-03eV rmax = 5.7631E+00A r00 = 5.4926E+00A",
                       " along x axis emax =-7.0435E-03eV rmax = 5.7631E+00A r00 = 5.4926E+00A"))
    assert not t1(edit("  2.3201E+00      1.4700E+01      1.1667E+01",
                       "  2.3201E+00      1.4800E+01      1.1707E+01"))
    assert t1(edit(" average TM cross section = 5.5402E+01",
                   " average TM cross section = 5.5403E+01"))
