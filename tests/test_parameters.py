"""The element tables: the TOML files say what the 2012 source says, and refuse what it cannot.

The first group is the proof that moving the tables out of the Fortran moved no number: it
parses the ``if(imass(iatom).eq.NN)`` chains and the nitrogen combining constants out of
``fortran/mobcal_*.f`` and holds every token of each TOML file to the literal the source spells,
row for row, in both of each source's coordinate readers (``fcoord`` and ``ncoord``). The one
place the two readers disagree is nitrogen's silicon row, where ``ncoord`` carries iron's
numbers; the file carries ``fcoord``'s. When the program reads the rendered table and the chains
leave the source, this group is retired with them.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

from mobcal import cli, fortran, parameters
from mobcal.parameters import ParameterError

# --- the 2012 source ------------------------------------------------------------------------

_IF = re.compile(r"^\s+if\(imass\(iatom\)\.eq\.(\d+)\)\s*then\s*$")
_CONSTANT = re.compile(r"^\s+(eogas|rogas|conve|convr)=(\S+)\s*$")
_ASSIGN = {
    "he": {
        "mass": re.compile(r"^\s+xmass\(iatom\)=(\S+)$"),
        "epsilon": re.compile(r"^\s+eolj\(iatom\)=(\S+)\*xe$"),
        "sigma": re.compile(r"^\s+rolj\(iatom\)=(\S+)\*1\.0d-10$"),
        "rhs": re.compile(r"^\s+rhs\(iatom\)=(\S+)\*1\.0d-10$"),
    },
    "n2": {
        "mass": re.compile(r"^\s+xmass\(iatom\)=(\S+)$"),
        "epsilon": re.compile(r"^\s+eolj\(iatom\)=dsqrt\(eogas\*(\S+)\)\*conve\*xe$"),
        "sigma": re.compile(r"^\s+rolj\(iatom\)=dsqrt\(rogas\*(\S+)\)\*convr\*1\.0d-10$"),
        "rhs": re.compile(r"^\s+rhs\(iatom\)=(\S+)\*1\.0d-10$"),
    },
}


def _unparen(token: str) -> str:
    return token[1:-1] if token.startswith("(") and token.endswith(")") else token


def _subroutine(gas: str, name: str) -> list[str]:
    """The code lines of one subroutine, fixed-form comment lines dropped."""
    lines = (fortran.FORTRAN_DIR / fortran.SOURCE[gas]).read_text(
        encoding="latin-1").splitlines()
    start = next(i for i, s in enumerate(lines)
                 if re.match(rf"^\s+subroutine\s+{name}\b", s))
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^\s+subroutine\s", lines[i])), len(lines))
    return [s.rstrip() for s in lines[start:end] if s[:1] not in "cC*!"]


def source_table(gas: str, name: str) -> tuple[dict[int, dict[str, str]], dict[str, str]]:
    """The element chain of one coordinate reader, key -> column -> literal, in source order,
    and the combining constants it assigns."""
    table: dict[int, dict[str, str]] = {}
    constants: dict[str, str] = {}
    key = None
    for line in _subroutine(gas, name):
        if m := _IF.match(line):
            key = int(m.group(1))
            assert key not in table, f"{name}: key {key} twice"
            table[key] = {}
            continue
        if key is not None and line.strip() == "endif":
            assert set(table[key]) == set(parameters.COLUMNS), f"{name} {key}: {table[key]}"
            key = None
            continue
        if key is not None:
            for col, pat in _ASSIGN[gas].items():
                if m := pat.match(line):
                    table[key][col] = _unparen(m.group(1))
        elif m := _CONSTANT.match(line):
            constants[m.group(1)] = _unparen(m.group(2))
    return table, constants


def toml_table(gas: str) -> dict[int, dict[str, str]]:
    return {e.key: {c: getattr(e, c) for c in parameters.COLUMNS}
            for e in parameters.shipped(gas).elements}


@pytest.mark.parametrize("gas", fortran.GASES)
def test_the_toml_tokens_are_fcoords_literals_row_for_row(gas):
    src, _ = source_table(gas, "fcoord")
    assert len(src) == {"he": 9, "n2": 10}[gas]
    assert toml_table(gas) == src


def test_ncoords_helium_chain_is_fcoords():
    assert source_table("he", "ncoord")[0] == toml_table("he")


def test_ncoords_nitrogen_chain_differs_only_in_silicon_which_holds_iron():
    ncoord, toml = source_table("n2", "ncoord")[0], toml_table("n2")
    assert {k for k in toml if ncoord[k] != toml[k]} == {28}
    assert (ncoord[28]["epsilon"], ncoord[28]["sigma"]) == (toml[56]["epsilon"], toml[56]["sigma"])
    assert (toml[28]["epsilon"], toml[28]["sigma"]) == ("0.4020", "4.2950")


@pytest.mark.parametrize("reader", ["fcoord", "ncoord"])
def test_the_combining_constants_are_the_sources(reader):
    assert source_table("n2", reader)[1] == parameters.shipped("n2").constants
    assert source_table("he", reader)[1] == {}
    assert parameters.shipped("he").constants == {}


@pytest.mark.parametrize("gas", fortran.GASES)
def test_every_literal_renders_verbatim(gas):
    ps = parameters.shipped(gas)
    for e in ps.elements:
        for c, tok in zip(parameters.COLUMNS, e.tokens()[1:], strict=True):
            if getattr(e, c) not in parameters.EXPRESSIONS:
                assert tok == getattr(e, c)
    assert [c in parameters.EXPRESSIONS for e in ps.elements for c in
            (e.mass, e.epsilon, e.sigma, e.rhs)].count(True) == (1 if gas == "he" else 0)


# --- the two expressions --------------------------------------------------------------------

# Each expression as the 2012 source writes it, compiled and folded by gfortran 16.2.0 (MSYS2,
# Rev3) under the recorded flags, Windows 11, 2026-10-22, printed as its 64-bit pattern; the
# same measurement read every rendered token of both files back at run time by its declared
# kind and found all 80 bit-identical to the compiled constants (lab record, task 14).
COMPILED_FOLDS = {
    "3.97d0/1.12246d0": "400c4b84c985e8c9",
    "4.2d0*0.01036427d0": "3fa6498e35daa4c9",
}


def _bits(x: float) -> str:
    return struct.pack(">d", x).hex()


@pytest.mark.parametrize("expr", parameters.EXPRESSIONS)
def test_an_expression_renders_to_the_compiled_fold(expr):
    assert _bits(parameters.evaluate(expr)) == COMPILED_FOLDS[expr]
    tok = parameters.rendered_token(expr)
    assert re.fullmatch(r"\d\.\d{16}d[+-]\d\d", tok), tok  # 17 significant digits
    assert _bits(float(tok.replace("d", "e"))) == COMPILED_FOLDS[expr]


def test_the_rendered_expressions():
    assert parameters.rendered_token("3.97d0/1.12246d0") == "3.5368743652335053d+00"
    assert parameters.rendered_token("4.2d0*0.01036427d0") == "4.3529933999999999d-02"


# --- the files and their pins ---------------------------------------------------------------

def test_both_shipped_files_are_pinned_and_verify():
    assert set(parameters.SHA256) == set(parameters.FILES.values())
    assert parameters.verify() == []
    for gas in fortran.GASES:
        ps = parameters.shipped(gas)
        assert ps.shipped and ps.sha256 == parameters.SHA256[parameters.FILES[gas]]


def test_verify_catches_a_changed_or_missing_file(tmp_path):
    for name in parameters.FILES.values():
        (tmp_path / name).write_bytes((parameters.PARAMETERS_DIR / name).read_bytes())
    assert parameters.verify(tmp_path) == []
    p = tmp_path / "mobcal_N2.toml"
    p.write_bytes(p.read_bytes().replace(b'"0.4020"', b'"0.4020d0"'))
    (tmp_path / "mobcal_He.toml").unlink()
    problems = parameters.verify(tmp_path)
    assert problems[0] == "mobcal_He.toml: missing"
    assert problems[1].startswith("mobcal_N2.toml: sha256 ")


def test_a_copy_loads_but_is_not_shipped(tmp_path):
    p = tmp_path / "mine.toml"
    text = parameters.default_path("he").read_text(encoding="utf-8")
    p.write_text(text.replace('name = "MOBCAL 2012 helium"', 'name = "my helium"'),
                 encoding="utf-8")
    ps = parameters.load(p, gas="he")
    assert ps.name == "my helium" and not ps.shipped
    assert ps.record() == {"path": str(p), "name": "my helium", "format": 1, "gas": "He",
                           "sha256": ps.sha256, "shipped": False, "rendered": "parameters.tab"}


# --- the rendered table ---------------------------------------------------------------------

def test_the_rendered_helium_table(tmp_path):
    ps = parameters.shipped("he")
    out = ps.render(tmp_path)
    assert out == tmp_path / "parameters.tab"
    data = out.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
    lines = data.decode("ascii").splitlines()
    assert lines[:4] == [f"MOBCAL-LJ 1 He MOBCAL_2012_helium {ps.sha256}", "8 8 8 8", "9",
                         "1 1.008d0 0.6175d-03 2.2610d0 2.2d0"]
    assert lines[8] == "23 22.99d0 0.0278d-3 3.5368743652335053d+00 2.853d0"
    assert len(lines) == 3 + 9


def test_the_rendered_nitrogen_table(tmp_path):
    ps = parameters.shipped("n2")
    lines = ps.render(tmp_path).read_text(encoding="ascii").splitlines()
    assert lines[:5] == [f"MOBCAL-LJ 1 N2 MOBCAL_2012_nitrogen {ps.sha256}", "8 4 4 8",
                         "0.06900d0 3.6600d0 4.3529933999999999d-02 0.890898718d0", "10",
                         "1 1.008d0 0.0189 1.2409 2.2d0"]
    assert "28 28.09d0 0.4020 4.2950 2.95d0" in lines
    assert len(lines) == 4 + 10


@pytest.mark.parametrize("gas", fortran.GASES)
def test_a_rendered_table_is_list_directed_safe(gas, tmp_path):
    text = parameters.shipped(gas).render(tmp_path).read_text(encoding="ascii")
    assert not set("/,'\"*!\t") & set(text)
    for line in text.splitlines():
        assert line == " ".join(line.split())  # single blanks, nothing at either end
        assert all(len(tok) <= parameters.MAX_TOKEN for tok in line.split()[:4]
                   if not tok.startswith("MOBCAL"))


# --- refusals, one per rule -----------------------------------------------------------------

def _variant(tmp_path: Path, gas: str, old: str, new: str) -> Path:
    """The shipped file with the first occurrence of ``old`` outside a comment replaced."""
    text = parameters.default_path(gas).read_text(encoding="utf-8")
    i = text.find(old)
    while i >= 0 and "#" in text[text.rfind("\n", 0, i) + 1:i]:
        i = text.find(old, i + 1)
    assert i >= 0, old
    p = tmp_path / f"variant-{gas}.toml"
    p.write_text(text[:i] + new + text[i + len(old):], encoding="utf-8")
    return p


REFUSALS = [
    ("not TOML", "he", "format = 1", "format = = 1", "not a TOML file"),
    ("unknown key", "he", "format = 1", "format = 1\nversion = 2", "unknown key 'version'"),
    ("unknown format", "he", "format = 1", "format = 2", "format is 2"),
    ("format a string", "he", "format = 1", 'format = "1"', "format is '1'"),
    ("name with a slash", "he", '"MOBCAL 2012 helium"', '"MOBCAL 2012/helium"', "name"),
    ("name blank at the end", "he", '"MOBCAL 2012 helium"', '"MOBCAL 2012 helium "', "name"),
    ("unknown gas", "he", 'gas = "He"', 'gas = "Ar"', "gas is 'Ar'"),
    ("form the program lacks", "he", 'form = "pair"', 'form = "combining"',
     "implements 'pair' only"),
    ("unknown form", "n2", 'form = "combining"', 'form = "mixed"', "form is 'mixed'"),
    ("kinds incomplete", "he", 'rhs = "double"\n', "", r"\[kinds\] must declare exactly"),
    ("unknown kind", "he", 'mass = "double"', 'mass = "quad"', r"\[kinds\]: mass is 'quad'"),
    ("combining in a pair file", "he", "[kinds]", '[combining]\neogas = "1.0d0"\n\n[kinds]',
     r"\[combining\] is for form"),
    ("a combining constant missing", "n2", 'convr = "0.890898718d0"\n', "",
     r"\[combining\] must give exactly"),
    ("a single-precision constant", "n2", 'rogas = "3.6600d0"', 'rogas = "3.6600"',
     r"\[combining\] rogas: '3.6600' is spelled single"),
    ("an element without a field", "he", 'rhs_status = "own"\n', "", "element 1: no rhs_status"),
    ("an unknown element field", "he", 'symbol = "C"', 'symbol = "C"\ncharge = "0.0d0"',
     "element 12: unknown field 'charge'"),
    ("a duplicate key", "he", "key = 14", "key = 12", "element 12: key 12 appears twice"),
    ("a key that is not a positive integer", "he", "key = 14", "key = 0",
     "element 3: key must be a positive integer"),
    ("a key as a string", "he", "key = 14", 'key = "14"', "element 3: key must be"),
    ("a number as a TOML float", "he", 'epsilon = "1.3266d-3"', "epsilon = 1.3266e-3",
     "element 12: epsilon: must be a string"),
    ("a single literal in a double column", "he", 'rhs = "2.95d0"', 'rhs = "2.95"',
     "element 28: rhs: '2.95' is spelled single precision and the column is declared double"),
    ("a double literal in a single column", "n2", 'epsilon = "0.4020"', 'epsilon = "0.4020d0"',
     "element 28: epsilon: '0.4020d0' is spelled double"),
    ("an operator outside the two expressions", "he", 'sigma = "3.0126d0"',
     'sigma = "3.0126d0*1.0d0"', "element 12: sigma: .* an operator is allowed only"),
    ("an E exponent", "he", 'sigma = "3.0126d0"', 'sigma = "3.0126e0"',
     "element 12: sigma: '3.0126e0' is not a Fortran real literal"),
    ("a comma", "he", 'sigma = "3.0126d0"', 'sigma = "3,0126d0"', "not a Fortran real literal"),
    ("a blank", "he", 'sigma = "3.0126d0"', 'sigma = "3.0126 d0"', "not a Fortran real literal"),
    ("no decimal point", "he", 'mass = "12.01d0"', 'mass = "12d0"', "not a Fortran real literal"),
    ("a sign", "he", 'mass = "12.01d0"', 'mass = "-12.01d0"', "not a Fortran real literal"),
    ("zero", "he", 'epsilon = "1.3266d-3"', 'epsilon = "0.0d0"', "is not positive"),
    ("too long", "he", 'mass = "12.01d0"', 'mass = "12.010000000000000000000000000000d0"',
     "longer than 32"),
    ("an unknown status", "he", 'status = "fitted"', 'status = "guessed"', "element 1: status"),
    ("an unknown rhs_status", "he", 'rhs_status = "own"', 'rhs_status = "lent"', "rhs_status"),
    ("a provenance of two lines", "he", 'provenance = "fitted to the mobility of C60',
     'provenance = """fitted\nto the mobility of C60', "element 12: provenance must be one"),
    ("a symbol that is not one", "he", 'symbol = "C"', 'symbol = "carbon"', "symbol 'carbon'"),
]


