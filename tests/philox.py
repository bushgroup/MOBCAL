"""Philox4x32-10 in Python: the oracle for ``fortran/mobcal_rng.inc``.

The counter-based generator of Salmon, Moraes, Dror and Shaw ("Parallel Random Numbers: As
Easy as 1, 2, 3", SC 2011), as the Random123 library defines it: four 32-bit counter words and
two 32-bit key words go through ten rounds, each two 32 x 32-bit multiplications, two xors and
a bump of the key (multipliers D2511F53 and CD9E8D57, bumps 9E3779B9 and BB67AE85, in hex).
``philox4x32`` is that block function, held here to the library's known-answer vectors.

``uniform`` is the program's mapping from a draw index to a double, the one the include
implements and ``test_rng.py`` pins: draw ``n`` (from 1) is counter block ``(n - 1) // 2``,
counter words ``((n - 1) // 2, 0, 0, 0)`` under the key ``(seed, 0)``, output words 0 and 1
when ``n`` is odd and 2 and 3 when it is even; the uniform takes the first word and the top 20
bits of the second, 52 bits, plus a half: ``(k + 1/2) / 2**52``, an odd multiple of ``2**-53``
in ``[2**-53, 1 - 2**-53]``, exact in a double and never 0 or 1.
"""

from __future__ import annotations

import struct

MASK = 0xFFFFFFFF
MULTIPLIERS = (0xD2511F53, 0xCD9E8D57)
BUMPS = (0x9E3779B9, 0xBB67AE85)
ROUNDS = 10

# Random123's tests/kat_vectors (DEShawResearch/random123, the file as of commit
# d8a0c25e49992685c0b9d91b553c1d04f81b6b4b): the three philox4x32 vectors at ten rounds, as
# (counter words, key words, output words), copied from the file.
KNOWN_ANSWERS = [
    ((0x00000000, 0x00000000, 0x00000000, 0x00000000), (0x00000000, 0x00000000),
     (0x6627E8D5, 0xE169C58D, 0xBC57AC4C, 0x9B00DBD8)),
    ((0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF), (0xFFFFFFFF, 0xFFFFFFFF),
     (0x408F276D, 0x41C83B0E, 0xA20BC7C6, 0x6D5451FD)),
    ((0x243F6A88, 0x85A308D3, 0x13198A2E, 0x03707344), (0xA4093822, 0x299F31D0),
     (0xD16CFE09, 0x94FDCCEB, 0x5001E420, 0x24126EA1)),
]


def philox4x32(counter: tuple[int, int, int, int], key: tuple[int, int],
               rounds: int = ROUNDS) -> tuple[int, int, int, int]:
    """The Philox4x32 block function: four output words for four counter and two key words."""
    c0, c1, c2, c3 = counter
    k0, k1 = key
    m0, m1 = MULTIPLIERS
    for r in range(rounds):
        if r:
            k0 = (k0 + BUMPS[0]) & MASK
            k1 = (k1 + BUMPS[1]) & MASK
        p0 = m0 * c0
        p1 = m1 * c2
        c0, c1, c2, c3 = (p1 >> 32) ^ c1 ^ k0, p1 & MASK, (p0 >> 32) ^ c3 ^ k1, p0 & MASK
    return c0, c1, c2, c3


def words(seed: int, n: int) -> tuple[int, int]:
    """The two 32-bit words draw ``n`` (from 1) at ``seed`` is made from."""
    m = n - 1
    r = philox4x32((m // 2, 0, 0, 0), (seed & MASK, 0))
    return r[2 * (m % 2)], r[2 * (m % 2) + 1]


def uniform(seed: int, n: int) -> float:
    """Draw ``n`` (from 1) at ``seed``, as the program's ``xrand`` returns it at Philox."""
    hi, lo = words(seed, n)
    k = (hi << 20) | (lo >> 12)
    return (k + 0.5) / 2**52


def bits(u: float) -> str:
    """A double as its 64-bit pattern, sixteen upper-case hex digits (Fortran's ``z16.16``)."""
    return f"{struct.unpack('>Q', struct.pack('>d', u))[0]:016X}"
