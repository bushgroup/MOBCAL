"""The shared descriptions (``mobcal.options``) on the command line, and the generated
command-line page. No Qt here: the window's half is in ``test_app.py``."""

from __future__ import annotations

import argparse
from pathlib import Path

from mobcal import cli, options

ROOT = Path(__file__).resolve().parent.parent

# Each shared description, and the option of the command line that carries it.
OPTIONS = {
    "inputs": ("run", "inputs"), "method": ("run", "method"),
    "parameters": ("run", "parameters"), "seeds": ("run", "seeds"),
    "temperature": ("run", "temperature"), "rng": ("run", "rng"), "imp": ("run", "imp"),
    "itn": ("run", "itn"), "inp": ("run", "inp"), "inum": ("run", "inum"),
    "inor": ("run", "inor"), "workers": ("run", "workers"), "split": ("run", "split"),
    "mode": ("run", "mode"),
    "dealing": ("run", "dealing"), "out": ("run", "out"), "charges": ("import", "charges"),
    "net_charge": ("import", "net_charge"), "result_ion": ("run", "result_ion"),
}


def commands() -> dict[str, argparse.ArgumentParser]:
    """Every subcommand of the three commands, by its name, which no two share."""
    out: dict[str, argparse.ArgumentParser] = {}
    for prog, ap in cli.programs().items():
        sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
        assert not set(sub.choices) & set(out), prog
        out.update(sub.choices)
    return out


def program(name: str) -> str:
    """The command a subcommand belongs to."""
    return next(prog for prog, ap in cli.programs().items()
                if name in next(a for a in ap._actions
                                if isinstance(a, argparse._SubParsersAction)).choices)


def test_every_shared_description_is_an_options_help():
    cmds = commands()
    assert set(OPTIONS) | {"methods_text"} == set(options.SHARED)
    for key, (cmd, dest) in OPTIONS.items():
        action = next(a for a in cmds[cmd]._actions if a.dest == dest)
        shown = action.help.replace("%%", "%")  # as argparse prints it
        assert shown.startswith(options.SHARED[key].text), key
        assert options.SHARED[key].cli in shown, key
    assert cmds["methods-text"].description == options.cli_help("methods_text")


def test_the_help_formats_and_says_no_dash_or_line_break():
    for p in commands().values():
        p.format_help()  # argparse interpolates % here
    for key, d in options.SHARED.items():
        for text in (d.text, d.cli, d.window):
            assert "\n" not in text and "—" not in text and " - " not in text, key
    for text in [*options.WINDOW.values(),
                 *(t for cols in options.COLUMNS.values() for t in cols.values())]:
        assert "\n" not in text and "—" not in text and " - " not in text


def test_the_command_line_page_is_the_generators():
    page = (ROOT / cli.REFERENCE).read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    assert page == cli.reference(), "run uv run tools/make_command_line.py"


def test_the_page_lists_every_command_and_option():
    page = cli.reference()
    for name, p in commands().items():
        assert f"\n## {program(name)} {name}\n" in page
        for a in p._actions:
            for flag in a.option_strings:
                assert flag in page or flag in ("-h", "--help"), flag


def test_the_files_commands_are_named_for_their_formats():
    # ccs-ion and ccs-result take the names of the formats they read and write (mobcal.io.ion,
    # mobcal.io.result); mobcal keeps none of their subcommands.
    from mobcal.io import ion, result
    assert set(cli.programs()) == {"mobcal", ion.FORMAT, result.FORMAT}
    assert {program(n) for n in ("import", "export")} == {ion.FORMAT}
    assert program("unpack") == result.FORMAT
    assert set(cli.COMMANDS) == set(cli.programs())
