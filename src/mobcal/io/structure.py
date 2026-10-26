"""A structure and its charges, from an ORCA output or an ``.xyz``, written as a 2012 ``.mfj``.

The 2012 model takes little from a structure: per atom x y z, the integer mass key of its
element, and a charge. No atom type, bond or force-field label. ``read`` gets the last geometry
and every charge block that belongs to it; ``convert`` turns one choice of charges into a
single-set ``Mfj`` (ångström, ``calc`` mode, five columns) and a provenance record; ``write``
puts the two side by side, ``X.mfj`` and ``X.import.json``, because the a30 label has no room
for where the numbers came from.

Sources. An ORCA output is read with cclib, pinned in ``pyproject.toml`` and imported here only,
inside ``read``, so that nothing else in the package loads it or the numpy and scipy it brings.
ORCA prints each charge block after the coordinate block it belongs to; in an optimization it
prints Mulliken and Löwdin at the start geometry and again at the stationary point, and CHELPG,
when asked, after every cycle. cclib keeps the last coordinate block and the last block of each
kind, and those belong together only when the block comes after the coordinates. ``read``
checks that order in the text, with the headings cclib's parser triggers on, and a kind whose
last block comes before the last geometry is reported and refused, never paired. An output
that did not terminate normally, or an optimization that did not converge, is refused. A
Gaussian output is recognized and refused (not yet supported); any other program cclib knows
is refused. An ``.xyz`` is read here, without cclib: a count, a comment line, then ``symbol x y
z`` per atom with an optional fifth column, the charges (``column``). One frame only.

Charges. There is no default: ``convert`` refuses ``charges=None`` and names what the file
holds. ``uniform`` writes Q/N on every atom as explicit values in ``calc`` mode, never in
``equal`` mode, because the two 2012 programs disagree on ``equal``: ``mobcal_He.f`` gives
every atom 1/N whatever the ion's charge, ``mobcal_N2.f`` divides the sum of the charge column
(``fcoord``, label 2011 in each). The net charge Q is the one the output was computed at, or
the one given (when both, they must agree); an ``.xyz`` carries none. Named charges must sum
to Q within ``TOLERANCE`` and are written as read, never rescaled.

Elements. Each atom's key is its element's key in the shipped default table of every gas asked
for (``mobcal.parameters``), and an element a table lacks is refused, naming the gas: helium's
has no phosphorus. Nothing here adds a row.

    from mobcal.io import structure
    s = structure.read("choline_sp.out")
    structure.write(structure.convert(s, "chelpg"), "choline_sp_chelpg.mfj")
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from mobcal import __version__, parameters
from mobcal.io.mfj import FIELD_WIDTH, MAX_ATOMS, Atom, Mfj

# |sum of the named charges - Q|, in e. ORCA's Hirshfeld charges, integrated on a grid, sum to
# Q + 2.2e-4 for the 21-atom choline cation; Mulliken, Loewdin and CHELPG to Q at the printed
# digits.
TOLERANCE = 1e-3
UNIFORM = "uniform"
COLUMN = "column"  # an .xyz file's fifth column
GASES = ("he", "n2")
RECORD_SUFFIX = ".import.json"
RECORD_FORMAT = 1

# The heading of each block cclib keys, as cclib's ORCA parser matches it (a line prefix).
ORCA_HEADINGS = {
    "mulliken": "MULLIKEN ATOMIC CHARGES",
    "lowdin": "LOEWDIN ATOMIC CHARGES",
    "chelpg": "CHELPG Charges",
    "hirshfeld": "HIRSHFELD ANALYSIS",
}
ORCA_COORDINATES = "CARTESIAN COORDINATES (ANGSTROEM)"

_SYMBOL = re.compile(r"[A-Za-z]{1,2}")
_LABEL_UNSAFE = re.compile(r"[^\x21-\x7e]")


class StructureError(ValueError):
    """A file or a choice the import refuses, with the reason."""


@dataclass(frozen=True)
class Structure:
    path: Path
    sha256: str  # of the file's bytes
    program: str  # ORCA | xyz
    version: str | None  # the program's, as the output prints it
    reader: str  # cclib and its version, or mobcal's own
    symbols: tuple[str, ...]
    coordinates: tuple[tuple[float, float, float], ...]  # ångström, the last geometry
    charges: dict[str, tuple[float, ...]]  # each block that belongs to that geometry, by key
    unpaired: dict[str, str]  # each block printed but refused: key -> why
    net_charge: int | None  # the charge the output was computed at; None for an .xyz
    details: dict  # what else the record carries: route keywords, input file name, comment

    @property
    def choices(self) -> tuple[str, ...]:
        """What ``convert`` takes for ``charges``: the blocks that belong, then ``uniform``."""
        return (*self.charges, UNIFORM)

    def offer(self) -> str:
        """The choices in words, for a refusal."""
        named = ", ".join(self.charges) if self.charges else "no charges of its own"
        skipped = "".join(f"; {k} is printed but refused: {why}" for k, why in
                          self.unpaired.items())
        return (f"{self.path.name} holds {named}{skipped}; or {UNIFORM} (Q/N on every atom, "
                "from the net charge)")


@dataclass(frozen=True)
class Imported:
    mfj: Mfj
    record: dict


def read(path: Path | str) -> Structure:
    """The last geometry of an ORCA output or an ``.xyz`` and the charge blocks that belong to
    it. Raises StructureError for anything the import does not take."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as e:
        raise StructureError(f"{path}: cannot read: {e.strerror or e}") from None
    sha = hashlib.sha256(data).hexdigest()
    if path.suffix.lower() == ".xyz":
        return _read_xyz(path, sha, data)
    return _read_output(path, sha, data)


