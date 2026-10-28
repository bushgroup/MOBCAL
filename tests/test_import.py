"""mobcal.io.structure and ``mobcal import``: the ORCA and Gaussian fixtures, the .xyz reader,
the refusals, and an imported ion run through the driver in both gases.

Every value an import writes is checked against the output as printed, read here by a few
regular expressions and no cclib, and the ORCA CHELPG charges also against ORCA's own
``<job>.chelpg.xyz``. Each refusal is shown on an edited copy of a fixture. The fixtures are
pinned by ``tests/data/qm/SHA256SUMS``.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mobcal import cli, fortran, parameters, settings
from mobcal.io import structure
from mobcal.io.mfj import MAX_ATOMS, Mfj
from mobcal.io.outfile import OutFile
from mobcal.io.structure import StructureError
from mobcal.run import Job, run_one

QM = Path(__file__).resolve().parent / "data" / "qm"
ORCA = QM / "orca"
CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"
REFERENCE = Path(__file__).resolve().parent / "reference"  # the 2012 outputs, current print

# The blocks each job's output holds at its last geometry (tests/data/qm/README.md).
BLOCKS = {
    "choline_opt": {"mulliken", "lowdin"},
    "choline_opt_chelpg": {"mulliken", "lowdin", "chelpg"},
    "choline_sp": {"mulliken", "lowdin", "chelpg", "hirshfeld"},
    "choline_two_jobs": {"mulliken", "lowdin", "chelpg", "hirshfeld"},
    "choline_2012_hf": {"mulliken", "lowdin", "chelpg", "hirshfeld"},
    "choline_2012_b3lyp": {"mulliken", "lowdin", "chelpg", "hirshfeld"},
}
# Where ORCA wrote the CHELPG charges of the last geometry.
CHELPG_XYZ = {job: ORCA / job / f"{job}.chelpg.xyz" for job in BLOCKS
              if "chelpg" in BLOCKS[job]}
CHELPG_XYZ["choline_two_jobs"] = ORCA / "choline_two_jobs" / "choline_two_jobs_job2.chelpg.xyz"


# --- the printed text, read without cclib ----------------------------------------------------

_HEADINGS = {k: re.compile("^" + re.escape(h)) for k, h in structure.ORCA_HEADINGS.items()}
_ATOM_Q = re.compile(r"^\s*\d+\s+[A-Z][a-z]?\s*:?\s+(-?\d+\.\d+)(?:\s+-?\d+\.\d+)?\s*$")


def printed(job: str) -> tuple[list[tuple[int, list]], dict[str, list[tuple[int, list]]]]:
    """Every coordinate block and every charge block of a job's output, with its line index."""
    lines = (ORCA / job / f"{job}.out").read_text(encoding="utf-8").splitlines()
    coords, charges = [], {k: [] for k in _HEADINGS}
    i = 0
    while i < len(lines):
        if lines[i] == structure.ORCA_COORDINATES:
            j, atoms = i + 2, []
            while lines[j].strip():
                sym, x, y, z = lines[j].split()
                atoms.append((sym, float(x), float(y), float(z)))
                j += 1
            coords.append((i, atoms))
            i = j
            continue
        key = next((k for k, h in _HEADINGS.items() if h.match(lines[i])), None)
        if key is None:
            i += 1
            continue
        j, q = i + 1, []
        while j < len(lines) and not (q and not _ATOM_Q.match(lines[j])):
            m = _ATOM_Q.match(lines[j])
            if m:
                q.append(float(m[1]))
            j += 1
        charges[key].append((i, q))
        i = j
    return coords, charges


