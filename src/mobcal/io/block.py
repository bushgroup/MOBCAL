"""The block file a split calculation's worker writes for each block it integrated.

A block is one (cycle, velocity point) pair of ``imp`` trajectories in ``mobil2``: at the
program's settings ``itn = 10`` cycles by ``inp = 40`` points, 400 blocks per coordinate set,
indexed ``k = (ic - 1) * inp + ig`` in the order the random stream reaches them. A worker
writes ``block-<set>-<k>.dat`` for each block it integrated, as one Fortran 77 unformatted
sequential record: the set, the cycle, the point and the seed as default integers (the reader in
the program checks all four before it accepts the block), the block's two sums ``temp1`` and
``temp2`` as the REAL*8 they were accumulated in, and the number of energy-conservation failures
among its trajectories. gfortran frames the record with a 4-byte length before and after, so
the file is 44 bytes, little-endian on every platform the package runs on.

The driver reads these for progress and never does arithmetic on them: the combination of the
blocks is done by the program itself, so that it is the serial calculation's own statements that
make the sums.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

CYCLES = 10  # itn
POINTS = 40  # inp
BLOCKS_PER_SET = CYCLES * POINTS

_RECORD = struct.Struct("<i4i2di i")  # length, set/cycle/point/seed, temp1/temp2, failures, length
PAYLOAD = _RECORD.size - 8


class BlockError(ValueError):
    pass


def block_name(coordinate_set: int, k: int) -> str:
    return f"block-{coordinate_set:03d}-{k:04d}.dat"


def owned(k: int, total: int, me: int) -> bool:
    """Whether block ``k`` is worker ``me``'s share of ``total`` (``me == 0`` owns none)."""
    return me > 0 and (k - 1) % total == me - 1


def expected_names(coordinate_sets: int, total: int, me: int) -> list[str]:
    """The block files worker ``me`` of ``total`` writes for an input with this many sets."""
    return [block_name(s, k) for s in range(1, coordinate_sets + 1)
            for k in range(1, BLOCKS_PER_SET + 1) if owned(k, total, me)]


@dataclass(frozen=True)
class Block:
    coordinate_set: int
    cycle: int
    point: int
    seed: int
    temp1: float
    temp2: float
    failures: int

    @property
    def k(self) -> int:
        return (self.cycle - 1) * POINTS + self.point

    @property
    def name(self) -> str:
        return block_name(self.coordinate_set, self.k)

    def write(self, directory: Path) -> Path:
        """Write the record as the program would (for the stand-in binary and for tests)."""
        path = Path(directory) / self.name
        path.write_bytes(_RECORD.pack(PAYLOAD, self.coordinate_set, self.cycle, self.point,
                                      self.seed, self.temp1, self.temp2, self.failures, PAYLOAD))
        return path

    @classmethod
    def read(cls, path: Path) -> Block:
        data = Path(path).read_bytes()
        if len(data) != _RECORD.size:
            raise BlockError(f"{path}: {len(data)} bytes, not {_RECORD.size}")
        head, s, c, p, seed, t1, t2, nf, tail = _RECORD.unpack(data)
        if head != PAYLOAD or tail != PAYLOAD:
            raise BlockError(f"{path}: record markers {head}, {tail}; expected {PAYLOAD}")
        return cls(s, c, p, seed, t1, t2, nf)
