"""The element tables: TOML files per gas, checked, pinned, and rendered into every run.

Each program assigns every atom of the ion a mass, a Lennard-Jones well depth and radius and a
hard-sphere radius by the atom's integer mass key. The 2012 source held those tables as chains
of ``if(imass(iatom).eq.NN)`` blocks; here each gas's table is a TOML file beside this module,
``mobcal_He.toml`` and ``mobcal_N2.toml``, and the source of truth for it. Those are each gas's
default set, named ``2012``. ``SETS`` adds the named alternates, so far one: ``2000`` for
helium, the Jarrold group's 2000 table (``mobcal_He_2000.toml``, every token that release's
literal). ``SHA256`` pins every shipped file as ``mobcal.fortran.SHA256`` pins the Fortran, and
``verify`` compares. ``--parameters`` takes a set's name or a path (``path_for``).

Every number in a file is a string holding the Fortran literal exactly as the 2012 source
spells it, because the spelling is the precision: ``0.4020`` is a REAL(4) literal and
``0.4020d0`` a REAL(8) one, different in the eighth digit, and the nitrogen table's literals
are single precision in every nitrogen cross section the program has produced. A TOML float
would be parsed to a double and that difference lost. ``[kinds]`` declares each column's
precision and ``load`` refuses a token whose spelling disagrees. Two tokens are expressions,
because the source wrote them as expressions and the expression is the record: helium sodium's
sigma, ``3.97d0/1.12246d0``, and nitrogen's ``conve``, ``4.2d0*0.01036427d0``. They are the
only tokens allowed an operator.

The package never does arithmetic with a parameter. ``ParameterSet.render`` writes
``parameters.tab`` into a run directory, the table the program reads: blank-separated tokens
only, no comment, no free text, no ``/`` or ``,`` (each would end or split a list-directed
read), every literal copied verbatim and each of the two expressions evaluated in IEEE double
and written as its 17-significant-digit round-trip token, which a compiled fold of the same
expression reproduces bit for bit. The driver renders it into every run directory, every run;
``mobcal render-parameters`` does it by hand.

    from mobcal import parameters
    ps = parameters.load(parameters.default_path("n2"), gas="n2")
    ps.render(Path("runs/choline-n2-5013489"))
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

PARAMETERS_DIR = Path(__file__).resolve().parent
# Per gas, the shipped sets by name, the default first. A run uses the default unless told
# otherwise; the 2012 tables are the default for both gases.
SETS = {
    "he": {"2012": "mobcal_He.toml", "2000": "mobcal_He_2000.toml"},
    "n2": {"2012": "mobcal_N2.toml"},
}
DEFAULT = "2012"
FILES = {gas: sets[DEFAULT] for gas, sets in SETS.items()}  # each gas's default file

# Every shipped table as committed (LF line endings, see .gitattributes).
SHA256 = {
    "mobcal_He.toml": "6e19c7ce13dbff2035bac9c762226db61316e706b23f52f2336028af76da18f0",
    "mobcal_He_2000.toml": "441382ffc0f618d2358131f74ed4898312c4d1b21524faf08fb9c3eeaedb9940",
    "mobcal_N2.toml": "06a2528ec169627d1c002c2d9561d7d8c434a459552b5642845ba69807443595",
}

FORMATS = (1,)  # the schema versions load() reads
RENDERED = "parameters.tab"  # the table's name in a run directory
MAGIC = "MOBCAL-LJ"  # the first token of a rendered table
RENDERED_FORMAT = 1  # the rendered table's own version, its second token

GAS = {"he": "He", "n2": "N2"}  # a file's spelling of the package's gas
FORM = {"he": "pair", "n2": "combining"}  # the one form each program implements
COLUMNS = ("mass", "epsilon", "sigma", "rhs")  # in the rendered row's order, after the key
KIND_BYTES = {"single": 4, "double": 8}
CONSTANTS = ("eogas", "rogas", "conve", "convr")  # [combining], double precision, this order
STATUS = ("fitted", "provisional")
RHS_STATUS = ("own", "borrowed")
ELEMENT_FIELDS = ("key", "symbol", *COLUMNS, "status", "rhs_status", "provenance")
TOP_LEVEL = ("format", "name", "gas", "form", "kinds", "combining", "element")

# The two expressions the 2012 source wrote, the only tokens allowed an operator.
EXPRESSIONS = ("3.97d0/1.12246d0", "4.2d0*0.01036427d0")

MAX_TOKEN = 32  # characters; the program reads each token into a character*32
MAX_ROWS = 100
MAX_NAME = 60

_LITERAL = re.compile(r"[0-9]+\.[0-9]*(?:[dD][+-]?[0-9]+)?")
_SYMBOL = re.compile(r"[A-Z][a-z]{0,2}")
# Printable characters a list-directed read takes as part of an undelimited string: no quote,
# no slash, no comma, no asterisk.
_NAME = re.compile(r"[A-Za-z0-9 ._()+\-]+")


class ParameterError(ValueError):
    """A parameter file that cannot be used, with the file, the element and the field named."""


def kind_of(literal: str) -> str:
    """The precision Fortran gives a real literal: double with a ``d`` exponent, else single."""
    return "double" if "d" in literal.lower() else "single"


def _value(literal: str) -> float:
    return float(literal.lower().replace("d", "e"))


def _operands(token: str) -> tuple[str, str, str] | None:
    """``(left, operator, right)`` for one of the two recorded expressions, else None."""
    if token not in EXPRESSIONS:
        return None
    op = "/" if "/" in token else "*"
    left, right = token.split(op)
    return left, op, right


def evaluate(token: str) -> float:
    """The value of one of the two recorded expressions, in IEEE double: each operand read as
    the REAL(8) literal it is, then one correctly rounded division or product, which is what a
    compiler's fold of the same expression computes."""
    parts = _operands(token)
    if parts is None:
        raise ValueError(f"{token!r} is not one of the recorded expressions {EXPRESSIONS}")
    left, op, right = parts
    a, b = _value(left), _value(right)
    return a / b if op == "/" else a * b


