"""The methods: everything a calculation depends on but its input, in one file.

A method is the gas, the element table, the random number generator and the six run settings
(``mobcal.settings``), and may carry a seed and a description. It is a JSON file,
``NAME.method.json`` (``load``, ``save``), and five ship beside this module, pinned like the
element tables (``SHA256``, ``verify``), each known by its key, the file's name without
``.method.json``:

    2012-he, 2012-n2              the calculation of the 2012 release: its tables and settings
                                  under RANLUX, which reproduces the 2012 outputs at the 2012 seed
    2012-philox-he, 2012-philox-n2  the same tables and settings under Philox4x32-10, whose
                                  divided runs give the serial result exactly; 2012-philox-he
                                  is the default of ``mobcal run`` and of the window
    2000-he                       the Jarrold group's 2000 helium release: its table, 298 K and
                                  ``imp`` 25, under RANLUX; it has no nitrogen form

A method file of one's own follows the same format, ``ccs-method`` version 1, one JSON object:
a core any program's method has, and one block of what only MOBCAL's has, the keys in this
order (``KEYS``, ``BLOCK``):

    "format": "ccs-method", "version": 1
    "name": "My method"            1 to 60 characters, shown in the window and recorded by runs
    "description": "..."           optional: what the method is, the Method list's tooltip
    "gas": "He"                    by formula, He or N2
    "temperature": {"value": 301, "unit": "K"}
    "seed": 5013489                optional: the first seed of a run made from the method
    "mobcal": {
      "generator": "philox"        philox or ranlux
      "imp": 1000, "itn": 10, "inp": 40, "inum": 250000, "inor": 30
      "parameters": {...}          the element table, whole (mobcal.parameters.from_document)
    }

Every key but ``description`` and ``seed`` is required, in the core and in the block, and an
unknown key is refused by name; format and version are checked first, so a file of another
version is refused for that alone, and a file under the format's name before 2.1.0
(``mobcal-method``, never released) is refused with that said. A method whose block is another
program's is refused by that program's name. The text is read as the ion file is
(``mobcal.io.strictjson``): a key twice in one object, or ``NaN`` or ``Infinity``, is refused.
The element table is carried whole, shipped or one's own, with the SHA-256 of the TOML file it
was taken from and of its rendered rows, so a method needs no other file to run: a shipped table
is checked against its pinned file, and any table's rows against its ``rows_sha256``. A file
whose name ends in ``.toml`` is refused with a message that method files are JSON: the TOML
method files of 2.0 were converted when the format changed, and no TOML reader is kept.

``seed`` and ``description`` are optional and are not fields ``identify`` reads: a run at
another seed is still a run of its method, and a description says what a method is without
being part of it. A run made from a method with a seed and no ``--seeds`` runs at it (n seeds
count up from it in the window); ``--seeds`` wins when given. Without one, the first seed is
the 2012 seed, 5013489 (``Method.first_seed``). The shipped methods carry a description and no
seed.

``method.schema.json`` beside this module is the format as a JSON Schema (``SCHEMA``), for
other tools, editors and the tests, never loaded here; its description lists the rules only
``load`` applies (the table's two hashes and its unique keys, the name against the list, a
finite temperature, counts written as integers, ``settings.MAX_POINTS``, the name's printable
characters beyond the controls). The tests hold its keys, enums and bounds to the constants
here.

``identify`` names the shipped method a run used from what the run used, so a run made with
``--rng ranlux`` and nothing else is a ``2012-he`` run whether or not ``--method 2012-he`` was
typed, and a run matching none is ``custom``. A run made from a file of one's own records the
file's name and SHA-256 while its fields are the file's (``mobcal.run.Job``). A record written
before methods carried their gas names ``current``, ``2012`` or ``2000``; ``record_method``
reads those as the shipped method they were (``ALIASES``).

``text`` writes the methods paragraph for a set of runs from their records: program and
version, method, gas, table, temperature, trajectory counts, generator, seeds, and the papers
to cite. It is the window's Copy methods text and ``mobcal methods-text``. Until this
package's own paper exists it cites the version and the repository.

    from mobcal import methods
    m = methods.get("2000-he")          # or a path to a method file
    methods.save(Path("mine.method.json"), "Mine", "he", "2012", "philox", m.settings)
    methods.save(Path("own.method.json"), "Own", "he", Path("my.toml"), "philox", m.settings)
    print(methods.text(methods.read_records([Path("runs")])))
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from mobcal import parameters, settings
from mobcal.io import strictjson
from mobcal.io.infile import GENERATORS, MAX_SEED
from mobcal.settings import DEFAULTS, Settings

METHODS_DIR = Path(__file__).resolve().parent
SCHEMA = METHODS_DIR / "method.schema.json"  # the format for other tools; never loaded here
DEFAULT = "2012-philox-he"
CUSTOM = "custom"
REPOSITORY = "https://github.com/bushgroup/MOBCAL"
RECORD_JSON = "record.json"
SUFFIX = ".method.json"  # a method file's name: KEY.method.json shipped, NAME.method.json saved

# The shipped method files as committed (LF line endings, see .gitattributes), by key.
SHA256 = {
    "2012-he": "8895d44d884f433427572c41633990afc3acf1d843de65fc1782c60aee505a8f",
    "2012-n2": "de021afd66ccf4e9d3de4f152a95e35cfdcc5df4cedd77e2c0c3594731197a76",
    "2012-philox-he": "80d1cfc6f6c00f2e06a95126591364e901eff83e8f7442900775cfdd05413aaf",
    "2012-philox-n2": "44e74ab1cad7b2c9e8441aad234fe880db562fd03fb68bfcdbd7a0613c5287d2",
    "2000-he": "8acd5a7ba89ff39ee21c60dfd449aecff7b76bbb9aa5b574663b973f8adbd26f",
}

FORMAT = "ccs-method"
FORMERLY = "mobcal-method"  # the format's name before 2.1.0, in development versions only
VERSIONS = (1,)  # the versions this reader takes
VERSION = 1  # the version this writer writes
BLOCK_NAME = "mobcal"  # the block of what only MOBCAL's method has
KEYS = ("format", "version", "name", "description", "gas", "temperature", "seed",
        BLOCK_NAME)  # the core and the block, in the order save writes them
REQUIRED = ("format", "version", "name", "gas", "temperature", BLOCK_NAME)
BLOCK = ("generator", *settings.COUNTS, "parameters")  # every one required, in this order
TEMPERATURE_UNIT = "K"
DEFAULT_SEED = 5013489  # the 2012 seed, batch.DEFAULT_SEED; the first seed without a method seed
MAX_NAME = 60

# What a record written before methods carried their gas says, as the shipped method it was.
ALIASES = {"current": "2012-philox-{gas}", "2012": "2012-{gas}", "2000": "2000-he"}


class MethodError(ValueError):
    """A method file that cannot be used, or a name that is not a method, with the file and
    the key named."""


@dataclass(frozen=True)
class Method:
    name: str  # what the window's list and the record say
    gas: str  # the package's spelling, he | n2
    table: parameters.ParameterSet  # the element table the method carries
    generator: str
    settings: Settings
    path: Path  # the method file
    sha256: str  # of the method file
    shipped: bool = False
    seed: int | None = None  # the method's seed, when its file carries one
    description: str | None = None  # what the method is, when its file says

    @property
    def first_seed(self) -> int:
        """The seed a run of this method starts at without ``--seeds``."""
        return DEFAULT_SEED if self.seed is None else self.seed

    @property
    def key(self) -> str:
        """What a run's record carries: a shipped method's key, or a file's name."""
        return stem(self.path) if self.shipped else self.name

    @property
    def ref(self) -> str:
        """What finds the method again (``get``): a shipped method's key, or the file's path."""
        return stem(self.path) if self.shipped else str(self.path)

    @property
    def title(self) -> str:
        return self.name

    @property
    def set_name(self) -> str | None:
        """The shipped set the table is (``2012``, ``2000``), None for a table of one's own."""
        return self.table.set_name

    @property
    def table_sha256(self) -> str:
        """The SHA-256 of the TOML file the table was taken from."""
        return self.table.sha256

    def job_table(self) -> Path | parameters.ParameterSet | None:
        """The table as a job takes it (``mobcal.run.Job.parameters``): None for the gas's
        default set, a shipped set's file, or the table itself for one of one's own."""
        if self.set_name == parameters.DEFAULT:
            return None
        if self.set_name is not None:
            return parameters.shipped_path(self.gas, self.set_name)
        return self.table

    def overrides(self) -> dict[str, float | int]:
        """The settings that differ from the 2012 values, as ``--temperature`` and the count
        options would give them."""
        return {k: v for k, v in self.settings.values().items() if v != getattr(DEFAULTS, k)}

    def matches(self, gas: str, table_sha256: str | None, generator: str, st: Settings) -> bool:
        """Whether a run of these fields is a run of this method: the same gas, generator and
        settings, and a table taken from the same TOML file (its SHA-256)."""
        return (gas, generator, table_sha256) == (self.gas, self.generator, self.table_sha256) \
            and st.values() == self.settings.values()

    def record(self) -> dict | None:
        """``record.json``'s ``method_file``: a file of one's own, by path and SHA-256."""
        return None if self.shipped else {"path": str(self.path), "sha256": self.sha256}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stem(path: Path | str) -> str:
    """A method file's name without ``.method.json``: a shipped method's key."""
    name = Path(path).name
    return name[:-len(SUFFIX)] if name.lower().endswith(SUFFIX) else Path(path).stem