def _read_xyz(path: Path, sha: str, data: bytes) -> Structure:
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise StructureError(f"{path}: not a text file") from None
    first = lines[0].split() if lines else []
    try:
        n = int(first[0])
    except (IndexError, ValueError):
        raise StructureError(f"{path}: line 1 is not an atom count") from None
    if not 1 <= n <= MAX_ATOMS:
        raise StructureError(f"{path}: {n} atoms; the program holds 1 to {MAX_ATOMS}")
    body = lines[2:2 + n]
    if len(body) < n:
        raise StructureError(f"{path}: ends after {len(body)} of {n} atoms")
    if any(line.strip() for line in lines[2 + n:]):
        raise StructureError(f"{path}: more lines follow the {n} atoms; one file is one "
                             "geometry (a multi-frame .xyz is several runs)")
    symbols, coordinates, charges = [], [], []
    for i, line in enumerate(body, 3):
        t = line.split()
        if len(t) not in (4, 5):
            raise StructureError(f"{path}: line {i}: {len(t)} fields; an atom line is symbol "
                                 "x y z and optionally a charge")
        if not _SYMBOL.fullmatch(t[0]):
            raise StructureError(f"{path}: line {i}: {t[0]!r} is not an element symbol")
        try:
            values = [float(v) for v in t[1:]]
        except ValueError:
            raise StructureError(f"{path}: line {i}: not a number among {t[1:]}") from None
        if not all(math.isfinite(v) for v in values):
            raise StructureError(f"{path}: line {i}: not a finite number among {t[1:]}")
        symbols.append(t[0].capitalize())
        coordinates.append(tuple(values[:3]))
        charges.append(values[3] if len(values) == 4 else None)
    have = [q is not None for q in charges]
    if any(have) and not all(have):
        raise StructureError(f"{path}: {sum(have)} of {n} atoms carry a charge column; all or "
                             "none must")
    return Structure(path, sha, "xyz", None, f"mobcal {__version__}", tuple(symbols),
                     tuple(coordinates), {COLUMN: tuple(charges)} if all(have) else {}, {},
                     None, {"comment": lines[1].strip() if len(lines) > 1 else ""})


def _cclib():
    with warnings.catch_warnings():
        # cclib 1.9rc1's method/volume.py has an invalid escape in a docstring, reported once
        # when the module is first compiled.
        warnings.simplefilter("ignore", SyntaxWarning)
        import cclib
        import cclib.parser.utils
    return cclib