def rendered_token(token: str) -> str:
    """What the rendered table carries for a token: the literal verbatim, or an expression's
    value as the 17-significant-digit round-trip literal with a ``d`` exponent."""
    if _operands(token) is None:
        return token
    return f"{evaluate(token):.16e}".replace("e", "d")


def _check_token(token: object, kind: str, where: str) -> str:
    if not isinstance(token, str):
        raise ParameterError(f"{where}: must be a string holding the Fortran literal, as "
                             f'"1.35d-3"; a TOML number would lose its spelling')
    if len(token) > MAX_TOKEN:
        raise ParameterError(f"{where}: {token!r} is longer than {MAX_TOKEN} characters")
    parts = _operands(token)
    if parts is None and ("/" in token or "*" in token):
        raise ParameterError(f"{where}: {token!r}: an operator is allowed only in the two "
                             f"expressions the 2012 source wrote, {' and '.join(EXPRESSIONS)}")
    for lit in ((parts[0], parts[2]) if parts else (token,)):
        if not _LITERAL.fullmatch(lit):
            raise ParameterError(f"{where}: {token!r} is not a Fortran real literal (digits, "
                                 f"one '.', digits, an optional d exponent)")
        if kind_of(lit) != kind:
            raise ParameterError(f"{where}: {token!r} is spelled {kind_of(lit)} precision and "
                                 f"the column is declared {kind}")
    if not (evaluate(token) if parts else _value(token)) > 0:
        raise ParameterError(f"{where}: {token!r} is not positive")
    return token


def _string(table: dict, field: str, where: str, allowed: tuple[str, ...] | None = None) -> str:
    v = table.get(field)
    if not isinstance(v, str):
        raise ParameterError(f"{where}: {field} must be a string")
    if allowed is not None and v not in allowed:
        raise ParameterError(f"{where}: {field} is {v!r}, not one of {', '.join(allowed)}")
    return v


@dataclass(frozen=True)
class Element:
    key: int  # the integer mass key the .mfj file carries
    symbol: str
    mass: str  # the Fortran literals, verbatim
    epsilon: str
    sigma: str
    rhs: str
    status: str  # fitted | provisional
    rhs_status: str  # own | borrowed
    provenance: str

    def tokens(self) -> list[str]:
        return [str(self.key), *(rendered_token(getattr(self, c)) for c in COLUMNS)]


