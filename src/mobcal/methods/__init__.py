"""The methods: everything a calculation depends on but its input and its seed, in one file.

A method is the gas, the element table, the random number generator and the six run settings
(``mobcal.settings``). It is a TOML file (``load``, ``save``), and five ship beside this module,
pinned like the element tables (``SHA256``, ``verify``), each known by its file's stem:

    2012-he, 2012-n2              the calculation of the 2012 release: its tables and settings
                                  under RANLUX, which reproduces the 2012 outputs at the 2012 seed
    2012-philox-he, 2012-philox-n2  the same tables and settings under Philox4x32-10, whose
                                  divided runs give the serial result exactly; 2012-philox-he
                                  is the default of ``mobcal run`` and of the window
    2000-he                       the Jarrold group's 2000 helium release: its table, 298 K and
                                  ``imp`` 25, under RANLUX; it has no nitrogen form

A method file of one's own follows the same format, ``format = 1``:

    format = 1
    name = "My method"          1 to 60 characters, shown in the window and recorded by runs
    gas = "he"                  he or n2
    parameters = "2012"         a shipped set's name, or a table:
                                [parameters] path = "...", sha256 = "..."
    generator = "philox"        philox or ranlux
    temperature = 301           the six settings; a key left out takes the 2012 value
    imp = 1000  ...

The first five keys are required and an unknown key is refused by name. A table of one's own
is named by its path, relative to the method file's folder unless absolute, and its SHA-256:
loading the method refuses it, saying which, when the table has moved or changed. The seed is
not part of a method: it belongs to the calculation, and the first seed is the 2012 seed under
every method.

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
    methods.save(Path("mine.toml"), "Mine", "he", "2012", "philox", m.settings)
    print(methods.text(methods.read_records([Path("runs")])))
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from mobcal import parameters, settings
from mobcal.io.infile import GENERATORS
from mobcal.settings import DEFAULTS, Settings

METHODS_DIR = Path(__file__).resolve().parent
DEFAULT = "2012-philox-he"
CUSTOM = "custom"
REPOSITORY = "https://github.com/bushgroup/MOBCAL"
RECORD_JSON = "record.json"

# The shipped method files as committed (LF line endings, see .gitattributes), by key.
SHA256 = {
    "2012-he": "9e0a49cfc07635673ce1ae175932f181b77de794ba0b31410a29a60bfeb94ef4",
    "2012-n2": "6d6684ba2716913838f2a3de9da1c5b453e05858ec93a215931fdae48760c518",
    "2012-philox-he": "17d80d64848b1dfefacf45a9c90c915b7b1e09c3e970aaa7e64aaf753ac7a1fe",
    "2012-philox-n2": "e0fa6d07e7e045be7e812a31c3a60cc36ccebc98a61e7faed35aae68463fea17",
    "2000-he": "d9682786413011e9688d1615e925a3e5604a45dcc66aa64c1e9a29a9c63f3781",
}

FORMATS = (1,)
REQUIRED = ("format", "name", "gas", "parameters", "generator")
KEYS = (*REQUIRED, *settings.NAMES)
MAX_NAME = 60

# What a record written before methods carried their gas says, as the shipped method it was.
ALIASES = {"current": "2012-philox-{gas}", "2012": "2012-{gas}", "2000": "2000-he"}


class MethodError(ValueError):
    """A method file that cannot be used, or a name that is not a method, with the file and
    the key named."""


@dataclass(frozen=True)
class Method:
    name: str  # what the window's list and the record say
    gas: str
    parameters: str | None  # a shipped set's name (mobcal.parameters.SETS), or None ...
    table: Path | None  # ... for a table of one's own, by path
    table_sha256: str | None  # and the SHA-256 the method file pins it at
    generator: str
    settings: Settings
    path: Path  # the method file
    sha256: str  # of the method file
    shipped: bool = False

    @property
    def key(self) -> str:
        """What a run's record carries: a shipped method's key, or a file's name."""
        return self.path.stem if self.shipped else self.name

    @property
    def ref(self) -> str:
        """What finds the method again (``get``): a shipped method's key, or the file's path."""
        return self.path.stem if self.shipped else str(self.path)

    @property
    def title(self) -> str:
        return self.name

    def table_path(self) -> Path | None:
        """The element table file, None for the gas's default set."""
        if self.table is not None:
            return self.table
        return None if self.parameters == parameters.DEFAULT else \
            parameters.shipped_path(self.gas, self.parameters)

    def overrides(self) -> dict[str, float | int]:
        """The settings that differ from the 2012 values, as ``--temperature`` and the count
        options would give them."""
        return {k: v for k, v in self.settings.values().items() if v != getattr(DEFAULTS, k)}

    def matches(self, gas: str, set_name: str | None, table_sha256: str | None,
                generator: str, st: Settings) -> bool:
        """Whether a run of these fields is a run of this method. ``set_name`` is the shipped
        set the run's table is by its pin, ``table_sha256`` the table file's hash."""
        if (gas, generator) != (self.gas, self.generator) or st.values() != \
                self.settings.values():
            return False
        if self.table is None:
            return set_name == self.parameters
        return table_sha256 == self.table_sha256

    def record(self) -> dict | None:
        """``record.json``'s ``method_file``: a file of one's own, by path and SHA-256."""
        return None if self.shipped else {"path": str(self.path), "sha256": self.sha256}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_name(name: object, where: str) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME \
            or name != name.strip() or not name.isprintable():
        raise MethodError(f"{where}: name must be 1 to {MAX_NAME} printable characters with no "
                          f"space at either end, not {name!r}")
    return name


