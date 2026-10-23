"""The Philox4x32-10 generator the programs can draw from, held to Random123 and pinned.

``fortran/mobcal_rng.inc`` is the generator ``xrand`` uses when the seed record of ``mobcal.in``
carries the word ``philox``. Three things are held here. The block function reproduces the
Random123 library's known-answer vectors, through ``rngprobe.f`` compiled with the include
under the recorded flags, and so does the Python reference ``philox.py``. The program's mapping
from draw index to double is the reference's, bit for bit: the first ten uniforms at the 2012
seed, and the draw after a seek of a thousand, which is what the split relies on. And the first
ten at the 2012 seed are pinned here as patterns, so that a change to the mapping is a change
to this file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import philox
from mobcal import fortran
from mobcal.io.infile import MAX_SEED

RNGPROBE = Path(__file__).resolve().parent / "rngprobe.f"
SEED = 5013489  # the 2012 seed

# The first ten uniforms the program draws at the 2012 seed under Philox, as 64-bit patterns.
FIRST_TEN = [
    "3FE01A36DD66D3C1", "3FD1030A94D4548E", "3FD40B9E820184D2", "3FEA2D492B5F37BF",
    "3FE52196E0D71C65", "3FDCE72DE5C69C0A", "3FE3E73407C22FA5", "3FE403FA484F0DDF",
    "3F9D1C56F8B290E0", "3FCE06C0DFEB5C2C",
]
SKIP = 1000


# --- the Python reference ----------------------------------------------------------------------

def test_the_reference_reproduces_the_random123_vectors():
    for counter, key, out in philox.KNOWN_ANSWERS:
        assert philox.philox4x32(counter, key) == out


def test_the_reference_pins_the_first_ten_uniforms_at_the_2012_seed():
    assert [philox.bits(philox.uniform(SEED, n)) for n in range(1, 11)] == FIRST_TEN


@pytest.mark.parametrize("seed", [1, SEED, MAX_SEED])
def test_a_uniform_is_an_odd_multiple_of_2_to_the_minus_53_and_never_0_or_1(seed):
    for n in range(1, 2001):
        u = philox.uniform(seed, n)
        assert 0.0 < u < 1.0
        k = u * 2**53
        assert k == int(k) and int(k) % 2 == 1, (n, u)


def test_consecutive_draws_share_a_block_in_pairs():
    # Draws 1 and 2 are words (0, 1) and (2, 3) of counter block 0; draws 3 and 4 of block 1.
    r0 = philox.philox4x32((0, 0, 0, 0), (SEED, 0))
    r1 = philox.philox4x32((1, 0, 0, 0), (SEED, 0))
    assert [philox.words(SEED, n) for n in (1, 2, 3, 4)] == [r0[:2], r0[2:], r1[:2], r1[2:]]


# --- the include, through the probe -----------------------------------------------------------

@pytest.fixture(scope="module")
def rngprobe(gfortran, tmp_path_factory) -> Path:
    """``rngprobe.f`` compiled with the pinned include under the recorded flags, no warnings."""
    d = tmp_path_factory.mktemp("rngprobe")
    exe = d / ("rngprobe.exe" if sys.platform == "win32" else "rngprobe")
    cmd = [gfortran, *fortran.flags(), "-I", str(fortran.FORTRAN_DIR), "-o", str(exe),
           str(RNGPROBE)]
    proc = subprocess.run(cmd, env=fortran._env(gfortran), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace")
    assert proc.returncode == 0, proc.stdout
    assert fortran.count_warnings(proc.stdout) == 0, proc.stdout
    return exe


def _probe(exe: Path, vectors, seed: int, n: int, skip: int) -> list[str]:
    records = [str(len(vectors))]
    records += [" ".join(str(w) for w in counter + key) for counter, key, _ in vectors]
    records.append(f"{seed} {n} {skip}")
    proc = subprocess.run([str(exe)], input="\n".join(records) + "\n", capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return [s.strip() for s in proc.stdout.splitlines() if s.strip()]


def test_the_include_reproduces_the_random123_vectors(rngprobe):
    lines = _probe(rngprobe, philox.KNOWN_ANSWERS, SEED, 0, 0)
    got = [tuple(int(w, 16) for w in s.split()) for s in lines[:3]]
    assert got == [out for _, _, out in philox.KNOWN_ANSWERS]


def test_the_include_draws_the_reference_uniforms_and_seeks(rngprobe):
    lines = _probe(rngprobe, [], SEED, 10, SKIP)
    assert lines[:10] == FIRST_TEN
    assert lines[10] == philox.bits(philox.uniform(SEED, 10 + SKIP + 1))


@pytest.mark.parametrize("seed", [1, 2, 96, MAX_SEED])
def test_the_include_agrees_with_the_reference_at_other_seeds(rngprobe, seed):
    lines = _probe(rngprobe, [], seed, 4, 399_999)
    want = [philox.bits(philox.uniform(seed, n)) for n in (1, 2, 3, 4, 400_004)]
    assert lines == want