@dataclass(frozen=True)
class ParameterSet:
    path: Path
    sha256: str  # of the file's bytes
    format: int
    name: str
    gas: str  # the package's spelling, he | n2
    form: str  # pair | combining
    kinds: dict[str, str]  # column -> single | double
    constants: dict[str, str]  # eogas, rogas, conve, convr for combining; empty for pair
    elements: tuple[Element, ...]

    @property
    def keys(self) -> tuple[int, ...]:
        return tuple(e.key for e in self.elements)

    @property
    def shipped(self) -> bool:
        """True when this is one of the package's own files for its gas, as pinned."""
        return self.set_name is not None

    @property
    def set_name(self) -> str | None:
        """The shipped set this file is, by its pin (``2012``, ``2000``), else None."""
        return next((n for n, f in SETS[self.gas].items() if self.sha256 == SHA256[f]), None)

    def lines(self) -> list[str]:
        """The rendered table, line by line."""
        lines = [f"{MAGIC} {RENDERED_FORMAT} {GAS[self.gas]} {self.name.replace(' ', '_')} "
                 f"{self.sha256}",
                 " ".join(str(KIND_BYTES[self.kinds[c]]) for c in COLUMNS)]
        if self.form == "combining":
            lines.append(" ".join(rendered_token(self.constants[c]) for c in CONSTANTS))
        lines.append(str(len(self.elements)))
        lines += [" ".join(e.tokens()) for e in self.elements]
        bad = [line for line in lines if "/" in line or "," in line or "\t" in line]
        if bad:  # cannot happen after load(); a list-directed read would stop or split on it
            raise ParameterError(f"{self.path}: the rendered table would carry {bad[0]!r}")
        return lines

    def render(self, d: Path) -> Path:
        """Write ``parameters.tab`` into ``d`` (LF, ASCII) and return its path."""
        out = Path(d) / RENDERED
        out.write_text("\n".join(self.lines()) + "\n", encoding="ascii", newline="\n")
        return out

    def record(self) -> dict:
        """What a run's record says about the set it used."""
        return {"path": str(self.path), "name": self.name, "format": self.format,
                "gas": GAS[self.gas], "sha256": self.sha256, "shipped": self.shipped,
                "rendered": RENDERED}


def default_path(gas: str) -> Path:
    """The package's own table for a gas, its default set."""
    if gas not in FILES:
        raise ValueError(f"gas must be one of {tuple(FILES)}, not {gas!r}")
    return PARAMETERS_DIR / FILES[gas]


def names(gas: str | None = None) -> tuple[str, ...]:
    """The shipped sets' names for a gas, the default first; without one, every gas's."""
    if gas is None:
        return tuple(dict.fromkeys(n for sets in SETS.values() for n in sets))
    default_path(gas)  # the gas check
    return tuple(SETS[gas])


def shipped_path(gas: str, name: str | None = None) -> Path:
    """The file of a shipped set for a gas, by name; the default set without one."""
    if name is None:
        return default_path(gas)
    if name not in names(gas):
        raise ParameterError(f"no shipped {GAS[gas]} set is named {name!r}; the shipped "
                             f"{GAS[gas]} sets are {', '.join(names(gas))}")
    return PARAMETERS_DIR / SETS[gas][name]


def path_for(value: str | Path | None, gas: str) -> Path:
    """What ``--parameters`` names for a gas: nothing, the default set; a shipped set's name,
    that set's file; anything else, a path. A file called by a set's name is given with its
    directory, ``./2000``."""
    if value is None:
        return default_path(gas)
    if isinstance(value, str) and value in names():
        return shipped_path(gas, value)
    return Path(value)


