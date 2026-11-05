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

Every other value the block prints has a property of its own, None where the block does not
print it (no SUMMARY, the other gas, or the other shape): ``program_version``, ``input_label``,
``temperature``, ``asymmetry_parameter`` (the one set's, or the AVGE row's mean; nitrogen with
several sets prints none), ``hard_sphere_trajectories`` (inum), ``maximum_reflections`` and
``minimum_reflections`` (several sets only), ``trajectory_parameters`` (sw1, sw2, dtsf1, dtsf2),
``itn``, ``inp``, ``imp``, ``total_points``, ``failed_trajectories`` (either label),
``tm_standard_deviation`` (percent, one set only), ``inverse_mobilities`` (the averages' lines
for one set, the AVGE row for several) and, per set, ``conformer_inverse_mobilities`` and
``conformer_asymmetry``; ``summary_lines`` is the block as printed. Each value is the printed
digits read as a number, never rounded or derived. The inverse mobilities are 1/K0 in V s m^-2
at z = 1 (``mconst`` carries one e). The ASYMP column is the same quantity as the single-set
line: the program prints ``asympp/10``, and the ``1P`` scale factor of the same format, which
carries into the ``f8.4`` that prints it, multiplies it by 10 again.

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
# Each column by the key a row's dict holds it under: a cross section by its method, an
# inverse mobility as "1/" and the method, and the asymmetry parameter, printed f8.4 last.
_TABLE_COLUMNS = {"PA CS": ("PA", "1/PA", "EHS", "1/EHS", "ASYMP"), "TM CS": ("TM", "1/TM")}
_TABLE_ROW = re.compile(r"^\s*(\d+|AVGE)((?:\s+-?\d\.\d+E[+-]\d\d)+)(\s+-?\d+\.\d+)?\s*$")
_SETS_LINE = " number of coordinate sets ="
_METHODS = ("PA", "EHS", "TM")
INVERSE_MOBILITY_LABELS = {
    "PA": "inverse average PA mobility",
    "EHS": "inverse average EHS mobility",
    "TM": "inverse average (second order) TM mobility",
}
_REFLECTIONS = re.compile(r"^ minimum and maximum number of reflections =\s*(\d+)\s+(\d+)\s*$")


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
    def summary_lines(self) -> list[str]:
        """The SUMMARY block as printed, from its ``SUMMARY`` line to the end; empty if none."""
        try:
            return self.lines[self.lines.index(SUMMARY_LINE):]
        except ValueError:
            return []

    @cached_property
    def summary(self) -> dict[str, str]:
        """Label to printed value for every pair after the SUMMARY line. Empty if there is none."""
        pairs = {}
        for line in self.summary_lines[1:]:
            for m in _PAIR.finditer(line):
                pairs[m.group(1)] = m.group(2)
        return pairs

    @cached_property
    def _tables(self) -> tuple[list[dict[str, float]], dict[str, float]]:
        """The per-set rows and the AVGE row of the multi-set SUMMARY tables, merged by method,
        every column under its ``_TABLE_COLUMNS`` key."""
        rows: dict[int, dict[str, float]] = {}
        avge: dict[str, float] = {}
        columns: tuple[str, ...] = ()
        for line in self.summary_lines[1:]:
            h = _TABLE_HEADER.match(line)
            if h:
                columns = _TABLE_COLUMNS[h.group(1)]
                continue
            r = _TABLE_ROW.match(line) if columns else None
            if not r:
                continue
            values = [float(v) for v in r.group(2).split()]
            if r.group(3):
                values.append(float(r.group(3)))
            named = dict(zip(columns, values, strict=False))
            if r.group(1) == "AVGE":
                avge.update(named)
                columns = ()
            else:
                rows.setdefault(int(r.group(1)), {}).update(named)
        return [rows[i] for i in sorted(rows)], avge

    @staticmethod
    def _pick(row: dict[str, float], prefix: str = "") -> dict[str, float]:
        """The methods' columns of a table row, ``prefix`` + method, keyed by method."""
        return {k: row[prefix + k] for k in _METHODS if prefix + k in row}

    def _lines_or_avge(self, labels: dict[str, str], prefix: str) -> dict[str, float]:
        single = {k: float(self.summary[label]) for k, label in labels.items()
                  if label in self.summary}
        return single or self._pick(self._tables[1], prefix)

    def _per_set(self, prefix: str, single: dict[str, float]) -> list[dict[str, float]]:
        rows = self._tables[0]
        if rows:
            return [self._pick(r, prefix) for r in rows]
        return [single] if single else []

    @cached_property
    def cross_sections(self) -> dict[str, float]:
        """The cross sections the SUMMARY block reports, in Å^2: some of ``PA``, ``EHS``, ``TM``.

        For one coordinate set, the ``average ... cross section`` lines; for several, the
        ``AVGE`` row of each table, the mean over sets.
        """
        return self._lines_or_avge(CROSS_SECTION_LABELS, "")

    @cached_property
    def conformers(self) -> list[dict[str, float]]:
        """One ``cross_sections``-shaped dict per coordinate set, in the file's order."""
        return self._per_set("", self.cross_sections)

    @cached_property
    def inverse_mobilities(self) -> dict[str, float]:
        """The inverse mobilities printed beside the cross sections, keyed as they are: 1/K0 in
        V s m^-2 at z = 1, the ``inverse average ...`` lines for one set, the AVGE row (the
        inverse of the mean mobility) for several."""
        return self._lines_or_avge(INVERSE_MOBILITY_LABELS, "1/")

    @cached_property
    def conformer_inverse_mobilities(self) -> list[dict[str, float]]:
        """One ``inverse_mobilities``-shaped dict per coordinate set, in the file's order."""
        return self._per_set("1/", self.inverse_mobilities)

    @property
    def asymmetry_parameter(self) -> float | None:
        """The structural asymmetry parameter: the one set's, or the AVGE row's mean over sets;
        None where the block prints none (nitrogen with several sets, or no SUMMARY)."""
        if self._tables[0]:
            return self._tables[1].get("ASYMP")
        return self._float("structural asymmetry parameter")

    @cached_property
    def conformer_asymmetry(self) -> list[float | None]:
        """Each coordinate set's asymmetry parameter, None for a set the block prints none for;
        empty without a SUMMARY."""
        rows = self._tables[0]
        if rows:
            return [r.get("ASYMP") for r in rows]
        return [self.asymmetry_parameter] if self.ok else []

    def _float(self, label: str) -> float | None:
        v = self.summary.get(label)
        return float(v) if v is not None else None

    def _int(self, label: str) -> int | None:
        v = self.summary.get(label)
        return int(v) if v is not None else None

    @property
    def program_version(self) -> str | None:
        return self.summary.get("program version")

    @property
    def input_label(self) -> str | None:
        """The input's label as the program echoes it, an a30 field with its trailing blanks
        dropped (a label may hold blanks, which ``summary`` would cut at)."""
        prefix = " input file label = "
        for line in self.summary_lines[1:]:
            if line.startswith(prefix):
                return line[len(prefix):].rstrip()
        return None

    @property
    def temperature(self) -> float | None:
        """The temperature the SUMMARY prints, in K."""
        return self._float("temperature")

    @property
    def hard_sphere_trajectories(self) -> int | None:
        """inum, the trajectories of the MOBIL4 pass (helium only)."""
        return self._int("number of Monte Carlo trajectories")

    @cached_property
    def _reflections(self) -> tuple[int, int] | None:
        for line in self.summary_lines[1:]:
            m = _REFLECTIONS.match(line)
            if m:
                return int(m.group(1)), int(m.group(2))
        return None

    @property
    def maximum_reflections(self) -> int | None:
        """The most reflections a MOBIL4 trajectory met, over the one set or over every set."""
        single = self._int("maximum number of reflections encountered")
        if single is not None:
            return single
        return self._reflections[1] if self._reflections else None

    @property
    def minimum_reflections(self) -> int | None:
        """The least of the sets' maxima, printed for several sets only."""
        return self._reflections[0] if self._reflections else None

    @property
    def trajectory_parameters(self) -> dict[str, float] | None:
        """sw1, sw2, dtsf1 and dtsf2 as printed; None without the MOBIL2 block."""
        keys = ("sw1", "sw2", "dtsf1", "dtsf2")
        if not all(k in self.summary for k in keys):
            return None
        return {k: float(self.summary[k]) for k in keys}

    @property
    def itn(self) -> int | None:
        return self._int("number of complete cycles (itn)")

    @property
    def inp(self) -> int | None:
        return self._int("number of velocity points (inp)")

    @property
    def imp(self) -> int | None:
        return self._int("number of random points (imp)")

    @property
    def total_points(self) -> int | None:
        """itn * inp * imp as the program prints it: the trajectory method's trajectories."""
        return self._int("total number of points")

    @property
    def failed_trajectories(self) -> int | None:
        """The trajectories the program counted as failed: ``number of failed trajectories``
        for one set, ``total number of failed trajectories`` for several."""
        single = self._int("number of failed trajectories")
        return single if single is not None else self._int("total number of failed trajectories")

    @property
    def tm_standard_deviation(self) -> float | None:
        """The standard deviation of the cycles' Ω*(1,1) in percent of their mean, printed for
        one coordinate set only."""
        return self._float("standard deviation (percent)")

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
