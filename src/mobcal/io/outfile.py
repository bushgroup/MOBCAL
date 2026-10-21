"""The ``.out`` file the 2012 program writes: normalize it, and read its SUMMARY block.

Two normalizations make a gfortran output comparable with the 2012 g77 references, and they are
applied to the program's side only (the references are never edited):

1. **End-of-line CR.** gfortran's Windows runtime opens the output unit in text mode and writes
   CRLF. One CR is stripped at the end of each line and nowhere else: the filename fields are
   blank-padded to 30 columns by an ``a30`` edit descriptor, and those trailing blanks are
   content.
2. **The ``D`` exponent on the ``mass of ion`` line.** Format 604 is the only ``1pd`` edit
   descriptor in either source; g77 printed ``E`` there and gfortran prints ``D``, same digits.
   The letter is rewritten on that one line.

Nothing else is normalized. With both applied, the founding build reproduced the 2012 helium
reference byte for byte; with either removed it did not.

The SUMMARY block at the end of the file repeats the run's identifying parameters and its
results, one ``label = value`` pair or two per line. ``OutFile.summary`` maps each label to the
value as printed; ``OutFile.cross_sections`` holds the cross sections the run reports, in Å^2,
keyed ``PA``, ``EHS`` and ``TM``. The nitrogen code has no MOBIL4 path, so its outputs report
``TM`` only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

MASS_LINE = " mass of ion ="
SUMMARY_LINE = " SUMMARY"

# A Fortran exponent letter between a mantissa digit and a signed exponent: 1.0417D+02.
_D_EXPONENT = re.compile(r"(?<=\d)D(?=[+-]\d)")

# One "label = value" pair. Labels contain blanks and parentheses; values do not contain blanks.
_PAIR = re.compile(r"\s*([^=]*?)\s*=\s*(\S+)")

CROSS_SECTION_LABELS = {
    "PA": "average PA cross section",
    "EHS": "average EHS cross section",
    "TM": "average TM cross section",
}


def normalize(text: str) -> str:
    """The program's output with the two normalizations applied, and nothing else changed."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.endswith("\r"):
            line = line[:-1]
        if line.startswith(MASS_LINE):
            line = _D_EXPONENT.sub("E", line)
        lines[i] = line
    return "\n".join(lines)


def read_text(path: Path) -> str:
    """A file's contents exactly as stored: no newline translation, every byte one character."""
    with open(path, encoding="latin-1", newline="") as f:
        return f.read()


@dataclass(frozen=True)
class OutFile:
    text: str  # normalized

    @classmethod
    def read(cls, path: Path) -> OutFile:
        return cls(normalize(read_text(path)))

    @cached_property
    def lines(self) -> list[str]:
        return self.text.splitlines()

    @cached_property
    def summary(self) -> dict[str, str]:
        """Label to printed value for every pair after the SUMMARY line. Empty if there is none."""
        try:
            start = self.lines.index(SUMMARY_LINE)
        except ValueError:
            return {}
        pairs = {}
        for line in self.lines[start + 1:]:
            for m in _PAIR.finditer(line):
                pairs[m.group(1)] = m.group(2)
        return pairs

    @cached_property
    def cross_sections(self) -> dict[str, float]:
        """The cross sections the SUMMARY block reports, in Å^2: some of ``PA``, ``EHS``, ``TM``."""
        return {k: float(self.summary[label]) for k, label in CROSS_SECTION_LABELS.items()
                if label in self.summary}

    @property
    def input_name(self) -> str | None:
        return self.summary.get("input file name")

    @property
    def seed(self) -> int | None:
        s = self.summary.get("using RANLUX with seed integer")
        return int(s) if s is not None else None
