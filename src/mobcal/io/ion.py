"""The ion file, ``X.ion.json``: format ``ccs-ion``, version 1 (``mobcal-ion`` before 2.1.0,
in development versions only, which this reader refuses by that name).

``docs/ion-file.md`` is the specification and ``ion.schema.json`` beside this module its
structure as a JSON Schema; this module reads, checks and writes the format with the standard
library alone (the schema is for other tools and for the tests, never loaded here). ``Ion.parse``
refuses everything that page's "What a reader refuses" lists, naming the field by its path
(``conformers[1].charges[3]``), and nothing it does not.

Two conversions, both pure apart from the record of who wrote the file:

- ``from_mfj``: a ``.mfj`` read the way the 2012 program reads it (``mobcal.io.mfj``) into an
  ion file. Each key is named by the shipped default tables, which agree on every key they
  share; a key none defines is refused. Coordinates, units, label, charge mode and correction
  factor are kept as read; a four-field atom line becomes a ``null`` charge; a set whose atom
  order differs from the first keeps its own ``symbols``. z is the common integer of every
  set's charge sum within ``TOLERANCE``, else ``null``. Given a path to MobCal-MPI's
  nine-column layout (``mobcal.io.mobcalmpi.detect``), it reads that instead: each element
  named from its mass, the masses and MMFF94 α N A G kept as declared columns, line 6 (in
  MobCal-MPI a switch, not a coordinate factor) and the run line kept in ``import.source``, and
  a correction factor of 1, since MobCal-MPI applies none.
- ``Ion.mfj``: the ion file back into the ``Mfj`` a run stages, for one element table. Each
  symbol becomes that table's key, so the table, not the file, decides what an atom weighs; an
  element the table lacks is refused, and so is a nitrogen run whose first conformer lacks a
  charge on any atom (``mobcal_N2.f`` reads five fields there in every mode). ``Mfj.text`` then
  gives the bytes, which depend on nothing else.

``from_mfj(path).mfj(table)`` equals ``Mfj.read(path)`` for every file the reader accepts and
every table that holds its elements, and its ``text()`` is the original byte for byte when
``Mfj.text`` wrote the original.

    from mobcal import parameters
    from mobcal.io import ion
    i = ion.from_mfj("Choline.mfj")
    i.write("choline.ion.json")
    ion.Ion.read("choline.ion.json").mfj(parameters.shipped("n2")).write("run/Choline.mfj")
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from mobcal import __version__, fortran, parameters
from mobcal.io import mobcalmpi, strictjson
from mobcal.io.mfj import FIELD_WIDTH, MAX_ATOMS, MAX_SETS, Atom, Mfj

FORMAT = "ccs-ion"
FORMERLY = "mobcal-ion"  # the format's name before 2.1.0, in development versions only
VERSIONS = (1,)  # the versions this reader takes
VERSION = 1  # the version this writer writes
SUFFIX = ".ion.json"
SCHEMA = Path(__file__).with_name("ion.schema.json")
TOLERANCE = 1e-3  # |sum of charges - z| in e; the import's tolerance
UNITS = {"angstrom": "ang", "bohr": "au"}  # the ion file's unit -> line 4 of the .mfj
CHARGE_MODES = ("calc", "equal", "none")
GASES = ("he", "n2")  # whose default tables name a .mfj's keys

# Each optional column, its fixed unit, and where it lives. ``charges`` is per conformer; the
# others are top-level and per atom, except ``connectivity``, a table of bonds.
COLUMNS = {"charges": "e", "masses": "u", "mmff94_types": "1", "mmff94_alpha": "angstrom^3",
           "mmff94_n": "1", "mmff94_a": "1", "mmff94_g": "1", "connectivity": "1"}
PER_ATOM = ("masses", "mmff94_types", "mmff94_alpha", "mmff94_n", "mmff94_a", "mmff94_g")
TOP_LEVEL = ("format", "version", "label", "comment", "molecular_charge", "units",
             "correction_factor", "charge_mode", "symbols", "columns", *PER_ATOM,
             "connectivity", "conformers", "import", "written", "written_by")
REQUIRED = ("format", "version", "label", "molecular_charge", "units", "correction_factor",
            "charge_mode", "symbols", "columns", "conformers", "written_by")
CONFORMER = ("symbols", "geometry", "charges")
IMPORT = ("source", "charges", "elements")
IMPORT_CHARGES = ("choice", "net_charge", "net_charge_from", "sum", "difference", "tolerance",
                  "available", "refused")
NET_CHARGE_FROM = ("output", "given", "charges", None)

_SYMBOL = re.compile(r"[A-Z][a-z]?")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}(-dirty)?")
# What str.splitlines() breaks a line on, and so what Mfj.parse would split a label on.
_LINE_BREAK = re.compile(r"[\n\r\x0b\x0c\x1c\x1d\x1e\x85  ]")


class IonError(ValueError):
    """An ion file MOBCAL refuses, or a ``.mfj`` it cannot write from one, with the field named."""


@dataclass(frozen=True)
class Conformer:
    geometry: tuple[tuple[float, float, float], ...]  # in the file's units, as read
    charges: tuple[float | None, ...] | None = None  # None: the conformer has no charge column
    symbols: tuple[str, ...] | None = None  # only where the atom order differs from the file's


@dataclass(frozen=True)
class Ion:
    label: str
    molecular_charge: int | None
    units: str  # angstrom | bohr
    correction_factor: float
    charge_mode: str  # calc | equal | none
    symbols: tuple[str, ...]
    conformers: tuple[Conformer, ...]
    written_by: dict  # program, version, commit (None where the program knows none)
    columns: dict = field(default_factory=dict)  # name -> {"unit", "source"}
    per_atom: dict = field(default_factory=dict)  # top-level column name -> tuple, one per atom
    connectivity: tuple[tuple[int, int, float], ...] | None = None
    comment: str | None = None
    import_record: dict | None = None  # the "import" block, as read
    written: str | None = None

    @classmethod
    def read(cls, path: Path | str) -> Ion:
        path = Path(path)
        try:
            return cls.parse(path.read_text(encoding="utf-8-sig"))
        except IonError as e:
            raise IonError(f"{path.name}: {e}") from None

    @classmethod
    def parse(cls, text: str) -> Ion:
        try:
            data = strictjson.loads(text)
        except strictjson.StrictJSONError as e:
            raise IonError(str(e)) from None
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: object) -> Ion:
        return _check(data)

    @property
    def atoms(self) -> int:
        return len(self.symbols)

    def to_dict(self) -> dict:
        d: dict = {"format": FORMAT, "version": VERSION, "label": self.label}
        if self.comment is not None:
            d["comment"] = self.comment
        d |= {"molecular_charge": self.molecular_charge, "units": self.units,
              "correction_factor": self.correction_factor, "charge_mode": self.charge_mode,
              "symbols": list(self.symbols), "columns": {k: dict(v) for k, v in
                                                         self.columns.items()}}
        for name in PER_ATOM:
            if name in self.per_atom:
                d[name] = list(self.per_atom[name])
        if self.connectivity is not None:
            d["connectivity"] = [list(b) for b in self.connectivity]
        conformers = []
        for c in self.conformers:
            cd: dict = {}
            if c.symbols is not None:
                cd["symbols"] = list(c.symbols)
            cd["geometry"] = [list(xyz) for xyz in c.geometry]
            if c.charges is not None:
                cd["charges"] = list(c.charges)
            conformers.append(cd)
        d["conformers"] = conformers
        if self.import_record is not None:
            d["import"] = self.import_record
        if self.written is not None:
            d["written"] = self.written
        d["written_by"] = dict(self.written_by)
        return d

    def text(self) -> str:
        """The file: JSON, two-space indent, an array of scalars on one line (so one atom's
        coordinates per line), every real as its shortest round-trip literal, LF."""
        return _dumps(self.to_dict(), 0) + "\n"

    def write(self, path: Path | str, overwrite: bool = False) -> Path:
        """Write ``text()`` to ``path`` (UTF-8, LF); refuses to replace a file unless told to."""
        path = Path(path)
        if path.exists() and not overwrite:
            raise IonError(f"{path} exists; not replacing it")
        path.write_text(self.text(), encoding="utf-8", newline="\n")
        return path

    def mfj(self, table: parameters.ParameterSet) -> Mfj:
        """The ``.mfj`` a run on ``table`` reads: each symbol as the table's key, the rest as
        stored. Refuses an element the table lacks and, in nitrogen, a first conformer without
        a charge on every atom."""
        keys = {e.symbol: e.key for e in table.elements}
        used = dict.fromkeys(s for c in self.conformers for s in (c.symbols or self.symbols))
        missing = [s for s in used if s not in keys]
        if missing:
            counts = ", ".join(f"{s} ({self.symbols.count(s)} atom"
                               f"{'s' if self.symbols.count(s) != 1 else ''})" for s in missing)
            where = f" ({table.path.name})" if table.path is not None else ""
            raise IonError(f"{counts} not in the element table {table.name!r}{where}, which "
                           f"holds {', '.join(keys)}")
        first = self.conformers[0].charges
        if table.gas == "n2" and (first is None or any(q is None for q in first)):
            n = self.atoms if first is None else sum(q is None for q in first)
            raise IonError(f"{n} atom(s) of conformers[0] have no charge, and the nitrogen "
                           f"program reads one on every atom of the first set in "
                           f"{self.charge_mode} mode too")
        sets = []
        for c in self.conformers:
            q = c.charges if c.charges is not None else (None,) * self.atoms
            sets.append(tuple(Atom(x, y, z, keys[s], qi) for s, (x, y, z), qi in
                              zip(c.symbols or self.symbols, c.geometry, q, strict=True)))
        return Mfj(self.label, UNITS[self.units], self.charge_mode, self.correction_factor,
                   tuple(sets))


# What record.json keeps of an ion file's import record, under the same names: enough for the
# methods text to name the charges, which outlives the ion file moving.
IMPORT_SOURCE = ("program", "version", "keywords", "route")


def charges_record(i: Ion) -> dict:
    """The record's account of an ion file's charges: its ``charge_mode`` and, when it carries
    an import record, ``import``, that record's ``source`` program, version, and keywords or
    route as given, and its ``charges.choice``."""
    out: dict = {"charge_mode": i.charge_mode}
    r = i.import_record
    if r is not None:
        out["import"] = {"source": {k: r["source"][k] for k in IMPORT_SOURCE
                                    if k in r["source"]},
                         "charges": {"choice": r.get("charges", {}).get("choice")}}
    return out


def is_ion(path: Path | str) -> bool:
    """Whether a path names an ion file, by its extension (``.ion.json``, any case)."""
    return Path(path).name.lower().endswith(SUFFIX)


def stem(path: Path | str) -> str:
    """A file's name without ``.ion.json``, or without its last suffix when it is not one."""
    path = Path(path)
    return path.name[:-len(SUFFIX)] if is_ion(path) else path.stem


