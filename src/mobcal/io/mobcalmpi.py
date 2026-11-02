"""The nine-column ``.mfj`` that MobCal-MPI reads, as an import source for an ion file.

MobCal-MPI's ``fcoord`` (2.1, ``MobCal_MPI.f``) reads a file that begins as the 2012 one does
and then departs from it:

    line 1   label                 a30
    line 2   coordinate sets       list-directed integer; MobCal-MPI reads the first set only
    line 3   atoms                 list-directed integer
    line 4   ang | au              a30
    line 5   equal | calc | none   a30
    line 6   a real                in 2.x the switch of the empirical high-field correction
                                   (on when > 0), never applied to the coordinates
    line 7   the run line          itn inp imp igas seed T_bath [T_eff,max [n_grid]]
    then     x y z mass charge alpha N A G, one line per atom, all nine in every mode

The fourth field is a real mass, read as given, never looked up; the last four are the MMFF94
van der Waals parameters of the atom's MMFF94 type, which the file does not name. This module
reads that layout and nothing else; ``mobcal.io.ion.from_mfj`` turns it into an ion file.

Each atom's element is named from its mass: the element of the shipped default tables whose
mass lies within ``MASS_TOLERANCE`` of it. The window holds an element's average mass (the 2012
tables') and its monoisotopic mass (what MobCal-MPI's ``mass.prm`` gives C, N, O and S) for
every element the tables hold; a mass in no element's window, or in two, is refused.

``detect`` says whether a text has this layout: line 7 carries six to eight fields of which
the first five are integers, and line 8 nine fields. A 2012 file's line 7 is an atom line,
whose coordinates are reals, and no 2012 input carries nine fields on an atom line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mobcal import parameters
from mobcal.io.mfj import CHARGE_MODES, MAX_ATOMS, UNITS, _a30, _integer, _real, _tokens

MASS_TOLERANCE = 0.25  # u; of the tables' elements Si differs most between the two, by 0.11
FIELDS = 9
RUN_LINE = ("itn", "inp", "imp", "igas", "seed", "T_bath", "T_eff,max", "n_grid")
GASES = ("he", "n2")  # whose default tables name an atom's element

_INTEGER = re.compile(r"[+-]?\d+")


class MobcalMpiError(ValueError):
    """A file this reader does not take as a MobCal-MPI input, with the line named."""


@dataclass(frozen=True)
class Atom:
    x: float
    y: float
    z: float
    mass: float
    charge: float
    alpha: float
    n: float
    a: float
    g: float


@dataclass(frozen=True)
class MobcalMpiMfj:
    label: str
    units: str
    charge_mode: str
    line6: str  # the token as read
    run_line: str  # line 7, stripped
    atoms: tuple[Atom, ...]

    @classmethod
    def parse(cls, text: str) -> MobcalMpiMfj:
        lines = text.splitlines()

        def line(i: int, what: str) -> str:
            if i >= len(lines):
                raise MobcalMpiError(f"line {i + 1}: file ends before the {what}")
            return lines[i]

        try:
            label = _a30(line(0, "label"))
            n_sets = _integer(line(1, "number of coordinate sets"), "number of coordinate sets",
                              2)
            n_atoms = _integer(line(2, "number of atoms"), "number of atoms", 3)
            units = _a30(line(3, "units line"))
            mode = _a30(line(4, "charge-mode line"))
            six = _tokens(line(5, "line 6"))
            if not six:
                raise MobcalMpiError("line 6: missing")
            _real(six[0], "line 6", 6)
            run = _tokens(line(6, "run line"))
        except ValueError as e:  # MfjError
            raise MobcalMpiError(str(e)) from None
        if n_sets != 1:
            raise MobcalMpiError(f"line 2: {n_sets} coordinate sets; MobCal-MPI reads one, and "
                                 "a nine-column file holds one")
        if not 1 <= n_atoms <= MAX_ATOMS:
            raise MobcalMpiError(f"line 3: {n_atoms} atoms; MOBCAL holds 1 to {MAX_ATOMS}")
        if units not in UNITS:
            raise MobcalMpiError(f"line 4: units {units!r}; one of {', '.join(UNITS)}")
        if mode not in CHARGE_MODES:
            raise MobcalMpiError(f"line 5: charge mode {mode!r}; one of "
                                 f"{', '.join(CHARGE_MODES)}")
        if not _is_run_line(run):
            raise MobcalMpiError(f"line 7: {lines[6].strip()!r} is not a run line ("
                                 f"{' '.join(RUN_LINE[:6])}, then optionally "
                                 f"{' '.join(RUN_LINE[6:])})")
        atoms = []
        for a in range(n_atoms):
            i = 7 + a
            t = _tokens(line(i, f"atom {a + 1}"))
            if len(t) != FIELDS:
                raise MobcalMpiError(f"line {i + 1}: {len(t)} fields; an atom line of a "
                                     f"MobCal-MPI input is x y z mass charge alpha N A G")
            try:
                atoms.append(Atom(*(_real(v, w, i + 1) for v, w in zip(
                    t, ("x", "y", "z", "mass", "charge", "alpha", "N", "A", "G"), strict=True))))
            except ValueError as e:
                raise MobcalMpiError(str(e)) from None
        if any(s.strip() for s in lines[7 + n_atoms:]):
            raise MobcalMpiError(f"line {8 + n_atoms}: more lines follow the {n_atoms} atoms")
        return cls(label, units, mode, six[0], " ".join(run), tuple(atoms))

    def symbols(self) -> tuple[str, ...]:
        """Each atom's element, named from its mass. Raises MobcalMpiError."""
        known = element_masses()
        out = []
        for i, a in enumerate(self.atoms):
            near = [s for s, m in known.items() if abs(a.mass - m) <= MASS_TOLERANCE]
            if len(near) != 1:
                which = (f"is within {MASS_TOLERANCE} u of {' and '.join(near)}" if near else
                         f"is within {MASS_TOLERANCE} u of no element of the shipped tables, "
                         "which hold " + ", ".join(f"{s} {m:g}" for s, m in known.items()))
                raise MobcalMpiError(f"atom {i + 1}: mass {a.mass:g} u {which}")
            out.append(near[0])
        return tuple(out)


def detect(text: str) -> bool:
    """The text has MobCal-MPI's layout: a run line at line 7 and nine fields on line 8."""
    lines = text.splitlines()
    return (len(lines) > 7 and _is_run_line(_tokens(lines[6]))
            and len(_tokens(lines[7])) == FIELDS)


def element_masses() -> dict[str, float]:
    """Each element of the shipped default tables and its mass there (they agree), lightest
    first."""
    found: dict[str, float] = {}
    for gas in GASES:
        for e in parameters.shipped(gas).elements:
            found.setdefault(e.symbol, float(e.mass.lower().replace("d", "e")))
    return dict(sorted(found.items(), key=lambda kv: kv[1]))


def _is_run_line(tokens: list[str]) -> bool:
    return 6 <= len(tokens) <= len(RUN_LINE) and all(_INTEGER.fullmatch(t) for t in tokens[:5])