def file_name(path: Path | str) -> Path:
    """``path`` named as a method file, ``NAME.method.json``: unchanged when it is one, its
    ``.json`` made ``.method.json``, or the suffix added."""
    path = Path(path)
    if path.name.lower().endswith(SUFFIX):
        return path
    if path.suffix.lower() == ".json":
        return path.with_name(path.name[:-len(".json")] + SUFFIX)
    return path.with_name(path.name + SUFFIX)


def _check_name(name: object, where: str) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME \
            or name != name.strip() or not name.isprintable():
        raise MethodError(f"{where}: name must be 1 to {MAX_NAME} printable characters with no "
                          f"space at either end, not {name!r}")
    return name


def load(path: Path | str, shipped: bool = False) -> Method:
    """Read and check a method file. Raises MethodError naming the file and the key."""
    path = Path(path)
    if path.suffix.lower() == ".toml":
        raise MethodError(f"{path}: a TOML method file, which this version of MOBCAL does not "
                          f"read; a method file is JSON, NAME{SUFFIX} (the guide's Methods page "
                          "gives the format)")
    try:
        data = path.read_bytes()
    except OSError as e:
        raise MethodError(f"{path}: cannot read: {e.strerror or e}") from None
    try:
        doc = strictjson.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError as e:
        raise MethodError(f"{path}: not UTF-8 text: {e}") from None
    except strictjson.StrictJSONError as e:
        raise MethodError(f"{path}: {e}") from None
    return from_document(doc, path, hashlib.sha256(data).hexdigest(), shipped)