def written_by() -> dict:
    """This program, its version and the commit it was built from (None where it knows none)."""
    return {"program": "mobcal", "version": __version__, "commit": fortran._commit() or None}


def now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def key_symbols() -> dict[int, str]:
    """Each key the shipped default tables define, and its element."""
    found: dict[int, str] = {}
    for gas in GASES:
        for e in parameters.shipped(gas).elements:
            if found.setdefault(e.key, e.symbol) != e.symbol:  # they agree; a guard, not a case
                raise IonError(f"key {e.key} is {found[e.key]} in one shipped table and "
                               f"{e.symbol} in the {parameters.GAS[gas]} table")
    return found


def from_mfj(source: Mfj | Path | str) -> Ion:
    """An ion file holding what a ``.mfj`` holds. Given a path, the ``import`` block records the
    file (its path and SHA-256) and the tables that named its keys; given an ``Mfj``, there is
    no source to record and the file carries no ``import`` block."""
    if isinstance(source, Mfj):
        m, path, data = source, None, None
    else:
        path = Path(source)
        data = path.read_bytes()
        text = data.decode("latin-1")
        if mobcalmpi.detect(text):
            return _from_mobcalmpi(path, data, text)
        m = Mfj.parse(text)
    names = key_symbols()
    undefined = sorted({a.key for s in m.sets for a in s} - names.keys())
    if undefined:
        raise IonError(f"key{'s' if len(undefined) > 1 else ''} "
                       f"{', '.join(map(str, undefined))} defined in no shipped element table, "
                       f"which define {', '.join(f'{k} {s}' for k, s in sorted(names.items()))}")
    first = tuple(names[a.key] for a in m.sets[0])
    conformers = []
    for atoms in m.sets:
        syms = tuple(names[a.key] for a in atoms)
        q = tuple(a.charge for a in atoms)
        conformers.append(Conformer(tuple((a.x, a.y, a.z) for a in atoms),
                                    None if all(c is None for c in q) else q,
                                    None if syms == first else syms))
    sums = [None if c.charges is None or None in c.charges else math.fsum(c.charges)
            for c in conformers]
    z = None
    if None not in sums:
        z = round(sums[0])
        if any(abs(s - z) > TOLERANCE for s in sums):
            z = None
    name = path.name if path else "the .mfj"
    columns = {}
    if any(c.charges is not None for c in conformers):
        columns["charges"] = {"unit": "e", "source": f"{name}, column 5 ({m.charge_mode} mode)"}
    record = None
    if path is not None:
        used = {s for c in conformers for s in (c.symbols or first)}
        record = {
            "source": {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
                       "program": "mfj", "version": None, "reader": f"mobcal {__version__}"},
            "charges": {"choice": "column",
                        "net_charge_from": "charges" if z is not None else None},
            "elements": {"keys": {s: k for k, s in sorted(names.items()) if s in used},
                         "tables": {parameters.GAS[g]: {"name": t.name, "sha256": t.sha256}
                                    for g, t in ((g, parameters.shipped(g)) for g in GASES)}},
        }
    units = {v: k for k, v in UNITS.items()}[m.units]
    return Ion(m.label, z, units, m.correct, m.charge_mode, first, tuple(conformers),
               written_by(), columns, import_record=record, written=now())


