"""``mobcal.in``, the run file the program reads from its working directory.

Three records, and an optional fourth: the input file name, the output file name, the random
seed, and ``W w`` for a calculation split across W processes. The two names are read with an
``a30`` edit descriptor, so a longer name is silently cut to 30 characters and the program then
opens a file that does not exist; the seed is a default integer. The program takes no arguments
and reads nothing else, so this file and the working directory are the whole interface, and the
driver writes one per run.

The seed reaches RANLUX through ``rluxgo``, which takes it as a positive default integer; the
2012 references were produced at 5013489, the seed the shipped ``mobcal.in`` carries.

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

    def __post_init__(self) -> None:
        check_name(self.input_name, "input file name")
        check_name(self.output_name, "output file name")
        if not isinstance(self.seed, int) or not 1 <= self.seed <= MAX_SEED:
            raise InFileError(f"seed {self.seed!r}: a positive integer up to {MAX_SEED}")
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
        text = f"{self.input_name}\n{self.output_name}\n{self.seed}\n"
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
        try:
            seed = int(lines[2].split()[0])
        except (IndexError, ValueError):
            raise InFileError(f"seed line {lines[2]!r} is not an integer") from None
        split = None
        rest = [s for s in lines[3:] if s.strip()]
        if rest:
            try:
                total, me = (int(x) for x in rest[0].split()[:2])
            except ValueError:
                raise InFileError(f"split record {rest[0]!r} is not two integers") from None
            split = (total, me)
        return cls(lines[0][:FIELD_WIDTH].rstrip(" "), lines[1][:FIELD_WIDTH].rstrip(" "), seed,
                   split)

    @classmethod
    def read(cls, path: Path) -> InFile:
        with open(path, encoding="latin-1") as f:
            return cls.parse(f.read())
