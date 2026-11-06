"""The result file, ``NAME.result.json`` (``docs/result-file.md``, ``ccs-result`` version 1),
read back: ``Result.read`` checks it and hands the embedded documents to their own readers,
``Result.record`` gives the methods text what it reads from a ``record.json``, and ``unpack``
writes the two inputs back as files and checks them against the hashes the result recorded.

The writer is ``mobcal.run.result_document``; the format's constants are here, so that the
reader need not import the driver. No Qt, no subprocess.

What ``unpack`` can check, and how (each established on the files MOBCAL writes, lab record,
task 57):

- **The ion file.** An ion file input is embedded as the same JSON value, and ``ion.dumps``
  lays a document out as ``Ion.text`` does, in the document's own key order. A given file that
  MOBCAL wrote (``mobcal import``, ``Ion.write``) is therefore written back byte for byte, and
  its SHA-256 is the recorded ``inputs.ion.file.sha256``; a file laid out otherwise is written
  back as the same document in MOBCAL's layout, and the hashes differ, which ``unpack`` reports
  without refusing. A ``.mfj`` input is embedded as the ion document reading it gives, and the
  recorded hash is the ``.mfj``'s, which no ion file can match.
- **The staged input**, for an ion file input: the ``.mfj`` the written ion file gives for the
  run's element table hashes to ``mobcal.staged_input.sha256``, the bytes the program read.
  ``unpack`` refuses a result for which it does not, since the record does not then describe
  one calculation. The table is the one the embedded method carries, shipped or one's own, so
  the check needs no other file and always runs. For a ``.mfj`` input the program read the
  ``.mfj`` as given, and the one the ion file gives holds the same values (``Mfj`` equality)
  in MOBCAL's own layout (``1.0`` for ``1.0000``, wider columns), so no recorded hash can be
  its: ``unpack`` checks that the document was read from the recorded ``.mfj`` and that it
  runs on the table, and says that the bytes differ.
- **The method.** A shipped method or a method file is embedded as its document, and
  ``methods.dumps`` writes back the bytes of every file MOBCAL saved; the recorded
  ``inputs.method.file.sha256`` is compared as for the ion. Every method is checked to make the
  run's calculation: its gas, generator, six settings and the SHA-256 of its table are those the
  result's ``mobcal`` block records. A custom run's method, named ``Custom`` in the result, is
  written under the result's name, so that two unpacked into one Method list do not collide.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from mobcal import methods, settings
from mobcal.io import ion, strictjson
from mobcal.io.ion import Ion, IonError

FORMAT = "ccs-result"
FORMERLY = "ims-result"  # the format's name before 2.1.0, in development versions only
VERSIONS = (1,)  # the versions this reader takes
VERSION = 1  # the version the driver writes
SUFFIX = ".result.json"
GAS_FORMULA = {"he": "He", "n2": "N2"}  # the result's gas, by formula, for each program's gas
GAS = {v: k for k, v in GAS_FORMULA.items()}
KEYS = ("format", "version", "status", "message", "software", "started", "finished", "seconds",
        "gas", "temperature", "seed", "inputs", "results", "mobcal")
ENTRY = {"ion": ("format", "file", "converted_from", "embedded", "document"),
         "method": ("format", "source", "name", "file", "from", "overrides", "embedded",
                    "document")}
MOBCAL = ("generator", "split", "settings", "parameters", "staged_input")


class ResultError(ValueError):
    """A result file that cannot be read back, or unpacked, with the file and the key named."""


def is_result(path: Path | str) -> bool:
    """Whether a path names a result file, by its ending (``.result.json``, any case)."""
    return Path(path).name.lower().endswith(SUFFIX)


def stem(path: Path | str) -> str:
    """A result file's name without ``.result.json``: its run directory's name."""
    name = Path(path).name
    return name[:-len(SUFFIX)] if is_result(name) else Path(path).stem


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get(d: object, keys: tuple[str, ...], where: str) -> dict:
    if not isinstance(d, dict):
        raise ResultError(f"{where} must be an object")
    missing = [k for k in keys if k not in d]
    if missing:
        raise ResultError(f"{where} has no {missing[0]!r}")
    return d


def _file(v: object, where: str) -> dict | None:
    if v is None:
        return None
    f = _get(v, ("name", "sha256"), where)
    if not isinstance(f["name"], str) or not isinstance(f["sha256"], str):
        raise ResultError(f"{where} must hold a name and a SHA-256, as strings")
    return f


@dataclass(frozen=True)
class Result:
    """A result file as read: the document, the embedded ion (None when recorded by reference)
    and the embedded method, both checked by their own readers."""
    path: Path
    doc: dict = field(repr=False)
    ion: Ion | None = field(repr=False)
    method: methods.Method = field(repr=False)

    @classmethod
    def read(cls, path: Path | str) -> Result:
        """Read and check ``path``. Raises ResultError naming the file and the first problem."""
        path = Path(path)
        try:
            data = path.read_bytes()
        except OSError as e:
            raise ResultError(f"{path}: cannot read: {e.strerror or e}") from None
        try:
            return cls.parse(data.decode("utf-8-sig"), path)
        except UnicodeDecodeError as e:
            raise ResultError(f"{path}: not UTF-8 text: {e}") from None

    @classmethod
    def parse(cls, text: str, path: Path | str) -> Result:
        """A result file's text, ``path`` naming it in refusals."""
        path = Path(path)
        try:
            return cls._check(strictjson.loads(text), path)
        except strictjson.StrictJSONError as e:
            raise ResultError(f"{path}: {e}") from None
        except ResultError as e:
            raise ResultError(f"{path}: {e}") from None

    @classmethod
    def _check(cls, doc: object, path: Path) -> Result:
        if not isinstance(doc, dict):
            raise ResultError("not a result file: the file must be one JSON object")
        # format and version first, so that a file of another version is refused for that alone
        for k in ("format", "version"):
            if k not in doc:
                raise ResultError(f'no {k}; a result file begins "format": "{FORMAT}", '
                                  f'"version": {VERSION}')
        if doc["format"] == FORMERLY:
            raise ResultError(f"format is {FORMERLY!r}: the file was written by a development "
                              "version before 2.1.0, under the name this format had then, which "
                              "no release wrote; the run's record.json beside it is its record")
        if doc["format"] != FORMAT:
            raise ResultError(f"format is {doc['format']!r}; this reader reads {FORMAT!r}")
        if type(doc["version"]) is not int or doc["version"] not in VERSIONS:
            raise ResultError(f"version is {doc['version']!r}; this version of MOBCAL reads "
                              f"version {', '.join(map(str, VERSIONS))} of {FORMAT}")
        _get(doc, KEYS, "the document")
        if doc["gas"] not in GAS:
            raise ResultError(f"gas is {doc['gas']!r}; MOBCAL's gases are "
                              + ", ".join(GAS))
        seed = doc["seed"]
        if type(seed) is not int:
            raise ResultError(f"seed is {seed!r}, not an integer")
        inputs = _get(doc["inputs"], ("ion", "method"), "inputs")
        mb = _get(doc["mobcal"], MOBCAL, "mobcal")
        _get(mb["parameters"], ("name", "sha256", "shipped"), "mobcal.parameters")
        _file(mb["staged_input"], "mobcal.staged_input")
        st = _get(mb["settings"], settings.NAMES, "mobcal.settings")
        try:
            settings.Settings(**{k: st[k] for k in settings.NAMES})
        except (TypeError, ValueError) as e:
            raise ResultError(f"mobcal.settings: {e}") from None

        ie = _get(inputs["ion"], ENTRY["ion"], "inputs.ion")
        if ie["format"] != ion.FORMAT:
            raise ResultError(f"inputs.ion.format is {ie['format']!r}, not {ion.FORMAT!r}")
        if _file(ie["file"], "inputs.ion.file") is None:
            raise ResultError("inputs.ion.file is null; the ion is named by its file")
        if ie["converted_from"] not in (None, "mfj"):
            raise ResultError(f"inputs.ion.converted_from is {ie['converted_from']!r}; it is "
                              "mfj or null")
        if ie["embedded"] is not (ie["document"] is not None):
            raise ResultError("inputs.ion.embedded does not say whether document holds the ion")
        the_ion = None
        if ie["embedded"]:
            try:
                the_ion = Ion.from_dict(ie["document"])
            except IonError as e:
                raise ResultError(f"inputs.ion.document: {e}") from None

        me = _get(inputs["method"], ENTRY["method"], "inputs.method")
        if me["format"] != methods.FORMAT:
            raise ResultError(f"inputs.method.format is {me['format']!r}, not "
                              f"{methods.FORMAT!r}")
        if me["source"] not in ("shipped", "file", "custom"):
            raise ResultError(f"inputs.method.source is {me['source']!r}; it is shipped, file "
                              "or custom")
        f = _file(me["file"], "inputs.method.file")
        if (f is None) is not (me["source"] == "custom"):
            raise ResultError("inputs.method.file is null exactly for a custom method")
        if me["embedded"] is not True or me["document"] is None:
            raise ResultError("inputs.method holds no document; every result embeds its method")
        name = f["name"] if f else f"{stem(path)}{methods.SUFFIX}"
        try:
            m = methods.from_document(me["document"], path.with_name(name),
                                      f["sha256"] if f else "", me["source"] == "shipped")
        except methods.MethodError as e:
            raise ResultError(f"inputs.method.document: {e}") from None
        return cls(path, doc, the_ion, m)

    # --- what the document says ------------------------------------------------------------

    @property
    def name(self) -> str:
        """The run directory's name, the file's without ``.result.json``."""
        return stem(self.path)

    @property
    def status(self) -> str:
        return self.doc["status"]

    @property
    def gas(self) -> str:
        """The program's gas, ``he`` or ``n2``."""
        return GAS[self.doc["gas"]]

    @property
    def seed(self) -> int:
        return self.doc["seed"]

    @property
    def ion_entry(self) -> dict:
        return self.doc["inputs"]["ion"]

    @property
    def method_entry(self) -> dict:
        return self.doc["inputs"]["method"]

    @property
    def embedded(self) -> bool:
        """Whether the ion is in the file, not named by its file alone."""
        return self.ion is not None

    @property
    def settings(self) -> settings.Settings:
        s = self.doc["mobcal"]["settings"]
        return settings.Settings(**{k: s[k] for k in settings.NAMES})

    def record(self) -> dict:
        """What ``methods.text`` reads from a run's ``record.json``, from this file: the same
        keys, filled from the result's own. The charges are said as the record says them, for
        an ion file with an import record; a ``.mfj`` input's or a referenced ion's are not."""
        mb, me, ie = self.doc["mobcal"], self.method_entry, self.ion_entry
        inp: dict = {"path": ie["file"]["name"], "sha256": ie["file"]["sha256"]}
        if ie["converted_from"] is None:
            inp["format"] = ion.FORMAT
            if self.ion is not None:
                inp |= ion.charges_record(self.ion)
        return {
            "mobcal_version": self.doc["software"]["version"],
            "name": self.name,
            "binary": {"gas": self.gas},
            "input": inp,
            "mobcal_in": {"seed": self.seed, "generator": mb["generator"],
                          "split": mb["split"]},
            "method": me["name"],
            "method_file": me["file"],
            "parameters": dict(mb["parameters"]),
            "settings": dict(mb["settings"]),
            "status": self.status,
        }


