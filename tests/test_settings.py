"""The run settings: the TOML is checked and pinned, the rendered file reads back to the bit,
the 2012 values are the program's own defaults, other values equal a build with them compiled
in, a split run is exact at any of them, and both sides refuse what the other does.

``mobcal.settings`` holds the temperature and the five sampling counts that the 2012 programs
compiled in; ``fortran/mobcal_settings.inc`` reads them from ``settings.tab`` when the file is
there. Four things are held here with the real binaries. The rendered temperature reads back
as the same 64-bit pattern (``setprobe.f`` compiled with the pinned include), and without a
file the reader's values are the 2012 ones. An output at other settings is byte-identical to
the output of a binary built from a copy of the sources with those values written into the
reader's defaults and no file, which is the oracle for "equals a compiled build": choline in
helium at 298 K and ``imp = 25`` (the 2000 release's settings) and in nitrogen at 350 K,
``imp = 10``, ``itn = 5``, ``inp = 20``. A split run at ``itn = 3``, ``inp = 7`` reproduces the
serial run under both generators, 21 blocks dealt among four workers. And every refusal of the
program on an edited ``settings.tab`` is driven, along with a combining run that finds a block
integrated under other settings.
"""

from __future__ import annotations

import difflib
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import gate
from mobcal import cli, fortran, parameters, settings
from mobcal.io.block import Block
from mobcal.io.infile import InFile
from mobcal.io.outfile import OutFile
from mobcal.run import OUTPUT_NAME, Job, run_many, run_one
from mobcal.settings import DEFAULTS, Settings, SettingsError
from test_split import shared

SETPROBE = Path(__file__).resolve().parent / "setprobe.f"
INCLUDE = "mobcal_settings.inc"
RENDERED = "MOBCAL-SETTINGS 1\n3.0100000000000000d+02 1000 10 40 250000 30\n"

# Hydrogen bromide, refused for its bromine (key 35) in well under a second, once the settings
# have been read: the settings refusals come first, and are the output's only line.
_HBR = "HBr+\n1\n2\nang\ncalc\n1.0000\n 0 0 0 35 0.5\n 1.41 0 0 1 0.5\n"


# --- the module -----------------------------------------------------------------------------

def test_the_defaults_are_the_2012_values_and_the_shipped_file_holds_them():
    assert DEFAULTS.values() == {"temperature": 301.0, "imp": 1000, "itn": 10, "inp": 40,
                                 "inum": 250000, "inor": 30}
    assert DEFAULTS.blocks_per_set == 400 and DEFAULTS.points == 400_000
    assert settings.verify() == []
    s = settings.shipped()
    assert s == DEFAULTS and s.is_default and s.source.path == settings.default_path()
    assert s.suffix() == "" and DEFAULTS.suffix() == ""
    assert s.lines() == RENDERED.splitlines()


def test_the_rendered_file_and_its_read_back(tmp_path):
    p = DEFAULTS.render(tmp_path)
    assert p == tmp_path / "settings.tab" and p.read_bytes() == RENDERED.encode()
    assert settings.read_rendered(p) == DEFAULTS
    s = Settings(298.15, 25, 3, 7, 200, 5)
    assert settings.read_rendered(s.render(tmp_path)) == s
    # 298.15 is not representable; the token is the double's own 17 digits, which read back.
    assert s.lines()[1] == "2.9814999999999998d+02 25 3 7 200 5"
    assert float("2.9814999999999998e+02") == 298.15
    with pytest.raises(SettingsError, match="not a MOBCAL-SETTINGS 1 file"):
        settings.read_rendered(Path(p).write_text("MOBCAL-X 1\n1 1 1 1 1 1\n") and p)


@pytest.mark.parametrize("t", [301, 298, 298.15, 80.5, 1e-3, 6000, 0.1 + 0.2, 1 / 3])
def test_the_temperature_token_round_trips(t):
    tok = settings.temperature_token(t)
    assert re.fullmatch(r"\d\.\d{16}d[+-]\d\d", tok), tok
    assert float(tok.replace("d", "e")) == float(t)