def _keys(d: dict, allowed: tuple[str, ...], required: tuple[str, ...], where: str,
          what: str) -> None:
    unknown = [k for k in d if k not in allowed]
    if unknown:
        raise MethodError(f"{where}: unknown key {unknown[0]!r}; the keys of {what} are "
                          + ", ".join(allowed))
    missing = [k for k in required if k not in d]
    if missing:
        raise MethodError(f"{where}: no {missing[0]}; {what} needs " + ", ".join(required))


def from_document(doc: object, path: Path | str, sha256: str, shipped: bool = False) -> Method:
    """A method document checked as ``load`` checks a file, ``path`` and ``sha256`` the file's
    it stands for (a document embedded in a result file is read by the same rules). Raises
    MethodError naming ``path`` and the key."""
    path = Path(path)
    if not isinstance(doc, dict):
        raise MethodError(f"{path}: not a method file: the file must be one JSON object")
    # format and version first, so that a file of another version is refused for that alone
    for k in ("format", "version"):
        if k not in doc:
            raise MethodError(f"{path}: no {k}; a method file begins "
                              f'"format": "{FORMAT}", "version": {VERSION}')
    if doc["format"] == FORMERLY:
        raise MethodError(f"{path}: format is {FORMERLY!r}, the name this format had in "
                          "development versions before 2.1.0, which no release wrote; a method "
                          "file now carries its element table, so load a shipped method, set "
                          "the fields again and save it")
    if doc["format"] != FORMAT:
        raise MethodError(f"{path}: format is {doc['format']!r}; this reader reads {FORMAT!r}")
    version = doc["version"]
    if type(version) is not int or version not in VERSIONS:
        raise MethodError(f"{path}: version is {version!r}; this version of MOBCAL reads "
                          f"version {', '.join(map(str, VERSIONS))} of {FORMAT}")
    others = [k for k in doc if k not in KEYS and isinstance(doc[k], dict)]
    if BLOCK_NAME not in doc and len(others) == 1:
        raise MethodError(f"{path}: a method for {others[0]}, whose block it carries; MOBCAL "
                          f"runs a method with a {BLOCK_NAME!r} block")
    _keys(doc, KEYS, REQUIRED, str(path), "a method file")
    name = _check_name(doc["name"], str(path))
    description = doc.get("description")
    if "description" in doc and not isinstance(description, str):
        raise MethodError(f"{path}: description must be a string, not {description!r}")
    formula = doc["gas"]
    gas = next((g for g, f in parameters.GAS.items() if f == formula), None)
    if gas is None:
        raise MethodError(f"{path}: gas is {formula!r}; the gases are "
                          + ", ".join(parameters.GAS.values()))
    t = doc["temperature"]
    if not isinstance(t, dict) or sorted(t) != ["unit", "value"]:
        raise MethodError(f'{path}: temperature must be {{"value": T, "unit": '
                          f'"{TEMPERATURE_UNIT}"}}, not {t!r}')
    if t["unit"] != TEMPERATURE_UNIT:
        raise MethodError(f"{path}: temperature.unit is {t['unit']!r}; it is "
                          f"{TEMPERATURE_UNIT!r}")
    block = doc[BLOCK_NAME]
    where = f"{path}: {BLOCK_NAME}"
    if not isinstance(block, dict):
        raise MethodError(f"{where} must be an object")
    _keys(block, BLOCK, BLOCK, where, f"the {BLOCK_NAME} block")
    generator = block["generator"]
    if not isinstance(generator, str) or generator not in GENERATORS:
        raise MethodError(f"{where}.generator is {generator!r}; the generators are "
                          + ", ".join(GENERATORS))
    try:
        table = parameters.from_document(block["parameters"], f"{where}.parameters", gas=gas)
    except parameters.ParameterError as e:
        raise MethodError(str(e)) from None
    try:
        st = settings.resolve(temperature=t["value"],
                              **{k: block[k] for k in settings.COUNTS})
    except settings.SettingsError as e:
        raise MethodError(f"{path}: {e}") from None
    st = Settings(**st.values())  # a method's settings are its own, none given singly
    seed = doc.get("seed")
    if "seed" in doc and (type(seed) is not int or not 1 <= seed <= MAX_SEED):
        raise MethodError(f"{path}: seed is {seed!r}; a seed is a positive integer up to "
                          f"{MAX_SEED}")
    return Method(name, gas, table, generator, st, path, sha256, shipped, seed, description)