def load(path: Path | str, shipped: bool = False) -> Method:
    """Read and check a method file. A table of one's own must be where the file says, with
    the SHA-256 it says. Raises MethodError naming the file and the key."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as e:
        raise MethodError(f"{path}: cannot read: {e.strerror or e}") from None
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise MethodError(f"{path}: not a TOML file: {e}") from None
    unknown = [k for k in doc if k not in KEYS]
    if unknown:
        raise MethodError(f"{path}: unknown key {unknown[0]!r}; the keys are "
                          + ", ".join(KEYS))
    missing = [k for k in REQUIRED if k not in doc]
    if missing:
        raise MethodError(f"{path}: no {missing[0]}; a method file needs "
                          + ", ".join(REQUIRED))
    fmt = doc["format"]
    if type(fmt) is not int or fmt not in FORMATS:
        raise MethodError(f"{path}: format is {fmt!r}; this version of mobcal reads format "
                          + ", ".join(map(str, FORMATS)))
    name = _check_name(doc["name"], str(path))
    gas = doc["gas"]
    if gas not in parameters.SETS:
        raise MethodError(f"{path}: gas is {gas!r}; the gases are " + ", ".join(parameters.SETS))
    generator = doc["generator"]
    if generator not in GENERATORS:
        raise MethodError(f"{path}: generator is {generator!r}; the generators are "
                          + ", ".join(GENERATORS))
    set_name, table, table_sha = _table(doc["parameters"], gas, path)
    try:
        st = settings.resolve(None, **{k: doc[k] for k in settings.NAMES if k in doc})
    except settings.SettingsError as e:
        raise MethodError(f"{path}: {e}") from None
    st = Settings(**st.values())  # a method's settings are its own, from no settings file
    return Method(name, gas, set_name, table, table_sha, generator, st, path,
                  hashlib.sha256(data).hexdigest(), shipped)


def _table(value: object, gas: str, path: Path) -> tuple[str | None, Path | None, str | None]:
    if isinstance(value, str):
        if value not in parameters.SETS[gas]:
            raise MethodError(f"{path}: parameters is {value!r}; the shipped "
                              f"{parameters.GAS[gas]} tables are "
                              + ", ".join(parameters.SETS[gas]))
        return value, None, None
    if not isinstance(value, dict) or sorted(value) != ["path", "sha256"] \
            or not all(isinstance(v, str) for v in value.values()):
        raise MethodError(f"{path}: parameters must be a shipped table's name or a table with "
                          "path and sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
        raise MethodError(f"{path}: parameters.sha256 must be 64 lowercase hex digits")
    table = Path(value["path"])
    if not table.is_absolute():
        table = path.resolve().parent / table
    if not table.is_file():
        raise MethodError(f"{path}: its element table {table} is not there; it has moved or "
                          "been deleted")
    if _sha256(table) != value["sha256"]:
        raise MethodError(f"{path}: its element table {table} has changed since the method was "
                          "saved (its SHA-256 differs)")
    try:
        parameters.load(table, gas=gas)
    except parameters.ParameterError as e:
        raise MethodError(f"{path}: its element table: {e}") from None
    return None, table, value["sha256"]


def _toml_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a TOML basic string


def save(path: Path | str, name: str, gas: str, table: str | Path, generator: str,
         st: Settings) -> Method:
    """Write a method file with every key, a table of one's own by its absolute path and its
    SHA-256 now, and return it as ``load`` reads it back. ``table`` is a shipped set's name or a
    path. Raises MethodError."""
    path = Path(path)
    _check_name(name, str(path))
    lines = ["format = 1", f"name = {_toml_string(name)}", f"gas = {_toml_string(gas)}"]
    if isinstance(table, str) and table in parameters.SETS.get(gas, {}):
        lines.append(f"parameters = {_toml_string(table)}")
        tail = []
    else:
        t = Path(table).resolve()
        try:
            sha = _sha256(t)
        except OSError as e:
            raise MethodError(f"{t}: cannot read: {e.strerror or e}") from None
        tail = ["", "[parameters]", f"path = {_toml_string(t.as_posix())}",
                f"sha256 = {_toml_string(sha)}"]
    lines.append(f"generator = {_toml_string(generator)}")
    lines.append(f"temperature = {st.temperature:g}" if st.temperature == int(st.temperature)
                 else f"temperature = {st.temperature!r}")
    lines += [f"{k} = {getattr(st, k)}" for k in settings.COUNTS]
    try:
        path.write_text("\n".join(lines + tail) + "\n", encoding="utf-8", newline="\n")
    except OSError as e:
        raise MethodError(f"{path}: cannot write: {e.strerror or e}") from None
    return load(path)


def shipped_path(key: str) -> Path:
    return METHODS_DIR / f"{key}.toml"


METHODS = {key: load(shipped_path(key), shipped=True) for key in SHA256}
TITLES = {**{k: m.title for k, m in METHODS.items()}, CUSTOM: "Custom"}


def get(ref: str | Path) -> Method:
    """A shipped method by its key, or a method file by its path. Raises MethodError."""
    if isinstance(ref, str) and ref in METHODS:
        return METHODS[ref]
    p = Path(ref)
    if p.suffix.lower() != ".toml" and not p.exists():
        raise MethodError(f"no method is named {str(ref)!r}; the methods are "
                          + ", ".join(METHODS) + ", or a method file's path")
    return load(p)


def identify(gas: str, set_name: str | None, generator: str, st: Settings) -> str:
    """The shipped method whose every field these are, else ``custom``. ``set_name`` is the
    shipped set the run's table is by its pin (``ParameterSet.set_name``), None for any other
    file."""
    for m in METHODS.values():
        if m.matches(gas, set_name, None, generator, st):
            return m.key
    return CUSTOM


def verify(methods_dir: Path = METHODS_DIR) -> list[str]:
    """One line per problem with the shipped method files: missing, differing from their pins,
    not loading, or named twice. Empty means they are the committed files."""
    problems, names = [], set()
    for key, want in SHA256.items():
        p = methods_dir / f"{key}.toml"
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
        if m.table is not None:
            problems.append(f"{p.name}: names a table by path; a shipped method names a set")
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


def read_records(paths: Iterable[Path | str]) -> list[dict]:
    """The ``record.json`` of each run directory named, or of every run directory inside each
    folder named, in name order within a folder. Raises FileNotFoundError when a path holds no
    record at all."""
    docs = []
    for p in map(Path, paths):
        files = [p / RECORD_JSON] if (p / RECORD_JSON).is_file() else \
            sorted(p.glob(f"*/{RECORD_JSON}"))
        if not files:
            raise FileNotFoundError(f"no run record in {p}")
        for f in files:
            docs.append(json.loads(f.read_text(encoding="utf-8")))
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
    set_name = next((n for n, f in parameters.SETS[gas].items()
                     if p.get("sha256") == parameters.SHA256[f]), None)
    return identify(gas, set_name, doc["mobcal_in"]["generator"], st)


def _cite(keys: Iterable[str], order: list[str]) -> str:
    for k in keys:
        if k not in order:
            order.append(k)
    return ", ".join(str(order.index(k) + 1) for k in keys)


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


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