def test_resolve_applies_defaults_then_the_file_then_the_values(tmp_path):
    f = tmp_path / "mine.toml"
    f.write_text("format = 1\nimp = 25\ntemperature = 298\n", encoding="utf-8")
    s = settings.resolve(f, itn=3)
    assert s.values() == {"temperature": 298.0, "imp": 25, "itn": 3, "inp": 40,
                          "inum": 250000, "inor": 30}
    assert s.source.path == f and s.source.overrides == {"itn": 3} and len(s.source.sha256) == 64
    assert s.suffix() == "-t298-imp25-itn3" and not s.is_default
    assert settings.resolve(f, imp=1000, temperature=301).is_default
    assert settings.resolve(None).source == settings.Source()
    assert settings.resolve(None, temperature=None, imp=None) == DEFAULTS
    assert settings.resolve(None, temperature=298.15).suffix() == "-t298.15"
    rec = s.record()
    assert rec["default"] is False and rec["rendered"] == "settings.tab"
    assert rec["source"] == {"path": str(f), "sha256": s.source.sha256, "overrides": {"itn": 3}}
    with pytest.raises(SettingsError, match="no setting named 'imq'"):
        settings.resolve(None, imq=1)


REFUSALS = {
    "unknown key": ("format = 1\nimq = 25\n", "unknown key 'imq'"),
    "format": ("format = 2\nimp = 25\n", "format is 2"),
    "no format": ("imp = 25\n", "format is None"),
    "count float": ("format = 1\nimp = 25.0\n", "imp must be an integer"),
    "count string": ("format = 1\ninp = \"40\"\n", "inp must be an integer"),
    "count bool": ("format = 1\ninor = true\n", "inor must be an integer"),
    "imp 0": ("format = 1\nimp = 0\n", "imp is 0; 1 to 999999 are allowed"),
    "imp over": ("format = 1\nimp = 1000000\n", "imp is 1000000; 1 to 999999 are allowed"),
    "itn over": ("format = 1\nitn = 101\n", "itn is 101; 1 to 100 are allowed"),
    "inp over": ("format = 1\ninp = 101\n", "inp is 101; 1 to 100 are allowed"),
    "inum over": ("format = 1\ninum = 10000000\n", "inum is 10000000; 1 to 9999999"),
    "inor over": ("format = 1\ninor = 101\n", "inor is 101; 1 to 100 are allowed"),
    "product": ("format = 1\nitn = 100\ninp = 100\n", "itn\\*inp\\*imp is 100\\*100\\*1000"),
    "t string": ("format = 1\ntemperature = \"301.d0\"\n", "temperature must be a number"),
    "t zero": ("format = 1\ntemperature = 0\n", "temperature 0 is not a positive number"),
    "t negative": ("format = 1\ntemperature = -5.0\n", "temperature -5.0 is not a positive"),
    "t nan": ("format = 1\ntemperature = nan\n", "temperature nan is not a positive number"),
    "t inf": ("format = 1\ntemperature = inf\n", "temperature inf is not a positive number"),
    "not toml": ("format = \n", "not a TOML file"),
}


@pytest.mark.parametrize("case", REFUSALS)
def test_a_settings_file_is_refused_naming_the_key(tmp_path, case):
    text, match = REFUSALS[case]
    f = tmp_path / "bad.toml"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(SettingsError, match=re.escape(str(f)) + ".*" + match):
        settings.load(f)


def test_values_given_singly_are_refused_the_same_way():
    with pytest.raises(SettingsError, match="--inp: inp is 101"):
        settings.resolve(None, inp=101)
    with pytest.raises(SettingsError, match="--temperature: temperature 0 is not"):
        settings.resolve(None, temperature=0)
    with pytest.raises(SettingsError, match="itn\\*inp\\*imp is 100\\*100\\*1000"):
        settings.resolve(None, itn=100, inp=100)
    with pytest.raises(SettingsError, match="imp is 0"):
        Settings(301.0, 0, 10, 40, 250000, 30)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(SettingsError, match="cannot read"):
        settings.load(tmp_path / "none.toml")


