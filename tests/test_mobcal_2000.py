"""The 2000 regression gate: the 2000 helium release's example, under the 2000 method.

The Jarrold group's 2000 helium release carries one example, ``a10A1.mfj`` (Ala10Na+, 50
coordinate sets of 104 atoms), and its output ``a10A1.out.orig`` at the seed of its run file,
kept as distributed under ``tests/data/mobcal-2000/``. The shipped helium program under the
shipped method ``2000-he`` (the 2000 element table, 298 K, 25 trajectories per block, RANLUX)
prints that output line for line but for the print changes made since: the atom count's width,
the q1st column and the ``mass of ion`` exponent letter (``test_reference.py``, against
``tests/reference/a10A1.out``). So does the run checked here, in the tiers of the 2012 gate
(``test_regression.py``), against ``tests/reference/a10A1.out``:

- **T1, deterministic lines**, every line no pattern in ``stochastic-lines.txt`` matches.
- **T2, cross sections**, the SUMMARY's PA, EHS and TM averages over the sets run and each
  set's own, within ``REL_TOL``.
- **T3, the whole output**, gating on the strict platforms.

The whole example is about 20 minutes as one process, so every session runs its first five
sets, which the program treats one after another on one random stream: a run of them prints
the lines of the whole run up to the sixth set (``gate.first_sets``), the set-count line apart,
and every line of the print changes falls in set 1. The whole example carries the ``mobcal2000``
marker and runs weekly, at every tag and on a dispatch that asks for the long gates
(``uv run pytest -m mobcal2000``).
"""

from __future__ import annotations

import difflib
import hashlib

import pytest

import gate
from mobcal.io.outfile import OutFile
from test_regression import REL_TOL


@pytest.fixture(scope="module", params=[
    gate.SLICE_2000, pytest.param(gate.A10A1_SETS, marks=pytest.mark.mobcal2000)])
def sets2000(request) -> int:
    return request.param


@pytest.fixture(scope="module")
def example(pool, sets2000) -> gate.GateRun:
    return pool.mobcal_2000[sets2000]


def _diff(a: list[str], b: list[str], n: int = 60) -> str:
    d = list(difflib.unified_diff(a, b, "reference", "this run", lineterm=""))
    return "\n".join(d[:n]) + (f"\n... {len(d) - n} more diff lines" if len(d) > n else "")


def test_the_run_says_how_many_sets_it_ran(example, sets2000):
    counts = [m.group(1) for s in example.new.lines if (m := gate.SET_COUNT.match(s))]
    assert counts == [str(sets2000)]
    assert len(example.new.conformers) == sets2000


def test_t1_deterministic_lines(example, sets2000):
    patterns = gate.stochastic_patterns()
    ref, new = gate.first_sets(example.ref.lines, example.new.lines, sets2000)
    ref, new = gate.deterministic(ref, patterns), gate.deterministic(new, patterns)
    assert new == ref, "deterministic lines differ:\n" + _diff(ref, new)


def test_t2_cross_sections(example, sets2000):
    pairs = list(zip(example.ref.conformers[:sets2000], example.new.conformers, strict=True))
    if sets2000 == gate.A10A1_SETS:
        pairs.append((example.ref.cross_sections, example.new.cross_sections))
    for i, (ref, new) in enumerate(pairs, 1):
        assert ref and new.keys() == ref.keys(), (i, sorted(ref), sorted(new))
        bad = {k: (ref[k], new[k]) for k in ref if abs(new[k] - ref[k]) > REL_TOL * abs(ref[k])}
        what = "the average" if i > sets2000 else f"set {i}"
        assert not bad, f"{what}: outside {REL_TOL:g} relative (reference, this run): {bad}"


def test_t3_whole_output(example, sets2000):
    ref, new = gate.first_sets(example.ref.lines, example.new.lines, sets2000)
    if new == ref:
        return
    here = gate.platform_key()
    n = sum(1 for x in difflib.ndiff(ref, new) if x[:1] in "+-")
    if here not in gate.strict_platforms():
        pytest.xfail(f"{n} lines differ from the reference; T3 does not gate on {here}")
    pytest.fail(f"{n} lines differ from the reference on {here}, a strict platform.\n"
                + _diff(ref, new))


RELEASE_SHA256 = {
    "a10A1.mfj": "6df8bde863d775cfaf42581ffb81f54a176494854394cb06e5358b6a51d206ed",
    "a10A1.out.orig": "dd09d9f346e2321034476c86d6aa4bcd10f815e854019227f991cff247955836",
    "mobcal.run": "949d1e433eb33ad2d36e611517fe34ef4723f3463c32bc7eda6127242a09fc00",
}
"""The pins of bushgroup/MOBCAL-2000 v1.0, as its README lists them."""


def test_the_example_files_are_the_release_files():
    files = {p.name for p in gate.MOBCAL_2000.iterdir()} - {"README.md"}
    assert files == set(RELEASE_SHA256)
    for name, pin in RELEASE_SHA256.items():
        assert hashlib.sha256((gate.MOBCAL_2000 / name).read_bytes()).hexdigest() == pin, name


def test_the_run_file_names_the_reference_seed():
    name, out, seed = (gate.MOBCAL_2000 / "mobcal.run").read_text(encoding="ascii").split()
    ref = OutFile.read(gate.A10A1_ORIG)
    assert (name, out) == (gate.A10A1.name, "a10A1.out")
    assert int(seed) == ref.seed == OutFile.read(gate.A10A1_REF).seed
    assert ref.input_name == gate.A10A1.name


def test_a_slice_is_the_first_sets_of_the_example():
    whole = gate.A10A1.read_text(encoding="ascii").split("\n")
    part = gate.a10A1_sets(gate.SLICE_2000).split("\n")
    assert part[1] == str(gate.SLICE_2000) and whole[1] == str(gate.A10A1_SETS)
    body = part[2:-1]
    assert part[0] == whole[0] and part[-1] == "" and body == whole[2:2 + len(body)]
    assert body[-1].strip() == whole[2]  # each set ends with the atom count, the last included
    with pytest.raises(ValueError):
        gate.a10A1_sets(1)