def _from_mobcalmpi(path: Path, data: bytes, text: str) -> Ion:
    """``from_mfj`` for MobCal-MPI's nine-column layout (``mobcal.io.mobcalmpi``)."""
    try:
        m = mobcalmpi.MobcalMpiMfj.parse(text)
        symbols = m.symbols()
    except mobcalmpi.MobcalMpiError as e:
        raise IonError(f"MobCal-MPI layout: {e}") from None
    a = m.atoms
    q = tuple(x.charge for x in a)
    z = round(math.fsum(q))
    if abs(math.fsum(q) - z) > TOLERANCE:
        z = None
    name = path.name
    columns = {"charges": {"unit": "e", "source": f"{name}, column 5 ({m.charge_mode} mode)"},
               "masses": {"unit": "u", "source": f"{name}, column 4 (MobCal-MPI layout)"}}
    per_atom = {"masses": tuple(x.mass for x in a)}
    for col, attr, n in (("mmff94_alpha", "alpha", 6), ("mmff94_n", "n", 7),
                         ("mmff94_a", "a", 8), ("mmff94_g", "g", 9)):
        columns[col] = {"unit": COLUMNS[col],
                        "source": f"{name}, column {n} (MobCal-MPI layout)"}
        per_atom[col] = tuple(getattr(x, attr) for x in a)
    keys = {s: k for k, s in key_symbols().items()}
    record = {
        "source": {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
                   "program": "MobCal-MPI", "version": None, "reader": f"mobcal {__version__}",
                   "line_6": m.line6, "run_line": m.run_line},
        "charges": {"choice": "column",
                    "net_charge_from": "charges" if z is not None else None},
        "elements": {"keys": {s: keys[s] for s in sorted(set(symbols), key=keys.get)},
                     "tables": {parameters.GAS[g]: {"name": t.name, "sha256": t.sha256}
                                for g, t in ((g, parameters.shipped(g)) for g in GASES)}},
    }
    units = {v: k for k, v in UNITS.items()}[m.units]
    return Ion(m.label, z, units, 1.0, m.charge_mode, symbols,
               (Conformer(tuple((x.x, x.y, x.z) for x in a), q),), written_by(), columns,
               per_atom, import_record=record, written=now())