def _read_output(path: Path, sha: str, data: bytes) -> Structure:
    cclib = _cclib()
    logger = logging.getLogger("cclib")  # ccopen warns there of a file it cannot place
    level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        log = cclib.io.ccopen(str(path), quiet=True, loglevel=logging.CRITICAL)
    except Exception as e:
        raise StructureError(f"{path}: cannot open: {e}") from None
    finally:
        logger.setLevel(level)
    name = type(log).__name__ if log is not None else None
    if name == "Gaussian":
        log.inputfile.close()
        raise StructureError(f"{path}: a Gaussian output; Gaussian outputs are not yet "
                             "supported. ORCA outputs and .xyz files are")
    if name != "ORCA":
        if log is not None:
            log.inputfile.close()
        raise StructureError(f"{path}: " + (f"a {name} output" if name else
                                            "not an output of a program cclib recognizes, "
                                            "nor an .xyz")
                             + "; ORCA outputs and .xyz files are supported")
    reader = f"cclib {cclib.__version__}"
    try:
        out = log.parse()
    except Exception as e:
        raise StructureError(f"{path}: {reader} could not read this ORCA output "
                             f"({type(e).__name__}: {e})") from None
    finally:
        log.inputfile.close()

    meta = out.metadata
    if not meta.get("success"):
        raise StructureError(f"{path}: ORCA did not terminate normally; the last geometry and "
                             "charges may be from an unfinished step")
    if hasattr(out, "geovalues") and not getattr(out, "optdone", False):
        raise StructureError(f"{path}: the optimization did not converge; the last geometry "
                             "is not a stationary point")
    if not hasattr(out, "atomcoords") or not hasattr(out, "atomnos"):
        raise StructureError(f"{path}: {reader} found no geometry")
    n = int(out.natom)
    if not 1 <= n <= MAX_ATOMS:
        raise StructureError(f"{path}: {n} atoms; the program holds 1 to {MAX_ATOMS}")
    table = cclib.parser.utils.PeriodicTable()
    symbols = tuple(table.element[int(z)] for z in out.atomnos)
    coordinates = tuple(tuple(float(v) for v in xyz) for xyz in out.atomcoords[-1])

    # Where each block is printed, by the headings cclib's parser triggers on.
    last_geometry, last_block = -1, {}
    for i, line in enumerate(data.decode("utf-8", errors="replace").splitlines()):
        if line.startswith(ORCA_COORDINATES):
            last_geometry = i
        for key, heading in ORCA_HEADINGS.items():
            if line.startswith(heading):
                last_block[key] = i
    if last_geometry < 0:
        raise StructureError(f"{path}: no {ORCA_COORDINATES} block")
    charges, unpaired = {}, {}
    for key, values in getattr(out, "atomcharges", {}).items():
        if key not in last_block:
            unpaired[key] = "the import cannot place its block in the file"
        elif last_block[key] < last_geometry:
            unpaired[key] = ("its last block is printed before the last geometry, so it "
                             "belongs to an earlier one")
        elif len(values) != n:
            unpaired[key] = f"it has {len(values)} values for {n} atoms"
        else:
            charges[key] = tuple(float(q) for q in values)
    details = {k: meta[k] for k in ("keywords", "input_file_name") if k in meta}
    return Structure(path, sha, "ORCA", meta.get("package_version"), reader, symbols,
                     coordinates, charges, unpaired, int(out.charge), details)


def element_keys(symbols: tuple[str, ...] | list[str],
                 gases: tuple[str, ...] = GASES) -> dict[str, int]:
    """Each distinct element's key in the default table of every gas named. Refuses an element
    a table lacks, naming the gas."""
    tables = {g: parameters.shipped(g) for g in gases}
    keys = {}
    for sym in dict.fromkeys(symbols):
        found = {g: next((e.key for e in t.elements if e.symbol == sym), None)
                 for g, t in tables.items()}
        missing = [g for g, k in found.items() if k is None]
        if missing:
            g = missing[0]
            have = ", ".join(e.symbol for e in tables[g].elements)
            others = [h for h in GASES if h not in missing and
                      any(e.symbol == sym for e in parameters.shipped(h).elements)]
            raise StructureError(
                f"{sym} ({symbols.count(sym)} atom{'s' if symbols.count(sym) != 1 else ''}) is "
                f"not in the {parameters.GAS[g]} element table, which holds {have}"
                + (f"; the {', '.join(parameters.GAS[h] for h in others)} table has it, and "
                   f"an import for that gas alone would take it" if others else ""))
        distinct = set(found.values())
        if len(distinct) != 1:  # the shipped tables agree on every key; a guard, not a case
            raise StructureError(f"{sym} has different keys in the tables: {found}")
        keys[sym] = distinct.pop()
    return keys