def load(path: Path | str, gas: str | None = None) -> ParameterSet:
    """Read and check a parameter file; with ``gas``, also refuse a table for the other gas.

    Raises ParameterError naming the file, and the element key and field where there is one.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as e:
        raise ParameterError(f"{path}: cannot read: {e.strerror or e}") from None
    sha = hashlib.sha256(data).hexdigest()
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ParameterError(f"{path}: not a TOML file: {e}") from None

    unknown = [k for k in doc if k not in TOP_LEVEL]
    if unknown:
        raise ParameterError(f"{path}: unknown key {unknown[0]!r}")
    fmt = doc.get("format")
    if type(fmt) is not int or fmt not in FORMATS:
        raise ParameterError(f"{path}: format is {fmt!r}; this version of mobcal reads "
                             f"format {', '.join(map(str, FORMATS))}")
    name = _string(doc, "name", str(path))
    if not (0 < len(name) <= MAX_NAME and _NAME.fullmatch(name) and name == name.strip()):
        raise ParameterError(f"{path}: name {name!r} must be 1 to {MAX_NAME} characters of "
                             f"letters, digits, blanks and ._()+- with no blank at either end")
    file_gas = _string(doc, "gas", str(path), tuple(GAS.values()))
    pkg_gas = next(g for g, s in GAS.items() if s == file_gas)
    if gas is not None and gas != pkg_gas:
        raise ParameterError(f"{path}: is a table for {file_gas}, not {GAS[gas]}")
    form = _string(doc, "form", str(path), tuple(FORM.values()))
    if form != FORM[pkg_gas]:
        raise ParameterError(f"{path}: form is {form!r}; the {file_gas} program implements "
                             f"{FORM[pkg_gas]!r} only")

    kinds = doc.get("kinds")
    if not isinstance(kinds, dict) or set(kinds) != set(COLUMNS):
        raise ParameterError(f"{path}: [kinds] must declare exactly {', '.join(COLUMNS)}")
    for c in COLUMNS:
        _string(kinds, c, f"{path}: [kinds]", tuple(KIND_BYTES))

    constants: dict[str, str] = {}
    if form == "combining":
        table = doc.get("combining")
        if not isinstance(table, dict) or set(table) != set(CONSTANTS):
            raise ParameterError(f"{path}: [combining] must give exactly {', '.join(CONSTANTS)}")
        for c in CONSTANTS:
            constants[c] = _check_token(table[c], "double", f"{path}: [combining] {c}")
    elif "combining" in doc:
        raise ParameterError(f"{path}: [combining] is for form \"combining\" only")

    rows = doc.get("element")
    if not (isinstance(rows, list) and all(isinstance(r, dict) for r in rows)):
        raise ParameterError(f"{path}: the elements must be [[element]] tables")
    if not 1 <= len(rows) <= MAX_ROWS:
        raise ParameterError(f"{path}: {len(rows)} elements; 1 to {MAX_ROWS} are allowed")
    elements, seen = [], set()
    for i, row in enumerate(rows, 1):
        key = row.get("key")
        if type(key) is not int or key < 1:
            raise ParameterError(f"{path}: element {i}: key must be a positive integer")
        where = f"{path}: element {key}"
        if key in seen:
            raise ParameterError(f"{where}: key {key} appears twice")
        seen.add(key)
        missing = [f for f in ELEMENT_FIELDS if f not in row]
        extra = [f for f in row if f not in ELEMENT_FIELDS]
        if missing or extra:
            raise ParameterError(f"{where}: " + (f"no {missing[0]}" if missing
                                                 else f"unknown field {extra[0]!r}"))
        symbol = _string(row, "symbol", where)
        if not _SYMBOL.fullmatch(symbol):
            raise ParameterError(f"{where}: symbol {symbol!r} is not an element symbol")
        tokens = {c: _check_token(row[c], kinds[c], f"{where}: {c}") for c in COLUMNS}
        provenance = _string(row, "provenance", where)
        if not provenance.strip() or "\n" in provenance or "\r" in provenance:
            raise ParameterError(f"{where}: provenance must be one non-empty line")
        elements.append(Element(key, symbol, **tokens,
                                status=_string(row, "status", where, STATUS),
                                rhs_status=_string(row, "rhs_status", where, RHS_STATUS),
                                provenance=provenance))
    return ParameterSet(path, sha, fmt, name, pkg_gas, form, dict(kinds), constants,
                        tuple(elements))


def shipped(gas: str, name: str | None = None) -> ParameterSet:
    """A shipped set for a gas, by name (the default without one), loaded and checked."""
    return load(shipped_path(gas, name), gas=gas)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(parameters_dir: Path = PARAMETERS_DIR) -> list[str]:
    """One line per shipped table that is missing or differs from its pin. Empty means every
    one is the committed file."""
    problems = []
    for name, want in SHA256.items():
        p = parameters_dir / name
        if not p.is_file():
            problems.append(f"{name}: missing")
            continue
        got = _sha256(p)
        if got != want:
            problems.append(f"{name}: sha256 {got[:12]}... differs from the pinned {want[:12]}...")
    return problems
