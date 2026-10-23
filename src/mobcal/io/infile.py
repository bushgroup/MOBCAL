"""``mobcal.in``, the run file the program reads from its working directory.

Three records, and an optional fourth: the input file name, the output file name, the random
seed, and ``W w`` for a calculation split across W processes. The two names are read with an
``a30`` edit descriptor, so a longer name is silently cut to 30 characters and the program then
opens a file that does not exist; the seed is a default integer. The program takes no arguments
and reads nothing else, so this file and the working directory are the whole interface, and the
driver writes one per run.

The seed reaches RANLUX through ``rluxgo``, which takes it as a positive default integer; the
2012 references were produced at 5013489, the seed the shipped ``mobcal.in`` carries. The seed
may be followed on its record by a word naming the generator, ``ranlux`` or ``philox``: the
2012 RANLUX, or Philox4x32-10, whose draws are addressed by index so that a split run seeks
to its blocks instead of drawing through the others. No word is ``ranlux``, and the program
refuses any other word before it calculates anything. The generator word is written only when
it is not the default, so a default ``InFile`` is the 2012 run file byte for byte.

The fourth record makes the run worker ``w`` of ``W``: it integrates the trajectory blocks
with ``(k - 1) mod W == w - 1``, draws the random stream through the others, and writes each
block it integrated to a file. ``w == 0`` is the combining run, which integrates nothing and
reads every block back. Without the record the program is the 2012 program, byte for byte.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

NAME = "mobcal.in"
FIELD_WIDTH = 30
MAX_SEED = 2**31 - 1
GENERATORS = ("ranlux", "philox")  # the words the program accepts on the seed record
DEFAULT_GENERATOR = "ranlux"  # what no word means: the 2012 generator


class InFileError(ValueError):
    pass


def check_name(name: str, what: str) -> None:
    if not name or name != name.strip() or "\n" in name or "\r" in name:
        raise InFileError(f"{what} {name!r}: empty, or begins or ends with whitespace")
    if len(name) > FIELD_WIDTH:
        raise InFileError(f"{what} {name!r} is {len(name)} characters; the program reads "
                          f"{FIELD_WIDTH} and would open a file that does not exist")


@dataclass(frozen=True)
class InFile:
    input_name: str
    output_name: str
    seed: int
    split: tuple[int, int] | None = None  # (W, w): worker w of W; w == 0 is the combining run
    generator: str = DEFAULT_GENERATOR  # the word on the seed record: ranlux or philox

    def __post_init__(self) -> None:
        check_name(self.input_name, "input file name")
        check_name(self.output_name, "output file name")
        if not isinstance(self.seed, int) or not 1 <= self.seed <= MAX_SEED:
            raise InFileError(f"seed {self.seed!r}: a positive integer up to {MAX_SEED}")
        if self.generator not in GENERATORS:
            raise InFileError(f"generator {self.generator!r}: one of {' or '.join(GENERATORS)}")
        if self.split is not None:
            try:
                total, me = self.split
                ok = isinstance(total, int) and isinstance(me, int) and 1 <= total and \
                    0 <= me <= total
            except (TypeError, ValueError):
                ok = False
            if not ok:
                raise InFileError(f"split {self.split!r}: (W, w) with W >= 1 and 0 <= w <= W")

    def text(self) -> str:
        word = "" if self.generator == DEFAULT_GENERATOR else f" {self.generator}"
        text = f"{self.input_name}\n{self.output_name}\n{self.seed}{word}\n"
        if self.split is not None:
            text += f"{self.split[0]} {self.split[1]}\n"
        return text

    def write(self, directory: Path) -> Path:
        """Write ``mobcal.in`` into ``directory`` (LF line endings on every platform)."""
        path = Path(directory) / NAME
        with open(path, "w", encoding="latin-1", newline="\n") as f:
            f.write(self.text())
        return path

    @classmethod
    def parse(cls, text: str) -> InFile:
        lines = text.splitlines()
        if len(lines) < 3:
            raise InFileError(f"{len(lines)} lines; the program reads three")
        words = lines[2].split()
        try:
            seed = int(words[0])
        except (IndexError, ValueError):
            raise InFileError(f"seed line {lines[2]!r} is not an integer") from None
        generator = words[1] if len(words) > 1 else DEFAULT_GENERATOR  # as the program reads it
        split = None
        rest = [s for s in lines[3:] if s.strip()]
        if rest:
            try:
                total, me = (int(x) for x in rest[0].split()[:2])
            except ValueError:
                raise InFileError(f"split record {rest[0]!r} is not two integers") from None
            split = (total, me)
        return cls(lines[0][:FIELD_WIDTH].rstrip(" "), lines[1][:FIELD_WIDTH].rstrip(" "), seed,
                   split, generator)

    @classmethod
    def read(cls, path: Path) -> InFile:
        with open(path, encoding="latin-1") as f:
            return cls.parse(f.read())