def convert(structure: Structure, charges: str | None, net_charge: int | None = None,
            gases: tuple[str, ...] = GASES, label: str | None = None) -> Imported:
    """The ``.mfj`` for one choice of charges, and its provenance record."""
    s = structure
    if charges is None:
        raise StructureError(f"choose the charges: {s.offer()}")
    if s.net_charge is not None and net_charge is not None and net_charge != s.net_charge:
        raise StructureError(f"{s.path.name} was computed at charge {s.net_charge:+d}, and the "
                             f"net charge given is {net_charge:+d}")
    q_net = s.net_charge if s.net_charge is not None else net_charge
    if q_net is None:
        raise StructureError(f"{s.path.name} does not carry the ion's net charge; give it")
    n = len(s.symbols)
    if charges == UNIFORM:
        q = (q_net / n,) * n
    elif charges in s.charges:
        q = s.charges[charges]
    elif charges in s.unpaired:
        raise StructureError(f"{s.path.name}: {charges} is refused: {s.unpaired[charges]}")
    else:
        raise StructureError(f"no {charges!r} charges: {s.offer()}")
    total = math.fsum(q)
    if abs(total - q_net) > TOLERANCE:
        raise StructureError(f"{s.path.name}: the {charges} charges sum to {total:+.6f}, "
                             f"{total - q_net:+.2e} e from the net charge {q_net:+d}; the "
                             f"import allows {TOLERANCE:g} e")
    keys = element_keys(s.symbols, gases)
    atoms = tuple(Atom(x, y, z, keys[sym], qi)
                  for sym, (x, y, z), qi in zip(s.symbols, s.coordinates, q, strict=True))
    if label is None:
        label = _LABEL_UNSAFE.sub("_", f"{s.path.stem}_{charges}")[:FIELD_WIDTH]
    mfj = Mfj(label, "ang", "calc", 1.0, (atoms,))
    record = {
        "format": RECORD_FORMAT,
        "mobcal": __version__,
        "written": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "source": {"path": str(s.path.resolve()), "sha256": s.sha256, "program": s.program,
                   "version": s.version, "reader": s.reader, **s.details},
        "charges": {"choice": charges, "net_charge": q_net,
                    "net_charge_from": "output" if s.net_charge is not None else "given",
                    "sum": total, "difference": total - q_net, "tolerance": TOLERANCE,
                    "available": list(s.charges), "refused": s.unpaired},
        "elements": {"keys": keys, "tables": {
            parameters.GAS[g]: {"name": t.name, "sha256": t.sha256}
            for g, t in ((g, parameters.shipped(g)) for g in gases)}},
        "mfj": {"label": label, "atoms": n, "units": "ang", "charge_mode": "calc"},
    }
    return Imported(mfj, record)


def record_path(mfj_path: Path | str) -> Path:
    """Where the provenance record of an imported ``X.mfj`` goes: ``X.import.json``."""
    p = Path(mfj_path)
    return p.with_name(p.stem + RECORD_SUFFIX)


def write(imported: Imported, out: Path | str, overwrite: bool = False) -> tuple[Path, Path]:
    """Write the ``.mfj`` and its record beside it; refuses to replace either unless told to."""
    out = Path(out)
    rec = record_path(out)
    if not overwrite:
        for p in (out, rec):
            if p.exists():
                raise StructureError(f"{p} exists; not replacing it")
    text = imported.mfj.text()
    if Mfj.parse(text) != imported.mfj:  # the writer's promise, kept on every file
        raise StructureError(f"{out}: the file would not read back as written")
    data = text.encode("latin-1")
    record = dict(imported.record)
    record["mfj"] = {**record["mfj"], "file": out.name, "sha256": hashlib.sha256(data).hexdigest()}
    out.write_bytes(data)
    rec.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")
    return out, rec
