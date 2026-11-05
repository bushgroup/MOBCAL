"""The run settings: the temperature and the five sampling counts, checked and rendered into
every run.

The 2012 programs compiled six run constants into their main program: the temperature,
``t = 301.d0``, and the sampling counts ``imp = 1000`` (trajectories per block of the trajectory
method), ``itn = 10`` (its cycles), ``inp = 40`` (its velocity points), ``inum = 250000``
(trajectories of the projection and hard-sphere pass) and ``inor = 30`` (reflections followed
there). The programs now read them from ``settings.tab`` in the working directory when it is
there and take the 2012 values when it is not. This module holds those values (``DEFAULTS``),
the bounds the programs enforce (``BOUNDS``, ``MAX_POINTS``: the 2012 arrays and output
formats, which ``fortran/mobcal_settings.inc`` declares and ``tools/check_public.py`` compares),
and the rendering.

The six values come from a method (``mobcal.methods``, whose file carries them) and from single
values given on the command line or in the window's fields; there is no settings file of its
own. ``resolve`` applies the precedence a run uses, the 2012 values, then the values given by
name, and the ``Settings`` it returns remembers which were given so that a run's record can
say.

The rendered file is two lines the program reads list-directed: the format line and the six
values. The temperature is written as the 17-significant-digit literal that reads back to the
same double, so ``temperature = 301`` reaches the program as exactly the ``301.d0`` the 2012
source compiled.

    from mobcal import settings
    s = settings.resolve(temperature=298, imp=25)
    s.render(Path("runs/choline-he-5013489-imp25"))
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from pathlib import Path

RENDERED = "settings.tab"  # the file's name in a run directory
MAGIC = "MOBCAL-SETTINGS"  # the first token of a rendered file
RENDERED_FORMAT = 1

NAMES = ("temperature", "imp", "itn", "inp", "inum", "inor")  # the file's and the record's order
COUNTS = NAMES[1:]

# The bounds the program enforces, from the 2012 arrays and formats (mobcal_settings.inc):
# itn and inp index arrays of 100 in MOBIL2, inor arrays of 100 in MOBIL4; imp prints i6, inum
# i7, and the total number of points itn*inp*imp i7.
BOUNDS = {"imp": (1, 999_999), "itn": (1, 100), "inp": (1, 100), "inum": (1, 9_999_999),
          "inor": (1, 100)}
MAX_POINTS = 9_999_999  # itn * inp * imp, the i7 field of "total number of points"
MAX_TEMPERATURE = 1e300  # the program refuses t >= 1.d300 along with NaN and infinity


class SettingsError(ValueError):
    """A setting that cannot be used, with the setting named."""


def temperature_token(t: float) -> str:
    """The rendered temperature: 17 significant digits with a ``d`` exponent, which a REAL(8)
    list-directed read converts back to the same 64-bit pattern."""
    return f"{t:.16e}".replace("e", "d")


def _check_temperature(t: object, where: str) -> float:
    if isinstance(t, bool) or not isinstance(t, (int, float)):
        raise SettingsError(f"{where}: temperature must be a number in kelvin, not {t!r}")
    if not (math.isfinite(t) and 0 < t < MAX_TEMPERATURE):
        raise SettingsError(f"{where}: temperature {t!r} is not a positive number")
    return float(t)


def _check_count(name: str, v: object, where: str) -> int:
    lo, hi = BOUNDS[name]
    if isinstance(v, bool) or not isinstance(v, int):
        raise SettingsError(f"{where}: {name} must be an integer, not {v!r}")
    if not lo <= v <= hi:
        raise SettingsError(f"{where}: {name} is {v}; {lo} to {hi} are allowed")
    return v


@dataclass(frozen=True)
class Source:
    """Which of a run's settings were given singly, over its method's. Empty means the
    method's values, or the defaults."""
    overrides: dict[str, float | int] = field(default_factory=dict)

    def record(self) -> dict:
        return {"overrides": dict(self.overrides)}


