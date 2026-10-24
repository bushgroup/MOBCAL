"""The block file a split calculation's worker writes for each block it integrated.

A block is one (cycle, velocity point) pair of ``imp`` trajectories in ``mobil2``: ``itn``
cycles by ``inp`` points, 400 blocks per coordinate set at the 2012 settings (``itn = 10``,
``inp = 40``, ``mobcal.settings.DEFAULTS``), indexed ``k = (ig - 1) * itn + ic``,
velocity-major. The random stream reaches the blocks cycle-major, but the shares are dealt by
this index so that a worker's blocks mix velocity points: a block's cost rises steeply at low
velocity, and dealing in stream order pinned each worker to fixed points whenever W divided the
40. A worker writes ``block-<set>-<k>.dat`` for each block it integrated, as one Fortran 77
unformatted sequential record: the set, the cycle, the point, the seed and the generator (1
RANLUX, 2 Philox4x32-10) as default integers; the five sampling counts ``imp itn inp inum
inor`` as default integers and the temperature as the REAL*8 the run read, the settings the
block was integrated under (the reader in the program checks all of these before it accepts
the block: a block drawn from another stream, or integrated with other settings, is not this
block); the block's two sums ``temp1`` and ``temp2`` as the REAL*8 they were accumulated in;
and the number of energy-conservation failures among its trajectories. gfortran frames the
record with a 4-byte length before and after, so the file is 76 bytes, little-endian on every
platform the package runs on.

The driver reads these for progress and never does arithmetic on them: the combination of the
blocks is done by the program itself, so that it is the serial calculation's own statements that
make the sums.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from mobcal.io.infile import DEFAULT_GENERATOR, GENERATORS
from mobcal.settings import DEFAULTS, Settings

CYCLES = DEFAULTS.itn  # itn, 2012
POINTS = DEFAULTS.inp  # inp, 2012
BLOCKS_PER_SET = CYCLES * POINTS  # at the 2012 settings; a run's is Settings.blocks_per_set

# length; set/cycle/point/seed/generator; imp/itn/inp/inum/inor; t; temp1/temp2; failures; length
_RECORD = struct.Struct("<i5i5id2di i")
PAYLOAD = _RECORD.size - 8
GENERATOR_CODE = {name: i + 1 for i, name in enumerate(GENERATORS)}  # i5 in the program


class BlockError(ValueError):
    pass


def block_name(coordinate_set: int, k: int) -> str:
    return f"block-{coordinate_set:03d}-{k:05d}.dat"


def owned(k: int, total: int, me: int) -> bool:
    """Whether block ``k`` is worker ``me``'s share of ``total`` (``me == 0`` owns none)."""
    return me > 0 and (k - 1) % total == me - 1


def expected_names(coordinate_sets: int, total: int, me: int,
                   blocks_per_set: int = BLOCKS_PER_SET) -> list[str]:
    """The block files worker ``me`` of ``total`` writes for an input with this many sets."""
    return [block_name(s, k) for s in range(1, coordinate_sets + 1)
            for k in range(1, blocks_per_set + 1) if owned(k, total, me)]


@dataclass(frozen=True)
class Block:
    coordinate_set: int
    cycle: int
    point: int
    seed: int
    temp1: float
    temp2: float
    failures: int
    generator: str = DEFAULT_GENERATOR
    settings: Settings = field(default=DEFAULTS)

    def __post_init__(self) -> None:
        if self.generator not in GENERATOR_CODE:
            raise BlockError(f"generator {self.generator!r}: one of {' or '.join(GENERATORS)}")

    @property
    def k(self) -> int:
        return (self.point - 1) * self.settings.itn + self.cycle

    @staticmethod
    def cycle_point(k: int, cycles: int = CYCLES) -> tuple[int, int]:
        """The (cycle, velocity point) of block ``k`` at ``cycles`` cycles per point."""
        return (k - 1) % cycles + 1, (k - 1) // cycles + 1

    @property
    def name(self) -> str:
        return block_name(self.coordinate_set, self.k)

    def write(self, directory: Path) -> Path:
        """Write the record as the program would (for the stand-in binary and for tests)."""
        s = self.settings
        path = Path(directory) / self.name
        path.write_bytes(_RECORD.pack(PAYLOAD, self.coordinate_set, self.cycle, self.point,
                                      self.seed, GENERATOR_CODE[self.generator],
                                      s.imp, s.itn, s.inp, s.inum, s.inor, s.temperature,
                                      self.temp1, self.temp2, self.failures, PAYLOAD))
        return path

    @classmethod
    def read(cls, path: Path) -> Block:
        data = Path(path).read_bytes()
        if len(data) != _RECORD.size:
            raise BlockError(f"{path}: {len(data)} bytes, not {_RECORD.size}")
        (head, s, c, p, seed, gen, imp, itn, inp, inum, inor, t, t1, t2, nf,
         tail) = _RECORD.unpack(data)
        if head != PAYLOAD or tail != PAYLOAD:
            raise BlockError(f"{path}: record markers {head}, {tail}; expected {PAYLOAD}")
        names = {code: name for name, code in GENERATOR_CODE.items()}
        if gen not in names:
            raise BlockError(f"{path}: generator code {gen}; expected one of {sorted(names)}")
        try:
            settings = Settings(t, imp, itn, inp, inum, inor)
        except ValueError as e:
            raise BlockError(f"{path}: {e}") from None
        return cls(s, c, p, seed, t1, t2, nf, names[gen], settings)