# --- checking ---------------------------------------------------------------------------------

def _fail(where: str, why: str):
    raise IonError(f"{where}: {why}")


def _unknown(d: dict, allowed: tuple[str, ...], where: str) -> None:
    extra = [k for k in d if k not in allowed]
    if extra:
        _fail(f"{where}.{extra[0]}" if where else extra[0],
              f"not a field of {FORMAT} version {VERSION}"
              + (f" here (the fields are {', '.join(allowed)})" if where else ""))


def _object(v: object, where: str) -> dict:
    if not isinstance(v, dict):
        _fail(where, f"must be an object, not {_kind(v)}")
    return v


def _list(v: object, where: str) -> list:
    if not isinstance(v, list):
        _fail(where, f"must be an array, not {_kind(v)}")
    return v


def _string(v: object, where: str) -> str:
    if not isinstance(v, str):
        _fail(where, f"must be a string, not {_kind(v)}")
    return v


def _integer(v: object, where: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        _fail(where, f"must be an integer, not {_kind(v)}")
    return v


def _real(v: object, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        _fail(where, f"must be a number, not {_kind(v)}")
    x = float(v)
    if not math.isfinite(x):
        _fail(where, f"{v!r} is not a finite double")
    return x


def _kind(v: object) -> str:
    return {dict: "an object", list: "an array", str: "a string", bool: "true or false",
            type(None): "null", int: "an integer", float: "a number"}.get(type(v), type(v).__name__)


def _per_atom(v: object, n: int, where: str) -> list:
    v = _list(v, where)
    if len(v) != n:
        _fail(where, f"{len(v)} entries for {n} atoms")
    return v


def _symbols(v: object, n: int | None, where: str) -> tuple[str, ...]:
    v = _list(v, where)
    if n is not None and len(v) != n:
        _fail(where, f"{len(v)} entries for {n} atoms")
    for i, s in enumerate(v):
        if not isinstance(s, str) or not _SYMBOL.fullmatch(s):
            _fail(f"{where}[{i}]", f"{s!r} is not an element symbol in standard case (C, Cl, Na)")
    return tuple(v)


def _check(data: object) -> Ion:
    d = _object(data, "the file")
    # format and version first, so that a file of another version is refused for that alone
    for k in ("format", "version"):
        if k not in d:
            _fail(k, "missing")
    if d["format"] == FORMERLY:
        _fail("format", f"{FORMERLY!r}, the name this format had in development versions "
              f"before 2.1.0, which no release wrote; change it to {FORMAT!r}, since nothing "
              "else differs")
    if d["format"] != FORMAT:
        _fail("format", f"{d['format']!r}; this reader reads {FORMAT!r}")
    if isinstance(d["version"], bool) or d["version"] not in VERSIONS:
        _fail("version", f"{d['version']!r}; this version of MOBCAL reads version "
              f"{', '.join(map(str, VERSIONS))} of {FORMAT}")
    _unknown(d, TOP_LEVEL, "")
    for k in REQUIRED:
        if k not in d:
            _fail(k, "missing")

    label = _string(d["label"], "label")
    if len(label) > FIELD_WIDTH:
        _fail("label", f"{len(label)} characters; line 1 of a .mfj holds {FIELD_WIDTH}")
    if _LINE_BREAK.search(label):
        _fail("label", "holds a line break")
    if any(ord(c) > 0xFF for c in label):
        _fail("label", "holds a character outside ISO 8859-1, the .mfj's encoding")
    if label != label.rstrip(" "):
        _fail("label", "ends in a blank, which line 1 of a .mfj drops")
    comment = _string(d["comment"], "comment") if "comment" in d else None
    z = d["molecular_charge"]
    if z is not None:
        z = _integer(z, "molecular_charge")
    units = d["units"]
    if units not in UNITS:
        _fail("units", f"{units!r}; one of {', '.join(UNITS)}")
    correction = _real(d["correction_factor"], "correction_factor")
    mode = d["charge_mode"]
    if mode not in CHARGE_MODES:
        _fail("charge_mode", f"{mode!r}; one of {', '.join(CHARGE_MODES)}")

    symbols = _symbols(d["symbols"], None, "symbols")
    n = len(symbols)
    if not 1 <= n <= MAX_ATOMS:
        _fail("symbols", f"{n} atoms; the program holds 1 to {MAX_ATOMS}")

    columns = _object(d["columns"], "columns")
    _unknown(columns, tuple(COLUMNS), "columns")
    for name, decl in columns.items():
        where = f"columns.{name}"
        decl = _object(decl, where)
        _unknown(decl, ("unit", "source"), where)
        for k in ("unit", "source"):
            if k not in decl:
                _fail(f"{where}.{k}", "missing")
        if decl["unit"] != COLUMNS[name]:
            _fail(f"{where}.unit", f"{decl['unit']!r}; the unit of {name} is {COLUMNS[name]!r}")
        if not _string(decl["source"], f"{where}.source"):
            _fail(f"{where}.source", "empty; say where the values came from")

    per_atom = {}
    for name in PER_ATOM:
        if name not in d:
            continue
        values = _per_atom(d[name], n, name)
        check = _integer if name == "mmff94_types" else _real
        per_atom[name] = tuple(check(v, f"{name}[{i}]") for i, v in enumerate(values))
        if name == "mmff94_types":
            bad = next((i for i, v in enumerate(per_atom[name]) if v < 1), None)
            if bad is not None:
                _fail(f"{name}[{bad}]", "an MMFF94 type is at least 1")

    connectivity = None
    if "connectivity" in d:
        bonds = []
        for b, bond in enumerate(_list(d["connectivity"], "connectivity")):
            where = f"connectivity[{b}]"
            bond = _list(bond, where)
            if len(bond) != 3:
                _fail(where, f"{len(bond)} entries; a bond is [i, j, order]")
            i, j = _integer(bond[0], f"{where}[0]"), _integer(bond[1], f"{where}[1]")
            order = _real(bond[2], f"{where}[2]")
            if not 0 <= i < n or not 0 <= j < n:
                _fail(where, f"names atom {i if not 0 <= i < n else j}; the atoms are 0 to {n - 1}")
            if not i < j:
                _fail(where, f"[{i}, {j}]: the lower atom comes first")
            if not order > 0:
                _fail(f"{where}[2]", f"bond order {order!r} is not positive")
            bonds.append((i, j, order))
        connectivity = tuple(bonds)

    raw = _list(d["conformers"], "conformers")
    if not 1 <= len(raw) <= MAX_SETS:
        _fail("conformers", f"{len(raw)} conformers; the program holds 1 to {MAX_SETS}")
    conformers = []
    for k, c in enumerate(raw):
        where = f"conformers[{k}]"
        c = _object(c, where)
        _unknown(c, CONFORMER, where)
        if "geometry" not in c:
            _fail(f"{where}.geometry", "missing")
        geometry = []
        for a, xyz in enumerate(_per_atom(c["geometry"], n, f"{where}.geometry")):
            w = f"{where}.geometry[{a}]"
            xyz = _list(xyz, w)
            if len(xyz) != 3:
                _fail(w, f"{len(xyz)} coordinates; an atom has x, y and z")
            geometry.append(tuple(_real(v, f"{w}[{i}]") for i, v in enumerate(xyz)))
        charges = None
        if "charges" in c:
            charges = tuple(None if q is None else _real(q, f"{where}.charges[{a}]")
                            for a, q in enumerate(_per_atom(c["charges"], n,
                                                            f"{where}.charges")))
        own = _symbols(c["symbols"], n, f"{where}.symbols") if "symbols" in c else None
        conformers.append(Conformer(tuple(geometry), charges, own))

    has_charges = any(c.charges is not None for c in conformers)
    present = {name: name in per_atom for name in PER_ATOM}
    present |= {"connectivity": connectivity is not None, "charges": has_charges}
    for name, here in present.items():
        if here and name not in columns:
            _fail(name, f"present without a declaration in columns.{name}")
        if not here and name in columns:
            _fail(f"columns.{name}", f"declared, and the file carries no {name}")

    if mode == "calc":
        for k, c in enumerate(conformers):
            if c.charges is None:
                _fail(f"conformers[{k}].charges", "missing; calc mode needs a charge on every atom")
            if None in c.charges:
                _fail(f"conformers[{k}].charges[{c.charges.index(None)}]",
                      "null; calc mode needs a charge on every atom")
            if z is not None:
                total = math.fsum(c.charges)
                if abs(total - z) > TOLERANCE:
                    _fail(f"conformers[{k}].charges",
                          f"sum to {total:+.6f}, {total - z:+.2e} e from molecular_charge "
                          f"{z:+d}; {TOLERANCE:g} e is allowed")
    if any(c.symbols is not None for c in conformers):
        held = [name for name in (*PER_ATOM, "connectivity") if present[name]]
        if held:
            k = next(k for k, c in enumerate(conformers) if c.symbols is not None)
            _fail(f"conformers[{k}].symbols",
                  f"a conformer with its own atom order makes {held[0]} ambiguous")

    record = None
    if "import" in d:
        record = _object(d["import"], "import")
        _check_import(record)
    written = None
    if "written" in d:
        written = _string(d["written"], "written")
        try:
            datetime.datetime.fromisoformat(written)
        except ValueError:
            _fail("written", f"{written!r} is not an ISO 8601 date and time")
    by = _object(d["written_by"], "written_by")
    _unknown(by, ("program", "version", "commit"), "written_by")
    for k in ("program", "version", "commit"):
        if k not in by:
            _fail(f"written_by.{k}", "missing")
    _string(by["program"], "written_by.program")
    _string(by["version"], "written_by.version")
    if by["commit"] is not None and not _COMMIT.fullmatch(_string(by["commit"],
                                                                  "written_by.commit")):
        _fail("written_by.commit", f"{by['commit']!r} is not 40 hexadecimal digits "
              "(with -dirty) or null")

    return Ion(label, z, units, correction, mode, symbols, tuple(conformers), dict(by),
               {k: dict(v) for k, v in columns.items()}, per_atom, connectivity, comment,
               record, written)


def _check_import(r: dict) -> None:
    _unknown(r, IMPORT, "import")
    if "source" not in r:
        _fail("import.source", "missing")
    s = _object(r["source"], "import.source")  # its other keys follow the source program
    for k in ("path", "sha256", "program", "reader"):
        if k not in s:
            _fail(f"import.source.{k}", "missing")
        _string(s[k], f"import.source.{k}")
    if not _SHA256.fullmatch(s["sha256"]):
        _fail("import.source.sha256", "is not 64 lowercase hexadecimal digits")
    if "version" in s and s["version"] is not None:
        _string(s["version"], "import.source.version")
    if "charges" in r:
        c = _object(r["charges"], "import.charges")
        _unknown(c, IMPORT_CHARGES, "import.charges")
        if "choice" not in c:
            _fail("import.charges.choice", "missing")
        _string(c["choice"], "import.charges.choice")
        if "net_charge_from" in c and c["net_charge_from"] not in NET_CHARGE_FROM:
            _fail("import.charges.net_charge_from", f"{c['net_charge_from']!r}; one of "
                  "output, given, charges or null")
    if "elements" in r:
        e = _object(r["elements"], "import.elements")
        _unknown(e, ("keys", "tables"), "import.elements")
        for k in ("keys", "tables"):
            if k not in e:
                _fail(f"import.elements.{k}", "missing")
        for sym, key in _object(e["keys"], "import.elements.keys").items():
            _symbols([sym], None, "import.elements.keys")
            _integer(key, f"import.elements.keys.{sym}")
        for name, t in _object(e["tables"], "import.elements.tables").items():
            where = f"import.elements.tables.{name}"
            t = _object(t, where)
            _unknown(t, ("name", "sha256"), where)
            for k in ("name", "sha256"):
                if k not in t:
                    _fail(f"{where}.{k}", "missing")
            if t["name"] is not None:
                _string(t["name"], f"{where}.name")
            if not _SHA256.fullmatch(_string(t["sha256"], f"{where}.sha256")):
                _fail(f"{where}.sha256", "is not 64 lowercase hexadecimal digits")


# --- writing ----------------------------------------------------------------------------------

def _scalar(v: object) -> str:
    return json.dumps(v, ensure_ascii=False, allow_nan=False)


def _dumps(v: object, depth: int) -> str:
    pad, inner = "  " * depth, "  " * (depth + 1)
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = [f"{inner}{_scalar(k)}: {_dumps(x, depth + 1)}" for k, x in v.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(v, list):
        if all(not isinstance(x, dict | list) for x in v):
            return "[" + ", ".join(_scalar(x) for x in v) + "]"
        return "[\n" + ",\n".join(inner + _dumps(x, depth + 1) for x in v) + "\n" + pad + "]"
    return _scalar(v)


def dumps(doc: dict) -> str:
    """An ion document as ``Ion.text`` lays one out, in the document's own key order: what a
    file written by this module reads back to, byte for byte."""
    return _dumps(doc, 0) + "\n"