# --- the job, the command line and the split bound -----------------------------------------

def test_a_jobs_settings_name_its_directory_and_bound_its_split(tmp_path):
    s = settings.resolve(None, temperature=298, imp=25)
    job = Job(Path("a10A1.mfj"), "he", 5013486, tmp_path, generator="ranlux", settings=s)
    assert job.label == "a10A1-he-5013486-ranlux-t298-imp25"
    assert Job(Path("x.mfj"), "he", 1, tmp_path).label == "x-he-1"
    small = settings.resolve(None, itn=3, inp=7)
    assert Job(Path("x.mfj"), "he", 1, tmp_path, split=21, settings=small).split == 21
    with pytest.raises(ValueError, match="from 1 to 21 \\(itn \\* inp\\)"):
        Job(Path("x.mfj"), "he", 1, tmp_path, split=22, settings=small)
    with pytest.raises(ValueError, match="settings must be"):
        Job(Path("x.mfj"), "he", 1, tmp_path, settings={"imp": 25})


def test_the_command_line_takes_a_file_and_single_values(tmp_path):
    args = cli.parser().parse_args(["run", "x.mfj", "--settings", "s.toml", "--temperature",
                                    "298", "--imp", "25", "--inor", "5"])
    assert args.settings == Path("s.toml") and args.temperature == 298.0
    assert (args.imp, args.itn, args.inp, args.inum, args.inor) == (25, None, None, None, 5)
    args = cli.parser().parse_args(["run", "x.mfj"])
    assert all(getattr(args, k) is None for k in settings.NAMES) and args.settings is None
    assert cli.parser().parse_args(["render-parameters", "he", "--settings", "s.toml"]).settings \
        == Path("s.toml")


def test_render_parameters_writes_the_settings_too(tmp_path, capsys):
    f = tmp_path / "mine.toml"
    f.write_text("format = 1\nimp = 25\n", encoding="utf-8")
    assert cli.main(["render-parameters", "he", str(tmp_path / "a")]) == 0
    assert (tmp_path / "a" / "settings.tab").read_bytes() == RENDERED.encode()
    assert cli.main(["render-parameters", "he", str(tmp_path / "b"), "--settings", str(f)]) == 0
    assert settings.read_rendered(tmp_path / "b" / "settings.tab").imp == 25
    assert "imp=25" in capsys.readouterr().out
    f.write_text("format = 1\nimp = 0\n", encoding="utf-8")
    assert cli.main(["render-parameters", "he", str(tmp_path / "c"), "--settings", str(f)]) == 2
    assert "imp is 0" in capsys.readouterr().err


# --- through the reader, to the bit ----------------------------------------------------------