# --- unpack ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Written:
    """One file ``unpack`` wrote, or found already there with the same bytes."""
    path: Path
    sha256: str
    recorded: str | None  # the SHA-256 the result records for the file the run was given
    existed: bool = False  # the file was there already, byte for byte

    @property
    def identical(self) -> bool:
        """Whether the bytes written are those of the file the run was given."""
        return self.sha256 == self.recorded


@dataclass(frozen=True)
class Unpacked:
    ion: Written
    method: Written
    converted_from: str | None  # "mfj" when the run's input was a .mfj, written as an ion file
    # the staged .mfj's SHA-256 reproduced: True; False for a .mfj input, whose bytes the ion
    # file cannot reproduce (its values it does)
    staged: bool
    notes: tuple[str, ...]  # what the files are, beyond the hashes, for the person unpacking
    rerun: tuple[str, ...]  # the arguments of the command that runs the calculation again

    @property
    def command(self) -> str:
        """``rerun`` as a line to type into this platform's shell."""
        return " ".join(_quote(a) for a in self.rerun)


def _quote(arg: str) -> str:
    return subprocess.list2cmdline([arg]) if os.name == "nt" else shlex.quote(arg)


def unpack(r: Result, out_dir: Path | str = ".", force: bool = False) -> Unpacked:
    """Write the result's ion and method into ``out_dir`` as ``NAME.ion.json`` and
    ``NAME.method.json`` and check them (the module's docstring says how). The ion file takes
    the name of the run's input (its own for an ion file, ``X.ion.json`` for ``X.mfj``), so that a
    run of it is named as the original was; the method file takes its file's name, or for a
    custom method the result's name, which also becomes the method's.

    Refuses, writing nothing, a result whose ion is recorded by reference, one whose method or
    staged input does not agree with its ``mobcal`` block, and a file already there with other
    bytes unless ``force``. Raises ResultError, or OSError from writing."""
    out_dir = Path(out_dir)
    ie, me, mb = r.ion_entry, r.method_entry, r.doc["mobcal"]
    where = r.path.name
    if r.ion is None:
        f = ie["file"]
        raise ResultError(f"{where}: the ion was recorded by reference, as {f['name']} "
                          f"(SHA-256 {f['sha256']}), so the result file does not hold it; "
                          "the file of that name and hash is the run's ion")

    # the method makes the run's calculation
    m = r.method
    for what, have, want in (("gas", m.gas, r.gas), ("generator", m.generator, mb["generator"]),
                             ("settings", m.settings.values(), r.settings.values()),
                             ("element table's SHA-256", m.table_sha256,
                              mb["parameters"]["sha256"])):
        if have != want:
            raise ResultError(f"{where}: the embedded method's {what} is {have!r} and the run's "
                              f"was {want!r}; the file does not describe one calculation")

    notes = []
    # the ion, under the input's name
    given = ie["file"]["name"]
    ion_name = f"{ion.stem(given)}{ion.SUFFIX}"
    ion_text = ion.dumps(ie["document"]).encode("utf-8")
    if ie["converted_from"] == "mfj":
        notes.append(f"the run's input was {given}, a .mfj, which the result holds as the ion "
                     f"document reading it gives; {ion_name} is that document")

    # the staged .mfj, from the ion as written, for the run's table
    table = m.table
    source = (r.ion.import_record or {}).get("source", {})
    if ie["converted_from"] == "mfj" and source.get("sha256") not in (None, ie["file"]["sha256"]):
        raise ResultError(f"{where}: the embedded ion was read from a .mfj of SHA-256 "
                          f"{source['sha256']}, not the run's {ie['file']['sha256']}")
    try:
        data = Ion.parse(ion_text.decode("utf-8")).mfj(table).text().encode("latin-1")
    except IonError as e:
        raise ResultError(f"{where}: the embedded ion does not run on the run's element "
                          f"table: {e}") from None
    want = mb["staged_input"]["sha256"]
    if ie["converted_from"] == "mfj":
        # The program read the .mfj as given; the one this ion gives holds the same values
        # in MOBCAL's layout, so no recorded hash can be its (lab record, task 57).
        staged = False
        notes.append(f"the .mfj this ion file gives holds the values the program read from "
                     f"{given}, laid out as MOBCAL writes a .mfj, so its SHA-256 is not "
                     f"the recorded one, which is {given}'s own; the result records no "
                     "hash of the values alone")
    elif _sha256(data) != want:
        raise ResultError(f"{where}: the .mfj the embedded ion gives for the run's element "
                          f"table has SHA-256 {_sha256(data)}, not the {want} the program "
                          "read; the file does not describe one calculation")
    else:
        staged = True

    # the method, under its file's name, or the result's for a custom method
    doc = dict(me["document"])
    if me["source"] == "custom":
        doc["name"] = r.name[:methods.MAX_NAME].strip() or "Custom"
        method_name = f"{r.name}{methods.SUFFIX}"
    else:
        method_name = me["file"]["name"]
    method_text = methods.dumps(doc).encode("utf-8")

    files = ((out_dir / ion_name, ion_text, ie["file"]["sha256"]),
             (out_dir / method_name, method_text, me["file"]["sha256"] if me["file"] else None))
    existed = {}
    for path, data, _ in files:
        existed[path] = path.is_file() and path.read_bytes() == data
        if path.exists() and not existed[path] and not force:
            raise ResultError(f"{path} exists with other contents; not replacing it (--force "
                              "replaces it)")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for path, data, recorded in files:
        if not existed[path]:
            path.write_bytes(data)
        written.append(Written(path, _sha256(data), recorded, existed[path]))

    rerun = ["mobcal", "run", str(written[0].path), "--method"]
    shipped = methods.METHODS.get(me["name"]) if me["source"] == "shipped" else None
    if shipped is not None and shipped.sha256 == me["file"]["sha256"]:
        rerun.append(me["name"])  # the shipped method itself, which the record then names
    else:
        rerun.append(str(written[1].path))
    rerun += ["--seeds", str(r.seed)]
    if mb["split"] is not None:
        rerun += ["--split", str(mb["split"])]
    return Unpacked(written[0], written[1], ie["converted_from"], staged, tuple(notes),
                    tuple(rerun))