@dataclass(frozen=True)
class Settings:
    temperature: float
    imp: int
    itn: int
    inp: int
    inum: int
    inor: int
    source: Source = field(default_factory=Source, compare=False, repr=False)

    def __post_init__(self) -> None:
        where = "settings"
        object.__setattr__(self, "temperature", _check_temperature(self.temperature, where))
        for name in COUNTS:
            _check_count(name, getattr(self, name), where)
        if self.points > MAX_POINTS:
            raise SettingsError(f"{where}: itn*inp*imp is {self.itn}*{self.inp}*{self.imp} = "
                                f"{self.points}; at most {MAX_POINTS} points per coordinate set")

    @property
    def points(self) -> int:
        """Trajectories of the trajectory method per coordinate set."""
        return self.itn * self.inp * self.imp

    @property
    def blocks_per_set(self) -> int:
        """Blocks of ``imp`` trajectories per coordinate set, one per cycle and velocity point:
        what a split run deals among its workers."""
        return self.itn * self.inp

    def values(self) -> dict[str, float | int]:
        return {name: getattr(self, name) for name in NAMES}

    @property
    def is_default(self) -> bool:
        """True when every value is the 2012 one, whatever the source."""
        return self.values() == DEFAULTS.values()

    def suffix(self) -> str:
        """What a run directory's name gains: each value that differs from 2012, in order, as
        ``-t298-imp25``; empty at the 2012 values."""
        parts = []
        for name in NAMES:
            v = getattr(self, name)
            if v != getattr(DEFAULTS, name):
                parts.append(("t" if name == "temperature" else name) + f"{v:g}")
        return "".join("-" + p for p in parts)

    def replace(self, **values: float | int) -> Settings:
        """A copy with some values changed and the source kept."""
        return dataclasses.replace(self, **values)

    def lines(self) -> list[str]:
        """The rendered file, line by line."""
        return [f"{MAGIC} {RENDERED_FORMAT}",
                " ".join([temperature_token(self.temperature)]
                         + [str(getattr(self, c)) for c in COUNTS])]

    def render(self, d: Path) -> Path:
        """Write ``settings.tab`` into ``d`` (LF, ASCII) and return its path."""
        out = Path(d) / RENDERED
        out.write_text("\n".join(self.lines()) + "\n", encoding="ascii", newline="\n")
        return out

    def record(self) -> dict:
        """What a run's record says about its settings."""
        return {**self.values(), "default": self.is_default, "source": self.source.record(),
                "rendered": RENDERED}


DEFAULTS = Settings(301.0, 1000, 10, 40, 250000, 30)
"""The 2012 values: what the programs compute without a settings file."""


def resolve(**overrides: float | int | None) -> Settings:
    """The settings a run uses: the 2012 values, then the ``overrides`` given by name
    (``temperature``, ``imp``, ...; None means not given).

    Raises SettingsError naming the value.
    """
    given = {k: v for k, v in overrides.items() if v is not None}
    unknown = [k for k in given if k not in NAMES]
    if unknown:
        raise SettingsError(f"no setting named {unknown[0]!r}; the settings are "
                            + ", ".join(NAMES))
    values = DEFAULTS.values()
    if "temperature" in given:
        values["temperature"] = _check_temperature(given["temperature"], "--temperature")
    for name in COUNTS:
        if name in given:
            values[name] = _check_count(name, given[name], f"--{name}")
    try:
        return Settings(**values, source=Source(given))
    except SettingsError as e:
        raise SettingsError(str(e).replace("settings:", "the settings given:", 1)) from None


def read_rendered(path: Path | str) -> Settings:
    """A rendered ``settings.tab`` read back, as the program reads it (for the stand-in binary
    and for tests). Raises SettingsError."""
    text = Path(path).read_text(encoding="ascii")
    lines = text.splitlines()
    if len(lines) < 2 or lines[0].split() != [MAGIC, str(RENDERED_FORMAT)]:
        raise SettingsError(f"{path}: not a {MAGIC} {RENDERED_FORMAT} file")
    tokens = lines[1].split()
    if len(tokens) != len(NAMES):
        raise SettingsError(f"{path}: {len(tokens)} values, not {len(NAMES)}")
    try:
        t = float(tokens[0].lower().replace("d", "e"))
        counts = [int(x) for x in tokens[1:]]
    except ValueError:
        raise SettingsError(f"{path}: cannot be read: {lines[1]!r}") from None
    return Settings(t, *counts)
