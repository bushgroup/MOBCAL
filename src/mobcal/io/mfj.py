"""The ``.mfj`` input file, read the way the 2012 program reads it.

``fcoord`` serves the first coordinate set and ``ncoord`` every set after it, and this module
follows those two subroutines line for line rather than describing a format of its own. There is
no version number and no comment syntax; every line means something by position:

    line 1   label                 a30: the first 30 characters, leading blanks kept
    line 2   coordinate sets       list-directed integer
    line 3   atoms per set         list-directed integer
    line 4   ang | au              a30, compared with blank padding, so a leading blank refuses
    line 5   equal | calc | none   a30, the same
    line 6   correction factor     list-directed real, applied to every centred coordinate
    then     x y z key [charge]    one line per atom; the charge is read in ``calc`` mode only
    then     one discarded line, then the next set's atoms, for each further set

The fourth field is an integer key, not a mass: the program rounds it (``nint``) and looks it up
in its element table, and the table's mass is what the ion weighs from then on. The key is
recorded here and not validated. The package has no element table of its own, and an undefined
key is a refusal the program prints (``type not defined for atom number``), which the driver
reports as a failed run.

What this reader refuses, before a binary is launched: an atom count above 1,000 or a set count
above 100 (``parameter (len=1000)`` and the main program's ``dimension tmc(100)``, which the
2012 code reads into without a check), a unit or charge mode the program would stop on, a
missing or short atom line, and a file that ends before its last set. Nothing about charge or
geometry is checked; the program's own checks (``masses do not add up``) stand.

Two points where the nitrogen source differs from the helium source, both in ``fcoord`` and
neither in ``ncoord``: ``mobcal_N2.f`` reads five fields per atom of the first set whatever the
charge mode, so a four-column file in ``equal`` or ``none`` mode fails its first read; and its
``equal`` mode divides the sum of the charge column evenly instead of assigning 1/N. The safe
file carries five columns on every line with charges that sum to the intended net charge.
``Mfj.has_charge_column`` says whether a file does.

One divergence from the program: a list-directed read that finds too few values on a line
continues onto the next, and this reader refuses instead. No shipped input relies on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

MAX_ATOMS = 1000
MAX_SETS = 100
UNITS = ("ang", "au")
CHARGE_MODES = ("equal", "calc", "none")
FIELD_WIDTH = 30  # the a30 edit descriptor

_SEPARATORS = re.compile(r"[\s,]+")
_D_EXPONENT = re.compile(r"(?<=[\d.])[dD](?=[+-]?\d)")


class MfjError(ValueError):
    """The file is not one the 2012 program would read to the end."""


@dataclass(frozen=True)
class Atom:
    x: float
    y: float
    z: float
    key: int  # the integer the program looks up; nint of the fourth field
    charge: float | None  # the fifth field when the file carries one, read or not


def _a30(line: str) -> str:
    """What an ``a30`` read leaves of a line: the first 30 characters, trailing blanks dropped.

    Fortran compares strings with the shorter one blank-padded, so trailing blanks never
    matter and leading ones always do.
    """
    return line[:FIELD_WIDTH].rstrip(" ")


def _tokens(line: str) -> list[str]:
    return [t for t in _SEPARATORS.split(line.strip()) if t]


def _real(token: str, what: str, lineno: int) -> float:
    try:
        return float(_D_EXPONENT.sub("e", token))
    except ValueError:
        raise MfjError(f"line {lineno}: {what} is not a number: {token!r}") from None


def _integer(line: str, what: str, lineno: int) -> int:
    tokens = _tokens(line)
    if not tokens:
        raise MfjError(f"line {lineno}: {what} is missing")
    try:
        return int(tokens[0])
    except ValueError:
        raise MfjError(f"line {lineno}: {what} is not an integer: {tokens[0]!r}") from None


@dataclass(frozen=True)
class Mfj:
    label: str
    units: str
    charge_mode: str
    correct: float
    sets: tuple[tuple[Atom, ...], ...]

    @classmethod
    def read(cls, path: Path | str) -> Mfj:
        path = Path(path)
        with open(path, encoding="latin-1") as f:
            return cls.parse(f.read())

    @classmethod
    def parse(cls, text: str) -> Mfj:
        lines = text.splitlines()

        def line(i: int, what: str) -> str:
            if i >= len(lines):
                raise MfjError(f"line {i + 1}: file ends before the {what}")
            return lines[i]

        label = _a30(line(0, "label"))
        n_sets = _integer(line(1, "number of coordinate sets"), "number of coordinate sets", 2)
        n_atoms = _integer(line(2, "number of atoms"), "number of atoms", 3)
        units = _a30(line(3, "units line"))
        mode = _a30(line(4, "charge-mode line"))
        tokens = _tokens(line(5, "correction factor"))
        if not tokens:
            raise MfjError("line 6: correction factor is missing")
        correct = _real(tokens[0], "correction factor", 6)

        if not 1 <= n_sets <= MAX_SETS:
            raise MfjError(f"line 2: {n_sets} coordinate sets; the program holds 1 to {MAX_SETS}")
        if not 1 <= n_atoms <= MAX_ATOMS:
            raise MfjError(f"line 3: {n_atoms} atoms; the program holds 1 to {MAX_ATOMS}")
        if units not in UNITS:
            raise MfjError(f"line 4: units {units!r}; the program stops unless it is exactly "
                           f"{' or '.join(UNITS)} (a leading blank counts)")
        if mode not in CHARGE_MODES:
            raise MfjError(f"line 5: charge mode {mode!r}; the program stops unless it is "
                           f"exactly {', '.join(CHARGE_MODES)} (a leading blank counts)")

        sets: list[tuple[Atom, ...]] = []
        i = 6
        for k in range(1, n_sets + 1):
            if k > 1:
                line(i, f"separator before coordinate set {k}")  # read and discarded
                i += 1
            atoms = []
            for a in range(1, n_atoms + 1):
                raw = line(i, f"atom {a} of coordinate set {k}")
                atoms.append(_atom(raw, i + 1, mode))
                i += 1
            sets.append(tuple(atoms))
        return cls(label, units, mode, correct, tuple(sets))

    @property
    def coordinate_sets(self) -> int:
        return len(self.sets)

    @property
    def atoms(self) -> int:
        return len(self.sets[0])

    @cached_property
    def keys(self) -> tuple[int, ...]:
        """The distinct element keys, ascending."""
        return tuple(sorted({a.key for s in self.sets for a in s}))

    @property
    def has_charge_column(self) -> bool:
        """Every atom line carries a fifth field, which the nitrogen source needs in every mode."""
        return all(a.charge is not None for s in self.sets for a in s)

    def net_charge(self, index: int = 0) -> float | None:
        """The sum of the charge column of one set, or None where the column is absent."""
        charges = [a.charge for a in self.sets[index]]
        return None if any(c is None for c in charges) else sum(charges)  # type: ignore[arg-type]


def _atom(raw: str, lineno: int, mode: str) -> Atom:
    tokens = _tokens(raw)
    need = 5 if mode == "calc" else 4
    if len(tokens) < need:
        raise MfjError(f"line {lineno}: {len(tokens)} fields on an atom line; "
                       f"{need} are read in {mode} mode")
    x, y, z = (_real(t, f"coordinate {n}", lineno) for t, n in zip(tokens[:3], "xyz",
                                                                    strict=True))
    key = round(_real(tokens[3], "element key", lineno))
    charge = _real(tokens[4], "charge", lineno) if len(tokens) >= 5 else None
    return Atom(x, y, z, key, charge)