def table_for(table: str | Path | parameters.ParameterSet, gas: str) -> parameters.ParameterSet:
    """A table as a method carries it: a shipped set's name, a TOML file's path, or the table
    itself. Raises MethodError."""
    if isinstance(table, parameters.ParameterSet):
        if table.gas != gas:
            raise MethodError(f"{table.where}: is a table for {parameters.GAS[table.gas]}, not "
                              f"{parameters.GAS[gas]}")
        return table
    try:
        return parameters.load(parameters.path_for(table, gas), gas=gas)
    except parameters.ParameterError as e:
        raise MethodError(str(e)) from None


def plain_number(v: float) -> float | int:
    """A temperature as a document writes it: an integer when it is one."""
    return int(v) if float(v).is_integer() and abs(v) < 2 ** 53 else v


def dumps(doc: dict) -> str:
    """A method document as ``save`` writes it: two-space indent, one key per line, the core's
    keys in ``KEYS`` order and the block's in ``BLOCK`` order, non-ASCII kept, a final
    newline. The table keeps its own order (``ParameterSet.document``)."""
    ordered = {k: doc[k] for k in KEYS if k in doc}
    block = ordered.get(BLOCK_NAME)
    if isinstance(block, dict):
        ordered[BLOCK_NAME] = {k: block[k] for k in BLOCK if k in block} \
            | {k: v for k, v in block.items() if k not in BLOCK}
    return json.dumps(ordered, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def document(name: str, gas: str, table: parameters.ParameterSet, generator: str,
             st: Settings, seed: int | None = None, description: str | None = None) -> dict:
    """A method document with every key in order, as ``save`` writes one: the table whole,
    the temperature an integer when it is one, ``seed`` and ``description`` only when given."""
    doc: dict = {"format": FORMAT, "version": VERSION, "name": name}
    if description:
        doc["description"] = description
    doc["gas"] = parameters.GAS[gas]
    doc["temperature"] = {"value": plain_number(st.temperature), "unit": TEMPERATURE_UNIT}
    if seed is not None:
        doc["seed"] = seed
    doc[BLOCK_NAME] = {"generator": generator, **{k: getattr(st, k) for k in settings.COUNTS},
                       "parameters": table.document()}
    return doc


def save(path: Path | str, name: str, gas: str, table: str | Path | parameters.ParameterSet,
         generator: str, st: Settings, seed: int | None = None,
         description: str | None = None) -> Method:
    """Write a method file with every key, the table whole (a shipped set's name, a TOML
    file's path, or a table already read), and ``seed`` and ``description`` when they are
    given, and return it as ``load`` reads it back. The file is named ``NAME.method.json``
    (``file_name``), whatever ``path`` ends in. Raises MethodError."""
    path = file_name(path)
    _check_name(name, str(path))
    doc = document(name, gas, table_for(table, gas), generator, st, seed, description)
    try:
        path.write_text(dumps(doc), encoding="utf-8", newline="\n")
    except OSError as e:
        raise MethodError(f"{path}: cannot write: {e.strerror or e}") from None
    return load(path)


def shipped_path(key: str) -> Path:
    return METHODS_DIR / f"{key}{SUFFIX}"


METHODS = {key: load(shipped_path(key), shipped=True) for key in SHA256}
TITLES = {**{k: m.title for k, m in METHODS.items()}, CUSTOM: "Custom"}


def get(ref: str | Path) -> Method:
    """A shipped method by its key, or a method file by its path. Raises MethodError."""
    if isinstance(ref, str) and ref in METHODS:
        return METHODS[ref]
    p = Path(ref)
    if p.suffix.lower() not in (".json", ".toml") and not p.exists():
        raise MethodError(f"no method is named {str(ref)!r}; the methods are "
                          + ", ".join(METHODS) + ", or a method file's path")
    return load(p)


def identify(gas: str, table_sha256: str | None, generator: str, st: Settings) -> str:
    """The shipped method whose every field these are, else ``custom``. ``table_sha256`` is
    the SHA-256 of the run's table file (a shipped set's pin for a shipped set)."""
    for m in METHODS.values():
        if m.matches(gas, table_sha256, generator, st):
            return m.key
    return CUSTOM


def verify(methods_dir: Path = METHODS_DIR) -> list[str]:
    """One line per problem with the shipped method files: missing, differing from their pins,
    not loading (which checks each embedded table against its pinned TOML), carrying a table
    of one's own, or named twice. Empty means they are the committed files."""
    problems, names = [], set()
    for key, want in SHA256.items():
        p = methods_dir / f"{key}{SUFFIX}"
        if not p.is_file():
            problems.append(f"{p.name}: missing")
            continue
        got = _sha256(p)
        if got != want:
            problems.append(f"{p.name}: sha256 {got[:12]}... differs from the pinned "
                            f"{want[:12]}...")
        try:
            m = load(p, shipped=True)
        except MethodError as e:
            problems.append(str(e))
            continue
        if m.set_name is None:
            problems.append(f"{p.name}: carries a table of one's own; a shipped method carries "
                            "a shipped set")
        if m.seed is not None:
            problems.append(f"{p.name}: carries a seed; a shipped method carries none")
        if not m.description:
            problems.append(f"{p.name}: carries no description; a shipped method says what "
                            "it is")
        if m.name in names:
            problems.append(f"{p.name}: the name {m.name!r} is another shipped method's")
        names.add(m.name)
    return problems


# --- the methods text -------------------------------------------------------------------------

REFERENCES = {
    "mesleh1996": "Mesleh, M. F.; Hunter, J. M.; Shvartsburg, A. A.; Schatz, G. C.; Jarrold, "
                  "M. F. Structural Information from Ion Mobility Measurements: Effects of the "
                  "Long Range Potential. J. Phys. Chem. 1996, 100, 16082-16086.",
    "shvartsburg1996": "Shvartsburg, A. A.; Jarrold, M. F. An Exact Hard-Spheres Scattering "
                       "Model for the Mobilities of Polyatomic Ions. Chem. Phys. Lett. 1996, "
                       "261, 86-91.",
    "kim2008": "Kim, H.; Kim, H. I.; Johnson, P. V.; Beegle, L. W.; Beauchamp, J. L.; Goddard, "
               "W. A.; Kanik, I. Experimental and Theoretical Investigation into the "
               "Correlation between Mass and Ion Mobility for Choline and Other Ammonium "
               "Cations in N2. Anal. Chem. 2008, 80, 1928-1936.",
    "campuzano2012": "Campuzano, I.; Bush, M. F.; Robinson, C. V.; Beaumont, C.; Richardson, "
                     "K.; Kim, H.; Kim, H. I. Structural Characterization of Drug-like "
                     "Compounds by Ion Mobility Mass Spectrometry: Comparison of Theoretical "
                     "and Experimentally Derived Nitrogen Collision Cross Sections. Anal. Chem. "
                     "2012, 84, 1026-1033.",
    "luscher1994": "Lüscher, M. A Portable High-Quality Random Number Generator for Lattice "
                   "Field Theory Simulations. Comput. Phys. Commun. 1994, 79, 100-110.",
    "james1994": "James, F. RANLUX: A Fortran Implementation of the High-Quality Pseudorandom "
                 "Number Generator of Lüscher. Comput. Phys. Commun. 1994, 79, 111-114.",
    "salmon2011": "Salmon, J. K.; Moraes, M. A.; Dror, R. O.; Shaw, D. E. Parallel Random "
                  "Numbers: As Easy as 1, 2, 3. In Proceedings of the International "
                  "Conference for High Performance Computing, Networking, Storage and Analysis "
                  "(SC11); ACM: New York, 2011; Article 16.",
}
_GAS_WORD = {"he": "helium", "n2": "nitrogen"}
_GENERATOR = {"ranlux": ("RANLUX at luxury level 3", ("luscher1994", "james1994")),
              "philox": ("Philox4x32-10", ("salmon2011",))}
# An import's choice of charges (``mobcal.io.structure``) as a methods section names it.
_SCHEME = {"mulliken": "Mulliken", "lowdin": "Löwdin", "hirshfeld": "Hirshfeld", "cm5": "CM5",
           "chelpg": "CHELPG", "chelp": "CHELP", "mk": "Merz-Kollman",
           "natural": "natural population analysis"}
_INPUT_FILE = {"xyz": ".xyz", "mfj": ".mfj", "MobCal-MPI": "MobCal-MPI .mfj"}


def read_records(paths: Iterable[Path | str]) -> list[dict]:
    """The ``record.json`` of each run directory named, or of every run directory inside each
    folder named, in name order within a folder; and for a result file named, or each one
    directly inside a folder named, what its record would say (``mobcal.io.result``), so that
    a result file sent on describes its run without the run directory. Raises
    FileNotFoundError when a path holds neither, and ResultError for a result file that cannot
    be read."""
    from mobcal.io import result  # it reads method documents with this module

    docs = []
    for p in map(Path, paths):
        if p.is_file() and result.is_result(p):
            docs.append(result.Result.read(p).record())
            continue
        files = [p / RECORD_JSON] if (p / RECORD_JSON).is_file() else \
            sorted(p.glob(f"*/{RECORD_JSON}"))
        loose = [] if (p / RECORD_JSON).is_file() else sorted(p.glob(f"*{result.SUFFIX}"))
        if not files and not loose:
            raise FileNotFoundError(f"no run record or result file in {p}")
        for f in files:
            docs.append(json.loads(f.read_text(encoding="utf-8")))
        docs += [result.Result.read(f).record() for f in loose]
    return docs


def record_method(doc: dict) -> str:
    """A record's method: the name it carries; for a record written before methods carried
    their gas (no ``method_file`` field), the shipped method its name was (``ALIASES``); for
    one written before the field existed, the one ``identify`` finds in it."""
    gas = doc["binary"]["gas"]
    if doc.get("method"):
        if "method_file" not in doc and doc["method"] in ALIASES:
            return ALIASES[doc["method"]].format(gas=gas)
        return doc["method"]
    s = doc["settings"]
    st = Settings(**{k: s[k] for k in settings.NAMES})
    p = doc.get("parameters") or {}
    return identify(gas, p.get("sha256"), doc["mobcal_in"]["generator"], st)


def _cite(keys: Iterable[str], order: list[str]) -> str:
    for k in keys:
        if k not in order:
            order.append(k)
    return ", ".join(str(order.index(k) + 1) for k in keys)


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def charges(inp: dict) -> str | None:
    """What a run's partial charges were, as a methods section says it, from its record's
    ``input`` block; None when the record does not say: a ``.mfj`` input, an ion file without
    an import record, or a record written before ion files' records carried one."""
    imp = inp.get("import")
    if imp is None:
        return None
    mode, src = inp["charge_mode"], imp["source"]
    choice = imp["charges"]["choice"]
    if mode == "none":
        return "not assigned"
    if mode == "equal":  # the 2012 program puts 1/N on every atom, whatever the column holds
        return "+1 e divided equally among the atoms"
    if choice == "uniform":
        return "the net charge divided equally among the atoms"
    if choice == "column" or choice is None:
        return f"those given in the {_INPUT_FILE.get(src['program'], src['program'])} input"
    program = " ".join(p for p in (src["program"], src.get("version")) if p)
    keywords = src.get("keywords")
    if isinstance(keywords, list):
        keywords = " ".join(keywords)
    job = (f"keywords {keywords}" if keywords else
           f"route {src['route']}" if src.get("route") else None)
    return f"the {_SCHEME.get(choice, choice)} charges from {program}" \
        + (f" ({job})" if job else "")


def text(records: list[dict]) -> str:
    """The methods paragraph for these runs, and its references, numbered in order of first
    citation. Runs that share a gas, method, table, settings and generator are described once,
    with their seeds counted. Only completed runs are described; ValueError when there are
    none."""
    done = [d for d in records if d.get("status") == "ok"]
    if not done:
        raise ValueError("no completed run to describe")
    order: list[str] = []
    versions = sorted({d["mobcal_version"] for d in done})
    groups: dict[tuple, list[dict]] = {}
    for d in done:
        s = d["settings"]
        key = (d["binary"]["gas"], record_method(d), d["parameters"]["name"],
               d["parameters"]["sha256"], d["mobcal_in"]["generator"],
               *(s[k] for k in settings.NAMES))
        groups.setdefault(key, []).append(d)

    gases = sorted({k[0] for k in groups}, key=list(_GAS_WORD).index)
    first = ["mesleh1996"] + (["shvartsburg1996"] if "he" in gases else []) \
        + (["kim2008"] if "n2" in gases else []) + ["campuzano2012"]
    program = (f"Collision cross sections were calculated by the trajectory method "
               f"({_cite(first, order)}) in {_join([_GAS_WORD[g] for g in gases])} with "
               f"MOBCAL {_join(versions)} ({REPOSITORY}), which runs the programs of the "
               f"MOBCAL 2012 release ({_cite(['campuzano2012'], order)}).")
    sentences = [program]
    said = [charges(d["input"]) for d in done]
    if all(said):  # every run's charges are on record, or the paragraph says nothing of them
        inputs: dict[str, set[str]] = {}
        for d, s in zip(done, said, strict=True):
            inputs.setdefault(s, set()).add(d["input"]["sha256"])
        if len(inputs) == 1:
            sentences.append(f"The partial charges on the atoms were {said[0]}.")
        else:
            n = {s: len(v) for s, v in inputs.items()}
            sentences.append("The partial charges on the atoms were " + _join(
                [f"{s} for {n[s]} {'ion file' if n[s] == 1 else 'ion files'}"
                 for s in inputs]) + ".")
    for key, docs in groups.items():
        gas, method, table, _, generator, t, imp, itn, inp, inum, inor = key
        what = {f"2012-{gas}": "the method of the MOBCAL 2012 release",
                f"2012-philox-{gas}": "the method of the MOBCAL 2012 release with its random "
                                      "number generator replaced",
                "2000-he": "the method of the 2000 MOBCAL release",
                CUSTOM: "custom settings"}.get(method, f"the method {method}")
        if method == "2000-he":
            what += f" ({_cite(['mesleh1996', 'shvartsburg1996'], order)})"
        gen, gen_refs = _GENERATOR[generator]
        hs = (f", and {inum:,} trajectories with {inor} reflections each for the projection "
              f"approximation and exact hard-sphere scattering") if gas == "he" else ""
        seeds = sorted({d["mobcal_in"]["seed"] for d in docs})
        if len(seeds) == 1:
            seed = f"at seed {seeds[0]}"
        else:
            seed = (f"at {len(seeds)} seeds per structure, and each cross section is the mean "
                    f"and standard deviation over its {len(seeds)} runs")
        sentences.append(
            f"The {_GAS_WORD[gas]} calculations used {what}: the {table} element table, "
            f"{t:g} K, {itn * inp * imp:,} trajectories per structure for the trajectory method "
            f"({itn} cycles of {inp} velocity points of {imp:,} trajectories){hs}, and random "
            f"numbers from {gen} ({_cite(gen_refs, order)}), {seed}.")
    refs = "\n".join(f"{i}. {REFERENCES[k]}" for i, k in enumerate(order, 1))
    return " ".join(sentences) + "\n\n" + refs + "\n"


def summary_line(values: list[float]) -> str:
    """``55.40`` for one value, ``55.40 ± 0.12`` (sample s.d.) for several."""
    if len(values) == 1:
        return f"{values[0]:.2f}"
    return f"{statistics.mean(values):.2f} ± {statistics.stdev(values):.2f}"