@pytest.fixture(scope="module")
def setprobe(gfortran, tmp_path_factory) -> Path:
    """``setprobe.f`` compiled with the pinned include under the recorded flags, no warnings."""
    d = tmp_path_factory.mktemp("setprobe")
    exe = d / ("setprobe.exe" if sys.platform == "win32" else "setprobe")
    cmd = [gfortran, *fortran.flags(), "-I", str(fortran.FORTRAN_DIR), "-o", str(exe),
           str(SETPROBE)]
    proc = subprocess.run(cmd, env=fortran._env(gfortran), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace")
    assert proc.returncode == 0, proc.stdout
    assert fortran.count_warnings(proc.stdout) == 0, proc.stdout
    return exe


def _probe(exe: Path, d: Path) -> tuple[int, list[str], str]:
    proc = subprocess.run([str(exe)], cwd=d, capture_output=True, text=True, timeout=60,
                          stdin=subprocess.DEVNULL)
    text = (d / "probe.txt").read_text(encoding="ascii") if (d / "probe.txt").exists() else ""
    return proc.returncode, [s.rstrip("\r") for s in text.splitlines()], proc.stdout


def _bits(t: float) -> str:
    return struct.pack(">d", t).hex().upper()


def test_without_a_file_the_reader_gives_the_2012_values(setprobe, tmp_path):
    rc, lines, out = _probe(setprobe, tmp_path)
    assert rc == 0 and out.strip() == ""
    assert lines == [f"{_bits(301.0)}     1000       10       40   250000       30"]


@pytest.mark.parametrize("t", [301, 298, 298.15, 80.5, 1e-3, 6000, 1 / 3])
def test_a_rendered_temperature_reads_back_bit_identical(setprobe, tmp_path, t):
    s = Settings(t, 25, 3, 7, 200, 5)
    s.render(tmp_path)
    rc, lines, out = _probe(setprobe, tmp_path)
    assert rc == 0, lines
    assert lines == [f"{_bits(float(t))}       25        3        7      200        5"]
    assert out.split()[:3] == ["settings", "from", "settings.tab:"]


def test_the_shipped_file_reads_back_as_the_defaults(setprobe, tmp_path):
    settings.shipped().render(tmp_path)
    rc, lines, _ = _probe(setprobe, tmp_path)
    assert rc == 0
    assert lines == [f"{_bits(301.0)}     1000       10       40   250000       30"]


# --- the program's refusals ------------------------------------------------------------------

@pytest.fixture(scope="module")
def binaries(pool, gfortran, tmp_path_factory) -> dict[str, Path]:
    """Both shipped binaries: the pool's, plus a build of any gas the session's pool left out
    (a session that collects this file alone builds helium only)."""
    out = dict(pool.binaries)
    for gas in fortran.GASES:
        if gas not in out:
            out[gas] = fortran.build(gas, tmp_path_factory.mktemp(f"settings-bin-{gas}"),
                                     gfortran).binary
    return out


def _tab(values: str) -> str:
    return f"MOBCAL-SETTINGS 1\n{values}\n"


# (the settings.tab written beside the input; the refusal, the output's only line)
TAB_REFUSALS = {
    "magic": ("MOBCAL-X 1\n301 1000 10 40 250000 30\n",
              "settings.tab is not a MOBCAL-SETTINGS 1 file"),
    "rendered format": ("MOBCAL-SETTINGS 2\n301 1000 10 40 250000 30\n",
                        "settings.tab is not a MOBCAL-SETTINGS 1 file"),
    "empty": ("", "settings.tab is not a MOBCAL-SETTINGS 1 file"),
    "short": (_tab("301 1000 10"), "settings.tab cannot be read as a MOBCAL-SETTINGS 1 file"),
    "token": (_tab("301 1000.5 10 40 250000 30"),
              "settings.tab cannot be read as a MOBCAL-SETTINGS 1 file"),
    "t zero": (_tab("0 1000 10 40 250000 30"),
               "settings.tab: temperature  0.0000E+00 is not a positive number"),
    "t negative": (_tab("-5 1000 10 40 250000 30"),
                   "settings.tab: temperature -5.0000E+00 is not a positive number"),
    "t nan": (_tab("nan 1000 10 40 250000 30"),
              "settings.tab: temperature         NaN is not a positive number"),
    "t inf": (_tab("inf 1000 10 40 250000 30"),
              "settings.tab: temperature    Infinity is not a positive number"),
    "imp 0": (_tab("301 0 10 40 250000 30"),
              "settings.tab: imp is          0; 1 to  999999 are allowed"),
    "imp over": (_tab("301 1000000 10 40 250000 30"),
                 "settings.tab: imp is    1000000; 1 to  999999 are allowed"),
    "itn over": (_tab("301 1000 101 40 250000 30"),
                 "settings.tab: itn is        101; 1 to     100 are allowed"),
    "inp over": (_tab("301 1000 10 101 250000 30"),
                 "settings.tab: inp is        101; 1 to     100 are allowed"),
    "inum over": (_tab("301 1000 10 40 10000000 30"),
                  "settings.tab: inum is   10000000; 1 to 9999999 are allowed"),
    "inor over": (_tab("301 1000 10 40 250000 101"),
                  "settings.tab: inor is        101; 1 to     100 are allowed"),
    "product": (_tab("301 1000 100 100 250000 30"),
                "settings.tab: itn*inp*imp is 100* 100*   1000; at most 9999999 points per "
                "coordinate set"),
}


@pytest.mark.parametrize("case", TAB_REFUSALS)
def test_a_bad_settings_file_is_refused_before_the_table_is_read(binaries, tmp_path, case):
    tab, last = TAB_REFUSALS[case]
    for gas, binary in binaries.items():
        d = tmp_path / gas
        d.mkdir()
        (d / "in.mfj").write_text(_HBR, encoding="latin-1", newline="\n")
        (d / "mobcal.in").write_text("in.mfj\nout.txt\n1\n", encoding="latin-1", newline="\n")
        parameters.shipped(gas).render(d)
        (d / settings.RENDERED).write_text(tab, encoding="ascii", newline="\n")
        proc = subprocess.run([str(binary)], cwd=d, capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)
        out = OutFile.read(d / "out.txt")
        assert proc.returncode == 1, (gas, proc.returncode, out.last_line)
        assert out.lines == [" " + last], (gas, out.lines[-3:])
        assert " " + last in proc.stdout.replace("\r", "").splitlines()


def test_the_bounds_the_include_declares_are_the_modules():
    text = (fortran.FORTRAN_DIR / INCLUDE).read_text(encoding="ascii")
    declared = {m[1]: int(m[2]) for m in re.finditer(r"parameter \((mx\w+)=(\d+)\)", text)}
    assert declared == {"mximp": 999_999, "mxitn": 100, "mxinp": 100, "mxinum": 9_999_999,
                        "mxinor": 100, "mxtot": 9_999_999}
    assert {k: v[1] for k, v in settings.BOUNDS.items()} == {
        "imp": declared["mximp"], "itn": declared["mxitn"], "inp": declared["mxinp"],
        "inum": declared["mxinum"], "inor": declared["mxinor"]}
    assert settings.MAX_POINTS == declared["mxtot"]
    assert all(v[0] == 1 for v in settings.BOUNDS.values())
    assert "t.lt.1.d300" in text and settings.MAX_TEMPERATURE == 1e300
    defaults = re.findall(r"^      (t|imp|itn|inp|inum|inor)=(\S+)$", text, re.M)
    assert dict(defaults) == {"t": "301.d0", "imp": "1000", "itn": "10", "inp": "40",
                              "inum": "250000", "inor": "30"}


# --- other settings equal a build with them compiled in -------------------------------------

# Per gas: the settings the run uses and the statements a copy of the include gets in place of
# its 2012 defaults; the copy is built with no settings.tab in its directory.
ORACLE = {
    "he": (dict(temperature=298, imp=25), {"t=301.d0": "t=298.d0", "imp=1000": "imp=25"}),
    "n2": (dict(temperature=350, imp=10, itn=5, inp=20),
           {"t=301.d0": "t=350.d0", "imp=1000": "imp=10", "itn=10": "itn=5", "inp=40": "inp=20"}),
}


@pytest.fixture(scope="module")
def rebuilt(gfortran, tmp_path_factory) -> dict[str, Path]:
    """Both binaries built from a copy of the sources whose include carries ``ORACLE``'s values
    as its defaults, every other line the shipped code."""
    out = {}
    for gas, (_, patches) in ORACLE.items():
        src = tmp_path_factory.mktemp(f"oracle-src-{gas}")
        for p in fortran.FORTRAN_DIR.glob("*.[fi]*"):
            shutil.copy(p, src / p.name)
        text = (src / INCLUDE).read_text(encoding="ascii")
        for old, new in patches.items():
            text, n = re.subn(rf"^      {re.escape(old)}$", f"      {new}", text, flags=re.M)
            assert n == 1, (old, n)
        (src / INCLUDE).write_text(text, encoding="ascii", newline="\n")
        exe = tmp_path_factory.mktemp(f"oracle-bin-{gas}") / fortran.binary_name(gas)
        cmd = [gfortran, *fortran.flags(), "-o", str(exe), str(src / fortran.SOURCE[gas])]
        proc = subprocess.run(cmd, env=fortran._env(gfortran), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace")
        assert proc.returncode == 0 and fortran.count_warnings(proc.stdout) == 0, proc.stdout
        out[gas] = exe
    return out


def _by_hand(binary: Path, d: Path, gas: str) -> subprocess.Popen:
    """Start ``binary`` on choline in ``d`` as the driver would, but with no ``settings.tab``:
    the input under its own name, the run file at the 2012 seed under RANLUX, the table."""
    d.mkdir()
    (d / gate.CHOLINE.name).write_bytes(gate.CHOLINE.read_bytes())
    InFile(gate.CHOLINE.name, OUTPUT_NAME, 5013489, None, "ranlux").write(d)
    parameters.shipped(gas).render(d)
    assert not (d / settings.RENDERED).exists()
    return subprocess.Popen([str(binary)], cwd=d, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


@pytest.mark.parametrize("gas", sorted(ORACLE))
def test_a_setting_equals_a_rebuilt_binary(pool, binaries, rebuilt, tmp_path, gas):
    values, _ = ORACLE[gas]
    s = settings.resolve(None, **values)
    # The rebuilt binary, its values compiled in, with no settings file (the driver would
    # render one, so it runs by hand); the shipped binary through the driver, which renders
    # the same values for it to read.
    proc = _by_hand(rebuilt[gas], tmp_path / "compiled", gas)
    read = run_one(Job(gate.CHOLINE, gas, 5013489, tmp_path, name="read", generator="ranlux",
                       settings=s), lambda j: [str(binaries[j.gas])])
    assert proc.wait(timeout=1800) == 0
    assert read.ok, read.message
    assert not (tmp_path / "compiled" / settings.RENDERED).exists()
    compiled = OutFile.read(tmp_path / "compiled" / OUTPUT_NAME)
    a, b = compiled.lines, OutFile.read(read.output).lines
    assert a == b, "\n".join(difflib.unified_diff(a, b, "compiled in", "read", lineterm=""))
    assert compiled.ok and read.cross_sections == compiled.cross_sections
    assert f" temperature = {s.temperature:.4E}" in b
    assert f" number of random points (imp) ={s.imp:6d}" in b
    assert f" total number of points ={s.points:7d}" in b
    if gas == "he":
        assert read.cross_sections != pool.runs["he"].new.cross_sections


# --- split = serial at other settings, both generators ---------------------------------------

SMALL = dict(itn=3, inp=7, imp=100)  # 21 blocks of 100 trajectories: seconds


@pytest.mark.parametrize("generator", ["ranlux", "philox"])
def test_a_split_run_at_other_settings_reproduces_the_serial_run(pool, tmp_path, generator):
    s = settings.resolve(None, **SMALL)
    jobs = [Job(gate.CHOLINE, "he", 5013489, tmp_path, name=f"serial-{generator}",
                generator=generator, settings=s),
            Job(gate.CHOLINE, "he", 5013489, tmp_path, name=f"split-{generator}", split=4,
                generator=generator, settings=s)]
    serial, split = run_many(jobs, workers=2, launcher=pool.launcher).results
    assert serial.ok and split.ok, (serial.message, split.message)
    a = shared(OutFile.read(serial.output).lines)
    b = shared(OutFile.read(split.output).lines)
    assert a == b, "\n".join(difflib.unified_diff(a, b, "serial", "W=4", lineterm=""))
    assert split.cross_sections == serial.cross_sections
    assert gate.provenance(0, 21, 0, 0, 4) in OutFile.read(split.output).lines
    blocks = [Block.read(p) for p in sorted(split.job.run_dir.glob("block-*.dat"))]
    assert len(blocks) == 21 and [b.k for b in blocks] == list(range(1, 22))
    assert {b.settings for b in blocks} == {s} and {b.generator for b in blocks} == {generator}
    assert [(b.cycle, b.point) for b in blocks] == [Block.cycle_point(k, 3) for k in range(1, 22)]
    for w in range(1, 5):
        worker = OutFile.read(split.job.worker_dir(w) / OUTPUT_NAME)
        mine = 6 if w == 1 else 5
        assert gate.provenance(mine, 0, 21 - mine, w, 4) in worker.lines


def test_a_block_from_other_settings_is_refused(pool, tmp_path):
    # A combining run at the 2012 settings, W = 2, that finds block 1 integrated at imp = 25.
    d = tmp_path
    (d / "Choline.mfj").write_bytes(gate.CHOLINE.read_bytes())
    InFile("Choline.mfj", "out.txt", 5013489, (2, 0), "ranlux").write(d)
    parameters.shipped("he").render(d)
    DEFAULTS.render(d)
    Block(1, 1, 1, 5013489, 0.5, 0.5, 0, "ranlux", DEFAULTS.replace(imp=25)).write(d)
    proc = subprocess.run([str(pool.binaries["he"])], cwd=d, capture_output=True, timeout=300,
                          stdin=subprocess.DEVNULL)
    out = OutFile.read(d / "out.txt")
    assert proc.returncode == 1, (proc.returncode, out.last_line)
    assert out.last_line == ("file block-001-00001.dat  is not this block: set   1 cycle  1 "
                             "point  1 seed   5013489 generator 1 imp     25 itn  10 inp  40 "
                             "inum  250000 inor  30 t 3.0100E+02")
    assert not out.ok


def test_a_block_file_of_another_shape_is_refused(pool, tmp_path):
    # The 48-byte record the programs wrote before the settings were in it.
    d = tmp_path
    (d / "Choline.mfj").write_bytes(gate.CHOLINE.read_bytes())
    InFile("Choline.mfj", "out.txt", 5013489, (2, 0), "ranlux").write(d)
    parameters.shipped("he").render(d)
    (d / "block-001-00001.dat").write_bytes(
        struct.pack("<i5i2di i", 40, 1, 1, 1, 5013489, 1, 0.5, 0.5, 0, 40))
    proc = subprocess.run([str(pool.binaries["he"])], cwd=d, capture_output=True, timeout=300,
                          stdin=subprocess.DEVNULL)
    out = OutFile.read(d / "out.txt")
    assert proc.returncode == 1, (proc.returncode, out.last_line)
    assert out.last_line == "file block-001-00001.dat  cannot be read as a block file"


# --- through the stand-in: the driver's plumbing at other settings ---------------------------

def test_the_driver_renders_and_records_other_settings(tmp_path):
    from test_run import launcher, write_input
    s = settings.resolve(None, itn=3, inp=7, imp=100, temperature=298)
    job = Job(write_input(tmp_path / "ok.mfj", "ok"), "he", 7, tmp_path / "runs", split=4,
              settings=s)
    r = run_one(job, launcher)
    assert r.ok, r.message
    assert job.run_dir.name == "ok-he-7-t298-imp100-itn3-inp7"
    assert settings.read_rendered(job.run_dir / settings.RENDERED) == s
    for w in range(1, 5):
        assert settings.read_rendered(job.worker_dir(w) / settings.RENDERED) == s
    blocks = sorted(job.run_dir.glob("block-*.dat"))
    assert len(blocks) == 21 and all(Block.read(p).settings == s for p in blocks)
    import json
    rec = json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))
    assert rec["settings"] == s.record()
    assert OutFile.read(r.output).summary["temperature"] == "2.9800E+02"
    with pytest.raises(ValueError, match="from 1 to 21"):
        Job(job.input, "he", 7, tmp_path, split=22, settings=s)