@pytest.mark.parametrize("gas,old,new,match", [r[1:] for r in REFUSALS],
                         ids=[r[0] for r in REFUSALS])
def test_a_bad_file_is_refused_naming_where(tmp_path, gas, old, new, match):
    if old.startswith('provenance = "fitted to the mobility of C60'):
        text = parameters.default_path(gas).read_text(encoding="utf-8")
        line = next(s for s in text.splitlines() if s.startswith(old))
        new = line.replace(old, new).replace('(2012 source)"', '(2012 source)"""')
        old = line
    p = _variant(tmp_path, gas, old, new)
    with pytest.raises(ParameterError, match=match) as e:
        parameters.load(p)
    assert str(e.value).startswith(str(p))


def test_a_table_for_the_other_gas_is_refused():
    with pytest.raises(ParameterError, match="is a table for N2, not He"):
        parameters.load(parameters.default_path("n2"), gas="he")


def test_no_elements_is_refused(tmp_path):
    p = tmp_path / "empty.toml"
    p.write_text('format = 1\nname = "x"\ngas = "He"\nform = "pair"\nelement = []\n'
                 '[kinds]\nmass = "double"\nepsilon = "double"\nsigma = "double"\n'
                 'rhs = "double"\n', encoding="utf-8")
    with pytest.raises(ParameterError, match="0 elements"):
        parameters.load(p)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(ParameterError, match="cannot read"):
        parameters.load(tmp_path / "none.toml")


