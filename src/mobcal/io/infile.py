"""``mobcal.in``, the run file the 2012 program reads from its working directory.

Three records: the input file name, the output file name, the random seed. The two names are
read with an ``a30`` edit descriptor, so a longer name is silently cut to 30 characters and the
program then opens a file that does not exist; the seed is a default integer. The program takes
no arguments and reads nothing else, so this file and the working directory are the whole
interface, and the driver writes one per run.

The seed reaches RANLUX through ``rluxgo``, which takes it as a positive default integer; the
2012 references were produced at 5013489, the seed the shipped ``mobcal.in`` carries.
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

    def __post_init__(self) -> None:
        check_name(self.input_name, "input file name")
        check_name(self.output_name, "output file name")
        if not isinstance(self.seed, int) or not 1 <= self.seed <= MAX_SEED:
            raise InFileError(f"seed {self.seed!r}: a positive integer up to {MAX_SEED}")

    def text(self) -> str:
        return f"{self.input_name}\n{self.output_name}\n{self.seed}\n"

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
        return cls(lines[0][:FIELD_WIDTH].rstrip(" "), lines[1][:FIELD_WIDTH].rstrip(" "), seed)

    @classmethod
    def read(cls, path: Path) -> InFile:
        with open(path, encoding="latin-1") as f:
            return cls.parse(f.read())
