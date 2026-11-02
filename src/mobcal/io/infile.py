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
The record may end with the word ``claim``, ``W w claim``: the worker then integrates not a
fixed share but every block it is the first to claim, by creating ``../claim-<set>-<k>`` in
the directory above its own, so workers that finish early keep integrating until no block is
left. The package calls the two dealings ``static`` and ``claimed`` (``DEALINGS``); the word
is written only for ``claimed``, so a static run file is what it was. The program refuses any
other word, and ``claim`` on the combining run, before it calculates anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

NAME = "mobcal.in"
FIELD_WIDTH = 30
MAX_SEED = 2**31 - 1
GENERATORS = ("ranlux", "philox")  # the words the program accepts on the seed record
DEFAULT_GENERATOR = "ranlux"  # what no word means: the 2012 generator
DEALINGS = ("static", "claimed")  # how a split run's blocks are shared among its workers
DEFAULT_DEALING = "claimed"  # the package's default for a split run (lab record, task 46)
RECORD_DEFAULT_DEALING = "static"  # what no word on the fourth record means: the (w, W) share
CLAIM_WORD = "claim"  # the word the program reads for the claimed dealing
_DEALING_WORDS = {"static": "static", CLAIM_WORD: "claimed"}  # the record's words


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
    dealing: str = RECORD_DEFAULT_DEALING  # static, or claimed (the word claim on the record)

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
        if self.dealing not in DEALINGS:
            raise InFileError(f"dealing {self.dealing!r}: one of {' or '.join(DEALINGS)}")
        if self.dealing == "claimed" and not (self.split and self.split[1] > 0):
            raise InFileError("dealing 'claimed' needs a worker, split (W, w) with w >= 1: the "
                              "combining run does not claim blocks")

    def text(self) -> str:
        word = "" if self.generator == DEFAULT_GENERATOR else f" {self.generator}"
        text = f"{self.input_name}\n{self.output_name}\n{self.seed}{word}\n"
        if self.split is not None:
            claim = f" {CLAIM_WORD}" if self.dealing == "claimed" else ""
            text += f"{self.split[0]} {self.split[1]}{claim}\n"
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
        split, dealing = None, RECORD_DEFAULT_DEALING
        rest = [s for s in lines[3:] if s.strip()]
        if rest:
            fields = rest[0].split()
            try:
                total, me = (int(x) for x in fields[:2])
            except ValueError:
                raise InFileError(f"split record {rest[0]!r} is not two integers") from None
            split = (total, me)
            if len(fields) > 2:  # the program reads a third word and refuses any other
                if fields[2] not in _DEALING_WORDS:
                    raise InFileError(f"split record {rest[0]!r}: the word after W w is "
                                      f"{fields[2]!r}, not static or {CLAIM_WORD}")
                dealing = _DEALING_WORDS[fields[2]]
        return cls(lines[0][:FIELD_WIDTH].rstrip(" "), lines[1][:FIELD_WIDTH].rstrip(" "), seed,
                   split, generator, dealing)

    @classmethod
    def read(cls, path: Path) -> InFile:
        with open(path, encoding="latin-1") as f:
            return cls.parse(f.read())