# --- the command line -----------------------------------------------------------------------

@pytest.mark.parametrize("gas", fortran.GASES)
def test_render_parameters_writes_what_the_driver_writes(tmp_path, capsys, gas):
    assert cli.main(["render-parameters", gas, str(tmp_path / "here")]) == 0
    got = (tmp_path / "here" / "parameters.tab").read_bytes()
    assert got == parameters.shipped(gas).render(tmp_path).read_bytes()
    assert capsys.readouterr().out.startswith(f"wrote {tmp_path / 'here' / 'parameters.tab'}")


def test_render_parameters_refuses_a_table_for_the_other_gas(tmp_path, capsys):
    rc = cli.main(["render-parameters", "he", str(tmp_path),
                   "--parameters", str(parameters.default_path("n2"))])
    assert rc == 2 and "is a table for N2, not He" in capsys.readouterr().err
    assert not (tmp_path / "parameters.tab").exists()


def test_run_refuses_a_bad_table_before_anything_runs(tmp_path, capsys):
    bad = _variant(tmp_path, "he", 'rhs = "2.95d0"', 'rhs = "2.95"')
    rc = cli.main(["run", str(fortran.FORTRAN_DIR / "Choline.mfj"), "--parameters", str(bad),
                   "--out", str(tmp_path / "runs")])
    assert rc == 2 and "element 28: rhs" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()


def test_run_refuses_a_table_the_program_would_not_read(tmp_path, capsys):
    mine = _variant(tmp_path, "he", '"MOBCAL 2012 helium"', '"my helium"')
    rc = cli.main(["run", str(fortran.FORTRAN_DIR / "Choline.mfj"), "--parameters", str(mine),
                   "--out", str(tmp_path / "runs")])
    assert rc == 2 and "do not yet read parameters.tab" in capsys.readouterr().err


@pytest.mark.parametrize("gas", ["he", "both"])
def test_run_refuses_a_table_for_another_gas(tmp_path, capsys, gas):
    rc = cli.main(["run", str(fortran.FORTRAN_DIR / "Choline.mfj"), "--gas", gas,
                   "--parameters", str(parameters.default_path("n2")),
                   "--out", str(tmp_path / "runs")])
    assert rc == 2 and "is a table for N2; run it with --gas n2" in capsys.readouterr().err
