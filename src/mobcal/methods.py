"""The methods: named presets of everything a calculation depends on but its input and seed.

A method fixes the element table, the random number generator and the six run settings
(``mobcal.settings``) for a gas. Three are named. ``current`` is what ``mobcal run`` does
without options: the 2012 table and settings under Philox4x32-10. ``2012`` is the calculation
of the 2012 release, the same under RANLUX (``docs/mobcal-2012.md``). ``2000`` is the
calculation of the Jarrold group's 2000 helium release: its table, 298 K and ``imp`` 25, under
RANLUX (``docs/mobcal-2000.md``), and has no nitrogen form. The seed is not part of a method: it
belongs to the calculation, and the first seed is the 2012 seed under every method.

``identify`` names the method a run used from what the run used, so a run made with
``--rng ranlux`` and nothing else is a ``2012`` run whether or not ``--method 2012`` was
typed, and a run matching no method is ``custom``; every ``record.json`` carries the name.

``text`` writes the methods paragraph for a set of runs from their records: program and
version, method, gas, table, temperature, trajectory counts, generator, seeds, and the papers
to cite. It is the window's Copy methods text and ``mobcal methods-text``. Until this
package's own paper exists it cites the version and the repository.

    from mobcal import methods
    m = methods.METHODS["2000"]
    m.check_gas("n2")  # MethodError: MOBCAL 2000 is a helium method
    print(methods.text(methods.read_records([Path("runs")])))
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from mobcal import parameters
from mobcal.settings import DEFAULTS, Settings

CURRENT = "current"
CUSTOM = "custom"
REPOSITORY = "https://github.com/bushgroup/MOBCAL"
RECORD_JSON = "record.json"


class MethodError(ValueError):
    """A method asked of a gas it has no form for, or a name that is not a method."""


@dataclass(frozen=True)
class Method:
    key: str  # the name --method takes and the record carries
    title: str  # what the window's dropdown and the methods text say
    gases: tuple[str, ...]
    parameters: str  # a shipped set's name, mobcal.parameters.SETS
    generator: str
    settings: Settings

    def check_gas(self, gas: str) -> None:
        if gas not in self.gases:
            only = " and ".join(parameters.GAS[g] for g in self.gases)
            raise MethodError(f"{self.title} is a method for {only} only, not "
                              f"{parameters.GAS.get(gas, gas)}")

    def overrides(self) -> dict[str, float | int]:
        """The settings that differ from the 2012 values, as ``--temperature`` and the count
        options would give them."""
        return {k: v for k, v in self.settings.values().items() if v != getattr(DEFAULTS, k)}


METHODS = {
    CURRENT: Method(CURRENT, "Current", ("he", "n2"), parameters.DEFAULT, "philox", DEFAULTS),
    "2012": Method("2012", "MOBCAL 2012", ("he", "n2"), "2012", "ranlux", DEFAULTS),
    "2000": Method("2000", "MOBCAL 2000", ("he",), "2000", "ranlux",
                   DEFAULTS.replace(temperature=298.0, imp=25)),
}
TITLES = {**{k: m.title for k, m in METHODS.items()}, CUSTOM: "Custom"}


def get(key: str) -> Method:
    try:
        return METHODS[key]
    except KeyError:
        raise MethodError(f"no method is named {key!r}; the methods are "
                          + ", ".join(METHODS)) from None


def identify(gas: str, set_name: str | None, generator: str, settings: Settings) -> str:
    """The method whose every field these are, else ``custom``. ``set_name`` is the shipped
    set the run's table is by its pin (``ParameterSet.set_name``), None for any other file."""
    for m in METHODS.values():
        if (gas in m.gases and set_name == m.parameters and generator == m.generator
                and settings.values() == m.settings.values()):
            return m.key
    return CUSTOM


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
    """A record's method: the name it carries, or for a record written before the field
    existed, the one ``identify`` finds in it."""
    if doc.get("method"):
        return doc["method"]
    s = doc["settings"]
    st = Settings(**{k: s[k] for k in ("temperature", "imp", "itn", "inp", "inum", "inor")})
    gas = doc["binary"]["gas"]
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
               *(s[k] for k in ("temperature", "imp", "itn", "inp", "inum", "inor")))
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
        what = {CURRENT: "the default method of this version",
                "2012": "the method of the MOBCAL 2012 release",
                "2000": "the method of the 2000 MOBCAL release",
                CUSTOM: "custom settings"}[method]
        if method == "2000":
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