def chelpg_xyz(path: Path) -> tuple[list[str], list[tuple[float, ...]], list[float]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    n = int(lines[0])
    rows = [line.split() for line in lines[2:2 + n]]
    return ([r[0] for r in rows], [tuple(map(float, r[1:4])) for r in rows],
            [float(r[4]) for r in rows])


# --- the fixtures ----------------------------------------------------------------------------

def test_every_fixture_is_its_pinned_file_and_every_file_is_pinned():
    pins = {}
    for line in (QM / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        pins[name] = digest
    on_disk = {p.relative_to(QM).as_posix() for p in QM.rglob("*")
               if p.is_file() and p.name not in ("README.md", "SHA256SUMS")}
    assert sorted(pins) == sorted(on_disk)
    for name, digest in pins.items():
        assert hashlib.sha256((QM / name).read_bytes()).hexdigest() == digest, name


def test_the_fixtures_are_the_six_jobs_lf_and_from_orca_6_1_1():
    assert sorted(p.name for p in ORCA.iterdir()) == sorted(BLOCKS)
    for p in ORCA.rglob("*"):
        if p.is_file():
            assert b"\r" not in p.read_bytes(), p
    for job in BLOCKS:
        text = (ORCA / job / f"{job}.out").read_text(encoding="utf-8")
        assert "Program Version 6.1.1" in text and "****ORCA TERMINATED NORMALLY****" in text


@pytest.mark.parametrize("job", BLOCKS)
def test_the_last_block_of_each_kind_follows_the_last_geometry(job):
    """The rule the import relies on, as the outputs print it; and an optimization's first
    population analysis, at the start geometry, is a different set of numbers."""
    coords, charges = printed(job)
    assert {k for k, b in charges.items() if b} == BLOCKS[job]
    for key in BLOCKS[job]:
        assert charges[key][-1][0] > coords[-1][0], key
        if len(charges[key]) > 1:
            assert charges[key][0][1] != charges[key][-1][1], key


# --- every fixture, every block --------------------------------------------------------------

@pytest.fixture(scope="module")
def read_all() -> dict[str, structure.Structure]:
    return {job: structure.read(ORCA / job / f"{job}.out") for job in BLOCKS}


@pytest.mark.parametrize("job", BLOCKS)
def test_an_orca_output_reads_as_its_last_geometry_and_blocks(read_all, job):
    s = read_all[job]
    coords, charges = printed(job)
    last = coords[-1][1]
    assert (s.program, s.version, s.net_charge) == ("ORCA", "6.1.1", 1)
    assert s.reader.startswith("cclib ")
    assert set(s.charges) == BLOCKS[job] and s.unpaired == {}
    assert s.symbols == tuple(a[0] for a in last)
    assert s.coordinates == tuple(a[1:] for a in last)
    for key in BLOCKS[job]:
        assert list(s.charges[key]) == charges[key][-1][1], key


@pytest.mark.parametrize("job,key", [(j, k) for j in BLOCKS for k in sorted(BLOCKS[j])])
def test_each_block_imports_as_printed(read_all, job, key):
    s = read_all[job]
    imp = structure.convert(s, key)
    m = imp.mfj
    _, charges = printed(job)
    assert (m.coordinate_sets, m.atoms, m.units, m.charge_mode, m.correct) == (
        1, 21, "ang", "calc", 1.0)
    assert [a.charge for a in m.sets[0]] == charges[key][-1][1]
    assert [(a.x, a.y, a.z) for a in m.sets[0]] == list(s.coordinates)
    assert [a.key for a in m.sets[0]] == [{"H": 1, "C": 12, "N": 14, "O": 16}[e]
                                          for e in s.symbols]
    assert Mfj.parse(m.text()) == m
    assert imp.record["charges"]["choice"] == key
    assert abs(imp.record["charges"]["difference"]) <= structure.TOLERANCE


@pytest.mark.parametrize("job", CHELPG_XYZ)
def test_chelpg_agrees_with_orcas_own_file(read_all, job):
    m = structure.convert(read_all[job], "chelpg").mfj
    symbols, xyz, q = chelpg_xyz(CHELPG_XYZ[job])
    assert symbols == list(read_all[job].symbols)
    for a, p, qi in zip(m.sets[0], xyz, q, strict=True):
        assert max(abs(a.x - p[0]), abs(a.y - p[1]), abs(a.z - p[2])) <= 5e-7
        assert abs(a.charge - qi) <= 5e-7  # six printed decimals against eight


def test_the_two_jobs_import_reads_job_2(read_all):
    """Job 2's geometry is job 1's stationary point, and job 1's start-geometry blocks are
    earlier in the same file."""
    coords, charges = printed("choline_two_jobs")
    s = read_all["choline_two_jobs"]
    stationary, job2 = coords[-2][1], coords[-1][1]
    assert stationary == job2
    assert list(s.charges["mulliken"]) == charges["mulliken"][2][1]
    assert charges["mulliken"][2][1] != charges["mulliken"][1][1]


def test_hirshfeld_sums_within_the_tolerance(read_all):
    sums = {job: structure.convert(read_all[job], "hirshfeld").record["charges"]["sum"]
            for job in BLOCKS if "hirshfeld" in BLOCKS[job]}
    assert all(1.0001 < v < 1.0003 for v in sums.values()), sums
    assert structure.TOLERANCE == 1e-3


# --- choices and refusals --------------------------------------------------------------------

def test_no_charges_named_is_refused_listing_what_the_file_holds(read_all):
    with pytest.raises(StructureError) as e:
        structure.convert(read_all["choline_opt_chelpg"], None)
    msg = str(e.value)
    assert msg.startswith("choose the charges")
    assert all(k in msg for k in ("mulliken", "lowdin", "chelpg", "uniform"))
    assert "hirshfeld" not in msg


def test_a_block_the_file_does_not_hold_is_refused(read_all):
    with pytest.raises(StructureError, match="no 'chelpg' charges"):
        structure.convert(read_all["choline_opt"], "chelpg")


def test_uniform_is_q_over_n_in_calc_mode_never_equal(read_all):
    for gases in (("he",), ("n2",), ("he", "n2")):
        imp = structure.convert(read_all["choline_sp"], "uniform", gases=gases)
        assert imp.mfj.charge_mode == "calc"
        assert [a.charge for a in imp.mfj.sets[0]] == [1 / 21] * 21
        assert imp.record["charges"]["net_charge"] == 1


def test_a_net_charge_that_disagrees_with_the_output_is_refused(read_all):
    with pytest.raises(StructureError, match="computed at charge"):
        structure.convert(read_all["choline_sp"], "chelpg", net_charge=2)
    assert structure.convert(read_all["choline_sp"], "chelpg", net_charge=1).mfj.atoms == 21


def orca_variant(tmp_path: Path, job: str, name: str, edit) -> Path:
    p = tmp_path / name
    text = (ORCA / job / f"{job}.out").read_text(encoding="utf-8")
    p.write_text(edit(text), encoding="utf-8", newline="\n")
    return p


def test_a_block_printed_only_before_the_last_geometry_is_refused(tmp_path):
    """The optimization's final population analysis hidden from the parser: cclib's last
    Mulliken is then the start geometry's, which the import must not pair with the final."""
    def hide_final(text):
        lines = text.split("\n")
        hits = [i for i, line in enumerate(lines)
                if line.startswith(("MULLIKEN ATOMIC CHARGES", "LOEWDIN ATOMIC CHARGES"))]
        for i in hits[2:]:
            lines[i] = lines[i].replace("CHARGES", "CHARGEZ")
        return "\n".join(lines)
    s = structure.read(orca_variant(tmp_path, "choline_opt", "nofinal.out", hide_final))
    assert s.charges == {} and set(s.unpaired) == {"mulliken", "lowdin"}
    with pytest.raises(StructureError, match="mulliken is refused: its last block is printed "
                                             "before the last geometry"):
        structure.convert(s, "mulliken")
    assert structure.convert(s, "uniform").mfj.atoms == 21


def test_an_output_that_did_not_terminate_normally_is_refused(tmp_path):
    p = orca_variant(tmp_path, "choline_sp", "cut.out",
                     lambda t: t[:t.index("****ORCA TERMINATED NORMALLY****")])
    with pytest.raises(StructureError, match="did not terminate normally"):
        structure.read(p)


def test_an_optimization_that_did_not_converge_is_refused(tmp_path):
    p = orca_variant(tmp_path, "choline_opt", "unconverged.out",
                     lambda t: t.replace("THE OPTIMIZATION HAS CONVERGED", "THE OPTIMIZATION "
                                                                           "HAS STOPPED"))
    with pytest.raises(StructureError, match="did not converge"):
        structure.read(p)


def test_a_gaussian_file_with_no_finished_job_is_refused(tmp_path):
    p = tmp_path / "ion.log"
    p.write_text(" Entering Gaussian System, Link 0=g16\n"
                 " Copyright (c) 1988-2019, Gaussian, Inc.  All Rights Reserved.\n",
                 encoding="utf-8")
    with pytest.raises(StructureError, match="0 of 1 job step terminated normally"):
        structure.read(p)


def test_an_orca_output_of_another_version_imports_with_a_warning(tmp_path):
    p = orca_variant(tmp_path, "choline_sp", "orca5.out",
                     lambda t: t.replace("Program Version 6.1.1", "Program Version 5.0.4"))
    s = structure.read(p)
    assert s.version == "5.0.4" and s.details["untested_version"] is True
    assert "tested on ORCA 6 outputs" in s.warnings[0]
    rec = structure.convert(s, "chelpg").record
    assert rec["source"]["untested_version"] is True and rec["format"] == 2


def test_a_file_no_program_wrote_is_refused(tmp_path):
    p = tmp_path / "notes.out"
    p.write_text("nothing a program wrote\n", encoding="utf-8")
    with pytest.raises(StructureError, match="not an output of a program cclib recognizes"):
        structure.read(p)
    with pytest.raises(StructureError, match="cannot read"):
        structure.read(tmp_path / "missing.out")


# --- Gaussian --------------------------------------------------------------------------------

GAUSSIAN = QM / "gaussian"
# The blocks each log holds at its last geometry, under the import's keys.
G_BLOCKS = {
    "choline_2012_mk": {"mulliken", "hirshfeld", "cm5", "mk"},
    "choline_2012_chelpg": {"mulliken", "natural", "chelpg"},
    "choline_optfreq": {"mulliken", "chelpg"},
}
G_STEPS = {"choline_2012_mk": 1, "choline_2012_chelpg": 1, "choline_optfreq": 2}

_G_COORD = re.compile(r"^\s+(Input|Standard|Z-Matrix) orientation:\s*$")
_G_COORD_ROW = re.compile(r"^\s+\d+\s+(\d+)\s+-?\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)$")
_G_ROW = re.compile(r"^\s+\d+\s+[A-Z][a-z]?\s+(-?\d+\.\d+)((?:\s+-?\d+\.\d+)*)\s*$")
_G_NPA_ROW = re.compile(r"^\s+[A-Z][a-z]?\s+\d+\s+(-?\d+\.\d+)\s")
_G_HEADS = {"mulliken": " Mulliken charges:", "hirshfeld": " Hirshfeld charges, spin densities",
            "esp": " ESP charges:", "natural": " Summary of Natural Population Analysis:"}
_G_RADII = {"Merz-Kollman atomic radii used.": "mk", "Breneman (CHELPG) radii used.": "chelpg"}


def g_printed(job: str):
    """Every coordinate block of a log (line index, kind, [(Z, x, y, z)]) and every charge
    block (line index, values), the ESP blocks keyed by the radii line before them."""
    lines = (GAUSSIAN / job / f"{job}.log").read_text(encoding="ascii").splitlines()
    coords, charges, radii = [], {}, None
    for i, line in enumerate(lines):
        if m := _G_COORD.match(line):
            rows = [_G_COORD_ROW.match(s) for s in lines[i + 5:i + 5 + 21]]
            coords.append((i, m[1], [(int(r[1]), *map(float, r.group(2, 3, 4))) for r in rows]))
        radii = _G_RADII.get(line.strip(), radii)
        key = next((k for k, h in _G_HEADS.items() if line.rstrip().startswith(h)), None)
        if key is None:
            continue
        rows = [(_G_NPA_ROW if key == "natural" else _G_ROW).match(s)
                for s in lines[i + 1:i + 40]]
        rows = [r for r in rows if r][:21]
        if key == "esp":
            key = radii
        charges.setdefault(key, []).append((i, [float(r[1]) for r in rows]))
        if key == "hirshfeld":
            charges.setdefault("cm5", []).append((i, [float(r[2].split()[-1]) for r in rows]))
    return lines, coords, charges


@pytest.fixture(scope="module")
def g_read() -> dict[str, structure.Structure]:
    return {job: structure.read(GAUSSIAN / job / f"{job}.log") for job in G_BLOCKS}


def g_variant(tmp_path: Path, job: str, name: str, edit) -> Path:
    p = tmp_path / name
    text = (GAUSSIAN / job / f"{job}.log").read_text(encoding="ascii")
    edited = edit(text)
    assert edited != text
    p.write_text(edited, encoding="ascii", newline="\n")
    return p


def test_the_gaussian_fixtures_are_three_g16_logs_with_their_inputs():
    assert sorted(p.name for p in GAUSSIAN.iterdir()) == sorted(G_BLOCKS)
    for job, steps in G_STEPS.items():
        log = (GAUSSIAN / job / f"{job}.log").read_bytes()
        gjf = (GAUSSIAN / job / f"{job}.gjf").read_bytes()
        assert b"\r" not in log and b"\r" not in gjf, job
        text = log.decode("ascii")
        assert " Gaussian 16:  ES64L-G16RevB.01 20-Dec-2017" in text
        assert text.count(" Normal termination of Gaussian 16") == steps
        route = next(s for s in gjf.decode("ascii").splitlines() if s.startswith("#"))
        assert f"\n {route}\n" in text, job  # the log echoes the input it was run from


@pytest.mark.parametrize("job", G_BLOCKS)
def test_a_gaussian_log_reads_as_its_last_geometry_and_blocks(g_read, job):
    s = g_read[job]
    _, coords, charges = g_printed(job)
    last = coords[-1][2]
    assert (s.program, s.version, s.net_charge, s.warnings) == ("Gaussian", "16 Rev. B.01", 1, ())
    assert set(s.charges) == G_BLOCKS[job] and s.unpaired == {}
    assert s.details["untested_version"] is False
    assert [{"H": 1, "C": 6, "N": 7, "O": 8}[e] for e in s.symbols] == [a[0] for a in last]
    assert s.coordinates == tuple(a[1:] for a in last)
    for key in G_BLOCKS[job]:
        assert charges[key][-1][0] > coords[-1][0], key
        assert list(s.charges[key]) == charges[key][-1][1], key


@pytest.mark.parametrize("job,key", [(j, k) for j in G_BLOCKS for k in sorted(G_BLOCKS[j])])
def test_each_gaussian_block_imports_as_printed(g_read, job, key):
    imp = structure.convert(g_read[job], key)
    _, _, charges = g_printed(job)
    assert [a.charge for a in imp.mfj.sets[0]] == charges[key][-1][1]
    assert Mfj.parse(imp.mfj.text()) == imp.mfj
    assert abs(imp.record["charges"]["difference"]) <= structure.TOLERANCE
    assert imp.record["source"]["route"].startswith("# B3LYP/6-31++G(d,p) ")


def test_the_single_points_are_at_the_2012_geometry_and_mk_is_the_2012_column(g_read):
    """NoSymm keeps Choline.mfj's coordinates; the 2012 charge column is a B3LYP/6-31++G(d,p)
    Merz-Kollman fit (every atom within 0.005 e, against 0.17 e for CHELPG)."""
    ref = Mfj.read(CHOLINE).sets[0]
    for job in ("choline_2012_mk", "choline_2012_chelpg"):
        assert g_read[job].coordinates == tuple((a.x, a.y, a.z) for a in ref), job
    dq = [abs(q - a.charge) for q, a in zip(g_read["choline_2012_mk"].charges["mk"], ref,
                                            strict=True)]
    assert max(dq) < 0.005
    dq = [abs(q - a.charge) for q, a in zip(g_read["choline_2012_chelpg"].charges["chelpg"], ref,
                                            strict=True)]
    assert max(dq) > 0.1


def test_the_opt_freq_import_reads_step_2(g_read):
    """Step 2 (Freq) prints its own coordinate block, equal to step 1's stationary point, and
    its own population analysis after it: pop=CHELPG carries into the frequency step."""
    lines, coords, charges = g_printed("choline_optfreq")
    step2 = next(i for i, s in enumerate(lines) if s.startswith(" Link1:  Proceeding"))
    standard = [c for c in coords if c[1] == "Standard"]
    assert standard[-1][0] > step2 > standard[-2][0] and standard[-1][2] == standard[-2][2]
    for key in ("mulliken", "chelpg"):
        assert charges[key][-1][0] > standard[-1][0]
        assert list(g_read["choline_optfreq"].charges[key]) == charges[key][-1][1]


def test_a_gaussian_log_cut_short_is_refused(tmp_path):
    full = (GAUSSIAN / "choline_optfreq" / "choline_optfreq.log").read_text(encoding="ascii")
    last = full.rindex(" Normal termination of Gaussian")
    for name, edit in (("no_final.log", lambda t: t[:last]),
                       ("no_freq.log", lambda t: t[:t.index("\n", t.index(" Link1:  ")) + 1])):
        with pytest.raises(StructureError, match="1 of 2 job steps terminated normally"):
            structure.read(g_variant(tmp_path, "choline_optfreq", name, edit))
    p = g_variant(tmp_path, "choline_2012_mk", "error.log",
                  lambda t: t.replace(" Normal termination", " Error termination via Lnk1e"))
    with pytest.raises(StructureError, match="error termination"):
        structure.read(p)


def test_a_gaussian_optimization_that_stopped_is_refused(tmp_path):
    p = g_variant(tmp_path, "choline_optfreq", "stopped.log",
                  lambda t: t.replace("Optimization completed.", "Optimization stopped."))
    with pytest.raises(StructureError, match="did not converge"):
        structure.read(p)


def test_a_step_2_geometry_other_than_cclibs_is_refused(tmp_path):
    """cclib keeps step 1's last point; a step 2 at another geometry must not pair with it."""
    def move(text):
        i = text.rindex("Standard orientation:")
        j = text.index("-0.878240", i)
        return text[:j] + "-0.878250" + text[j + 9:]
    with pytest.raises(StructureError, match="not the last geometry printed"):
        structure.read(g_variant(tmp_path, "choline_optfreq", "moved.log", move))


def test_a_gaussian_block_printed_only_before_the_last_geometry_is_refused(tmp_path):
    def hide_step2(text):
        i = text.index(" Link1:  Proceeding")
        return text[:i] + (text[i:].replace(" ESP charges:\n", " ESP chargez:\n")
                           .replace(" Mulliken charges:\n", " Mulliken chargez:\n"))
    s = structure.read(g_variant(tmp_path, "choline_optfreq", "nostep2.log", hide_step2))
    assert s.charges == {} and set(s.unpaired) == {"mulliken", "chelpg"}
    assert all("before the last geometry" in why for why in s.unpaired.values())


@pytest.mark.parametrize("job,old,new,key,match", [
    ("choline_2012_mk", " Merz-Kollman atomic radii used.", " Read replacement radii",
     "mk", "radii read from the input"),
    ("choline_2012_mk", " Fitting point charges to electrostatic potential\n",
     " Fitting point charges to electrostatic potential\n The dipole moment will be "
     "constrained to the correct value\n", "mk", "constrains the dipole moment"),
    ("choline_2012_chelpg", " Breneman (CHELPG) radii used.", " Merz-Kollman atomic radii used.",
     "mk", "the radii line names mk, and the route asks for chelpg"),
    ("choline_2012_chelpg", "Gaussian NBO Version 3.1", "NBO 7.0 (11-Nov-2026)",
     "natural", "not from Gaussian's built-in NBO 3.1"),
])
def test_a_gaussian_charge_block_the_import_refuses(tmp_path, job, old, new, key, match):
    s = structure.read(g_variant(tmp_path, job, "edited.log", lambda t: t.replace(old, new)))
    assert key not in s.charges and match in s.unpaired[key]
    with pytest.raises(StructureError, match=f"{key} is refused"):
        structure.convert(s, key)


def test_an_untested_esp_scheme_is_refused(tmp_path):
    def chelp(text):
        return (text.replace("Pop=(CHELPG,NBO)", "Pop=(CHELP,NBO)")
                .replace(" Breneman (CHELPG) radii used.", " Francl (CHELP) radii used."))
    s = structure.read(g_variant(tmp_path, "choline_2012_chelpg", "chelp.log", chelp))
    assert "chelpg" not in s.charges
    assert s.unpaired["chelp"] == "CHELP fits are not among the import's tested outputs"


def test_a_gaussian_log_of_another_version_imports_with_a_warning(tmp_path, capsys,
                                                                    monkeypatch):
    p = g_variant(tmp_path, "choline_2012_mk", "g09.log",
                  lambda t: t.replace("ES64L-G16RevB.01", "ES64L-G09RevD.01"))
    s = structure.read(p)
    assert s.version == "09 Rev. D.01" and s.details["untested_version"] is True
    assert set(s.charges) == G_BLOCKS["choline_2012_mk"]
    monkeypatch.chdir(tmp_path)
    assert cli.main(["import", str(p), "--charges", "mk"]) == 0
    err = capsys.readouterr().err
    assert err.startswith("warning: g09.log is from Gaussian 09 Rev. D.01; the import is tested "
                          "on Gaussian 16 outputs")
    rec = json.loads((tmp_path / "g09_mk.import.json").read_text(encoding="utf-8"))
    assert rec["source"]["untested_version"] is True
    assert cli.main(["import", str(GAUSSIAN / "choline_2012_mk" / "choline_2012_mk.log"),
                     "--charges", "mk"]) == 0
    io = capsys.readouterr()
    assert io.err == "" and "(Gaussian 16 Rev. B.01), mk charges" in io.out


# --- .xyz ------------------------------------------------------------------------------------

def xyz(tmp_path: Path, rows: list[str], name: str = "ion.xyz", count: int | None = None) -> Path:
    p = tmp_path / name
    p.write_text(f"{len(rows) if count is None else count}\ncomment\n" + "\n".join(rows) + "\n",
                 encoding="utf-8")
    return p


def test_an_xyz_without_charges_takes_uniform_and_needs_the_net_charge():
    s = structure.read(ORCA / "choline_opt" / "choline_opt.xyz")
    assert (s.program, s.charges, s.net_charge) == ("xyz", {}, None)
    with pytest.raises(StructureError, match="does not carry the ion's net charge"):
        structure.convert(s, "uniform")
    with pytest.raises(StructureError, match="no 'column' charges"):
        structure.convert(s, "column", net_charge=1)
    m = structure.convert(s, "uniform", net_charge=2).mfj
    assert [a.charge for a in m.sets[0]] == [2 / 21] * 21


def test_orcas_chelpg_xyz_imports_through_its_charge_column(read_all):
    s = structure.read(CHELPG_XYZ["choline_sp"])
    assert set(s.charges) == {"column"}
    m = structure.convert(s, "column", net_charge=1).mfj
    _, xyz_, q = chelpg_xyz(CHELPG_XYZ["choline_sp"])
    assert [a.charge for a in m.sets[0]] == q
    assert [(a.x, a.y, a.z) for a in m.sets[0]] == xyz_


@pytest.mark.parametrize("rows,count,match", [
    (["C 0 0 0", "H 1 0 0 0.5"], None, "1 of 2 atoms carry a charge column"),
    (["C 0 0 0", "H 1 0"], None, "line 4: 3 fields"),
    (["C1 0 0 0"], None, "'C1' is not an element symbol"),
    (["C 0 0 x"], None, "not a number"),
    (["C 0 0 nan"], None, "not a finite number"),
    (["C 0 0 0"], 2, "ends after 1 of 2 atoms"),
    (["C 0 0 0", "1", "frame 2", "C 0 0 0"], 1, "more lines follow the 1 atoms"),
    ([], MAX_ATOMS + 1, f"{MAX_ATOMS + 1} atoms; the program holds 1 to {MAX_ATOMS}"),
    ([], 0, "0 atoms"),
])
def test_an_xyz_the_import_refuses(tmp_path, rows, count, match):
    with pytest.raises(StructureError, match=re.escape(match)):
        structure.read(xyz(tmp_path, rows, count=count))


def test_charges_must_sum_to_the_net_charge_within_the_tolerance(tmp_path):
    ok = structure.read(xyz(tmp_path, ["C 0 0 0 0.5", "H 1.1 0 0 0.5009"], "ok.xyz"))
    assert structure.convert(ok, "column", net_charge=1).record["charges"]["sum"] == (
        pytest.approx(1.0009, abs=1e-12))
    far = structure.read(xyz(tmp_path, ["C 0 0 0 0.5", "H 1.1 0 0 0.502"], "far.xyz"))
    with pytest.raises(StructureError, match=r"sum to \+1\.002000, \+2\.00e-03 e from the net "
                                             r"charge \+1; the import allows 0\.001 e"):
        structure.convert(far, "column", net_charge=1)


def test_an_element_a_table_lacks_is_refused_naming_the_gas(tmp_path):
    s = structure.read(xyz(tmp_path, ["P 0 0 0", "h 1.4 0 0", "H -1.4 0 0"], "ph2.xyz"))
    assert s.symbols == ("P", "H", "H")
    with pytest.raises(StructureError, match="P \\(1 atom\\) is not in the He element table, "
                                             "which holds H, C, N, O, F, Na, Si, S, Fe; the "
                                             "N2 table has it"):
        structure.convert(s, "uniform", net_charge=1)
    m = structure.convert(s, "uniform", net_charge=1, gases=("n2",)).mfj
    assert [a.key for a in m.sets[0]] == [31, 1, 1]
    br = structure.read(xyz(tmp_path, ["Br 0 0 0", "H 1.4 0 0"], "hbr.xyz"))
    with pytest.raises(StructureError, match="Br \\(1 atom\\) is not in the He element table"):
        structure.convert(br, "uniform", net_charge=1)
    with pytest.raises(StructureError, match="Br \\(1 atom\\) is not in the N2 element table, "
                                             "which holds H, C, N, O, F, Na, Si, P, S, Fe$"):
        structure.convert(br, "uniform", net_charge=1, gases=("n2",))


def test_keys_are_the_tables_keys():
    for gas in fortran.GASES:
        table = {e.symbol: e.key for e in parameters.shipped(gas).elements}
        assert structure.element_keys(list(table), (gas,)) == table


# --- writing and the record ------------------------------------------------------------------

def test_write_puts_the_record_beside_the_file_and_never_replaces(tmp_path, read_all):
    imp = structure.convert(read_all["choline_sp"], "chelpg")
    mfj, rec = structure.write(imp, tmp_path / "choline.mfj")
    assert rec == tmp_path / "choline.import.json"
    assert Mfj.read(mfj) == imp.mfj
    r = json.loads(rec.read_text(encoding="utf-8"))
    src = ORCA / "choline_sp" / "choline_sp.out"
    assert r["source"]["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert (r["source"]["program"], r["source"]["version"]) == ("ORCA", "6.1.1")
    assert r["source"]["keywords"] == ["B3LYP", "D3BJ", "def2-TZVP", "CHELPG", "Hirshfeld"]
    assert r["mfj"]["sha256"] == hashlib.sha256(mfj.read_bytes()).hexdigest()
    assert r["mfj"]["label"] == "choline_sp_chelpg"
    assert r["charges"]["net_charge_from"] == "output"
    assert r["elements"]["tables"]["He"]["sha256"] == parameters.SHA256["mobcal_He.toml"]
    assert r["elements"]["tables"]["N2"]["sha256"] == parameters.SHA256["mobcal_N2.toml"]
    with pytest.raises(StructureError, match="exists; not replacing it"):
        structure.write(imp, mfj)
    structure.write(imp, mfj, overwrite=True)


def test_a_long_or_unusual_name_gives_a_label_the_program_reads(tmp_path):
    p = xyz(tmp_path, ["C 0 0 0", "H 1.1 0 0"], "a very long name for one small ion.xyz")
    m = structure.convert(structure.read(p), "uniform", net_charge=1).mfj
    assert m.label == "a_very_long_name_for_one_small"
    assert Mfj.parse(m.text()) == m


# --- the command -----------------------------------------------------------------------------

def test_the_command_lists_the_blocks_until_one_is_named(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = str(ORCA / "choline_two_jobs" / "choline_two_jobs.out")
    assert cli.main(["import", src]) == 2
    assert "choose the charges: choline_two_jobs.out holds mulliken" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
    assert cli.main(["import", src, "--charges", "chelpg"]) == 0
    out = capsys.readouterr().out
    assert "21 atoms from choline_two_jobs.out (ORCA 6.1.1), chelpg charges" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "choline_two_jobs_chelpg.import.json", "choline_two_jobs_chelpg.mfj"]
    assert cli.main(["import", src, "--charges", "chelpg"]) == 2
    assert "exists; not replacing it" in capsys.readouterr().err
    assert cli.main(["import", src, "--charges", "chelpg", "--force"]) == 0


def test_the_command_takes_an_xyz_a_net_charge_and_a_gas(tmp_path, capsys):
    p = xyz(tmp_path, ["P 0 0 0", "H 1.4 0 0", "H -1.4 0 0"], "ph2.xyz")
    out = tmp_path / "ph2.mfj"
    assert cli.main(["import", str(p), "--charges", "uniform", "-o", str(out)]) == 2
    assert "does not carry the ion's net charge" in capsys.readouterr().err
    assert cli.main(["import", str(p), "--charges", "uniform", "--net-charge", "1",
                     "-o", str(out)]) == 2
    assert "not in the He element table" in capsys.readouterr().err
    assert cli.main(["import", str(p), "--charges", "uniform", "--net-charge", "1",
                     "--gas", "n2", "-o", str(out)]) == 0
    assert Mfj.read(out).keys == (1, 31)


def test_running_a_calculation_never_loads_cclib():
    code = ("import sys; from mobcal import cli, run, selfcheck; from mobcal.io import structure;"
            " cli.main(['version']); print(sorted(m for m in ('cclib', 'scipy', 'numpy')"
            " if m in sys.modules))")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          timeout=120, check=True)
    assert proc.stdout.split("\n")[-2] == "[]"


# --- through the program ---------------------------------------------------------------------

# Small enough that both gases finish in seconds; the header the program prints before any
# trajectory (charge, mass, centre of mass) does not depend on them.
QUICK = settings.resolve(None, imp=4, itn=1, inp=2, inum=2000, inor=30)
HEADER = ("number of coordinate sets", "number of atoms", "coordinates in", "correction factor",
          "using a", "total charge", "total absolute charge", "mass of ion",
          "center of mass coordinates")


@pytest.fixture(scope="module")
def binaries(gfortran, tmp_path_factory) -> dict[str, Path]:
    return {gas: fortran.build(gas, tmp_path_factory.mktemp(f"import-bin-{gas}"),
                               gfortran).binary for gas in fortran.GASES}


def header(out: Path) -> list[str]:
    return [line for line in OutFile.read(out).lines
            if line.strip().startswith(HEADER)]


def run(binary: Path, mfj: Path, gas: str, out_dir: Path):
    r = run_one(Job(mfj, gas, 5013489, out_dir, generator="ranlux", settings=QUICK),
                lambda _job: [str(binary)])
    assert r.ok, (gas, r.message)
    return r


def test_choline_through_an_xyz_runs_as_the_2012_input_in_both_gases(binaries, tmp_path):
    """Choline.mfj's own coordinates and charges, written as an .xyz with a charge column and
    imported: both programs print the header of the 2012 references (tests/reference/, the
    current print format), line for line."""
    ref = Mfj.read(CHOLINE)
    symbols = {1: "H", 12: "C", 14: "N", 16: "O"}
    raw = CHOLINE.read_text(encoding="latin-1").splitlines()[6:6 + ref.atoms]
    rows = [f"{symbols[int(t[3])]} {t[0]} {t[1]} {t[2]} {t[4]}" for t in map(str.split, raw)]
    s = structure.read(xyz(tmp_path, rows, "choline.xyz"))
    mfj, _ = structure.write(structure.convert(s, "column", net_charge=1),
                             tmp_path / "choline.mfj")
    got = Mfj.read(mfj)
    assert got.sets == ref.sets
    for gas, binary in binaries.items():
        r = run(binary, mfj, gas, tmp_path / "runs")
        want = header(REFERENCE / f"Choline_{parameters.GAS[gas]}.out")
        assert header(r.output) == want, gas
        assert len(want) == len(HEADER)


@pytest.mark.parametrize("charges", ["chelpg", "uniform"])
def test_an_imported_orca_output_runs_in_both_gases(binaries, tmp_path, read_all, charges):
    mfj, _ = structure.write(structure.convert(read_all["choline_sp"], charges),
                             tmp_path / f"choline_sp_{charges}.mfj")
    for gas, binary in binaries.items():
        r = run(binary, mfj, gas, tmp_path / "runs")
        lines = header(r.output)
        assert " using a calculated (non-uniform) charge distribution" in lines
        assert " total charge = 1.0000E+00" in lines
        if charges == "uniform":
            assert " total absolute charge = 1.0000E+00" in lines
        assert "TM" in r.cross_sections


def test_an_imported_gaussian_mk_fit_runs_in_both_gases(binaries, tmp_path, g_read):
    """At the 2012 geometry the MK import differs from Choline.mfj in the charges alone, so the
    program prints the 2012 header but for the total absolute charge."""
    mfj, _ = structure.write(structure.convert(g_read["choline_2012_mk"], "mk"),
                             tmp_path / "choline_2012_mk.mfj")
    for gas, binary in binaries.items():
        r = run(binary, mfj, gas, tmp_path / "runs")
        want = header(REFERENCE / f"Choline_{parameters.GAS[gas]}.out")
        got = header(r.output)
        assert [s for s in got if "absolute" not in s] == [s for s in want if "absolute" not in s]
        assert "TM" in r.cross_sections
