"""The ``.out`` file the 2012 program writes: normalize it, and read its SUMMARY block.

One normalization makes a gfortran output comparable with the 2012 g77 references, and it is
applied to the program's side only (the references are never edited): **end-of-line CR.**
gfortran's Windows runtime opens the output unit in text mode and writes CRLF. One CR is stripped
at the end of each line and nowhere else: the filename fields are blank-padded to 30 columns by
an ``a30`` edit descriptor, and those trailing blanks are content.

Nothing else is normalized. There were two until format 604, the ``mass of ion`` line, was
changed from ``1pd`` to ``1pe`` (``fortran/README.md``, Changes): gfortran printed a ``D``
exponent there where g77 printed ``E``, and the letter was rewritten on that one line. The line
now reaches the comparison as printed, so a ``D`` there fails it.

The SUMMARY block at the end of the file repeats the run's identifying parameters and its
results, one ``label = value`` pair or two per line. ``OutFile.summary`` maps each label to the
value as printed; ``OutFile.cross_sections`` holds the cross sections the run reports, in Å^2,
keyed ``PA``, ``EHS`` and ``TM``. The nitrogen code has no MOBIL4 path, so its outputs report
``TM`` only. An input with several coordinate sets gets a different SUMMARY: a table per method
with one row per set and an ``AVGE`` row, and no ``average ... cross section`` lines.
``OutFile.conformers`` gives the per-set values in either case and ``cross_sections`` the
average, which for one set is the set itself.

The SUMMARY block is also the evidence that a run completed. The program exits 1 when it refuses
an input (``units not specified``, ``type not defined for atom number``, ``masses do not add
up``), the refusal being the last line the output file holds; the 2012 program exited 0 on every
termination, so the exit status alone was never relied on. ``OutFile.ok`` is whether the block
is present and ``OutFile.last_line`` is what to report when it is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

SUMMARY_LINE = " SUMMARY"

# One "label = value" pair. Labels contain blanks and parentheses; values do not contain blanks.
_PAIR = re.compile(r"\s*([^=]*?)\s*=\s*(\S+)")

CROSS_SECTION_LABELS = {
    "PA": "average PA cross section",
    "EHS": "average EHS cross section",
    "TM": "average TM cross section",
}

# The multi-set SUMMARY tables (formats 622-624 and 630-632): a header naming the columns, one
# row per set with the set index first, then an AVGE row. Cross sections are in Å^2 already.
_TABLE_HEADER = re.compile(r"^\s+set\s+(PA CS|TM CS)\b")
_TABLE_COLUMNS = {"PA CS": ("PA", None, "EHS"), "TM CS": ("TM",)}
_TABLE_ROW = re.compile(r"^\s*(\d+|AVGE)((?:\s+-?\d\.\d+E[+-]\d\d)+)")
_SETS_LINE = " number of coordinate sets ="


def normalize(text: str) -> str:
    """The program's output with one CR stripped at the end of each line, nothing else changed."""
    return "\n".join(s[:-1] if s.endswith("\r") else s for s in text.split("\n"))


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
    def _tables(self) -> tuple[list[dict[str, float]], dict[str, float]]:
        """The per-set rows and the AVGE row of the multi-set SUMMARY tables, merged by method."""
        try:
            start = self.lines.index(SUMMARY_LINE)
        except ValueError:
            return [], {}
        rows: dict[int, dict[str, float]] = {}
        avge: dict[str, float] = {}
        columns: tuple[str | None, ...] = ()
        for line in self.lines[start + 1:]:
            h = _TABLE_HEADER.match(line)
            if h:
                columns = _TABLE_COLUMNS[h.group(1)]
                continue
            r = _TABLE_ROW.match(line) if columns else None
            if not r:
                continue
            values = [float(v) for v in r.group(2).split()]
            named = {k: v for k, v in zip(columns, values, strict=False) if k is not None}
            if r.group(1) == "AVGE":
                avge.update(named)
                columns = ()
            else:
                rows.setdefault(int(r.group(1)), {}).update(named)
        return [rows[i] for i in sorted(rows)], avge

    @cached_property
    def cross_sections(self) -> dict[str, float]:
        """The cross sections the SUMMARY block reports, in Å^2: some of ``PA``, ``EHS``, ``TM``.

        For one coordinate set, the ``average ... cross section`` lines; for several, the
        ``AVGE`` row of each table, the mean over sets.
        """
        single = {k: float(self.summary[label]) for k, label in CROSS_SECTION_LABELS.items()
                  if label in self.summary}
        return single or dict(self._tables[1])

    @cached_property
    def conformers(self) -> list[dict[str, float]]:
        """One ``cross_sections``-shaped dict per coordinate set, in the file's order."""
        rows = self._tables[0]
        if rows:
            return rows
        return [self.cross_sections] if self.cross_sections else []

    @property
    def coordinate_sets(self) -> int | None:
        for line in self.lines:
            if line.startswith(_SETS_LINE):
                return int(line[len(_SETS_LINE):])
        return None

    @property
    def ok(self) -> bool:
        """Whether the run completed: the SUMMARY block is present."""
        return bool(self.summary)

    @property
    def last_line(self) -> str:
        """The last non-blank line: the refusal, when a run stopped without a SUMMARY."""
        for line in reversed(self.lines):
            if line.strip():
                return line.strip()
        return ""

    @property
    def input_name(self) -> str | None:
        return self.summary.get("input file name")

    @property
    def seed(self) -> int | None:
        s = self.summary.get("using RANLUX with seed integer")
        if s is None:
            s = self.summary.get("using Philox4x32-10 with seed integer")
        return int(s) if s is not None else None

    @property
    def generator(self) -> str | None:
        """``ranlux`` or ``philox``, from the SUMMARY's seed line; None without a SUMMARY."""
        if "using RANLUX with seed integer" in self.summary:
            return "ranlux"
        if "using Philox4x32-10 with seed integer" in self.summary:
            return "philox"
        return None
