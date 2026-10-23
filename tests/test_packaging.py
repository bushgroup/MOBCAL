"""What the installed program relies on: build.json and the frozen layout, without a compiler."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mobcal import cli, fortran


@pytest.fixture
def built(tmp_path: Path) -> Path:
    """Two stand-in binaries recorded the way ``fortran.build`` records real ones."""
    for gas in fortran.GASES:
        p = tmp_path / fortran.binary_name(gas)
        p.write_bytes(f"not really {gas}".encode())
        fortran._record(tmp_path, gas, p, "no-such-gfortran")
    return tmp_path


def _edit(d: Path, gas: str, **fields) -> None:
    m = json.loads((d / fortran.MANIFEST).read_text())
    m["binaries"][fortran.binary_name(gas)].update(fields)
    (d / fortran.MANIFEST).write_text(json.dumps(m))


def test_recorded_binaries_verify(built):
    assert fortran.verify_binaries(built) == []
    rec = fortran.read_manifest(built)["binaries"][fortran.binary_name("he")]
    assert rec["source_sha256"] == fortran.SHA256["mobcal_He.f"]
    assert rec["include"] == "mobcal_ljread.inc"
    assert rec["include_sha256"] == fortran.SHA256["mobcal_ljread.inc"]
    assert rec["flags"] == fortran.flags()
    assert rec["compiler"] == ""  # this gfortran would not say


def test_no_manifest(tmp_path):
    assert fortran.verify_binaries(tmp_path) == [f"no readable build.json in {tmp_path}"]


def test_a_changed_binary_is_caught(built):
    (built / fortran.binary_name("n2")).write_bytes(b"something else")
    assert fortran.verify_binaries(built) == [
        f"{fortran.binary_name('n2')}: sha256 differs from the one recorded when it was built"]


def test_a_missing_binary_is_caught(built):
    (built / fortran.binary_name("he")).unlink()
    [problem] = fortran.verify_binaries(built)
    assert problem.startswith(f"{fortran.binary_name('he')}: missing")


def test_a_binary_from_other_sources_is_caught(built):
    _edit(built, "he", source_sha256="0" * 64)
    assert fortran.verify_binaries(built) == [
        f"{fortran.binary_name('he')}: built from a mobcal_He.f that is not the pinned file"]


def test_a_binary_from_another_include_is_caught(built):
    _edit(built, "n2", include_sha256="0" * 64)
    assert fortran.verify_binaries(built) == [
        f"{fortran.binary_name('n2')}: built from a mobcal_ljread.inc that is not the pinned file"]


def test_a_binary_without_fno_automatic_is_caught(built):
    _edit(built, "n2", flags=["-O3", "-std=legacy"])
    assert fortran.verify_binaries(built) == [
        f"{fortran.binary_name('n2')}: built without -fno-automatic"]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="no git")
def test_commit_is_marked_dirty_when_the_tree_has_changes(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.f").write_text("      end\n")
    _git(tmp_path, "add", "a.f")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a")
    head = _git(tmp_path, "rev-parse", "HEAD")
    assert fortran._commit(tmp_path) == head
    (tmp_path / "a.f").write_text("      stop\n      end\n")  # a change to a tracked file
    assert fortran._commit(tmp_path) == head + "-dirty"
    _git(tmp_path, "checkout", "-q", "--", "a.f")
    (tmp_path / "new.py").write_text("")  # a file HEAD does not hold
    assert fortran._commit(tmp_path) == head + "-dirty"


def test_without_git_the_commit_is_ci_s(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "f" * 40)
    monkeypatch.setattr(fortran, "_git", lambda *_: None)
    assert fortran._commit(tmp_path) == "f" * 40


def test_short_commit_keeps_the_dirty_mark():
    sha = "97b673deaaf44f605952b8ce86023eebede8f541"
    assert fortran.short_commit(sha) == "97b673deaaf4"
    assert fortran.short_commit(sha + "-dirty") == "97b673deaaf4-dirty"
    assert fortran.short_commit("") == ""


def test_every_platform_links_without_a_gfortran_runtime():
    assert set(fortran.LINK_FLAGS) == {"win32", "linux", "darwin"}
    assert fortran.LINK_FLAGS["linux"] == fortran.LINK_FLAGS["win32"] == ["-static"]
    assert {"-static-libgfortran", "-static-libquadmath"} <= set(fortran.LINK_FLAGS["darwin"])


@pytest.fixture
def frozen_at(monkeypatch, tmp_path: Path) -> Path:
    """Pretend to be the installed program at ``tmp_path/mobcal(.exe)``."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "mobcal.exe"))
    monkeypatch.delenv("MOBCAL_BIN_DIR", raising=False)
    return tmp_path.resolve()


def test_frozen_layout(frozen_at):
    assert fortran.frozen()
    assert fortran.binary_dir() == frozen_at / "fortran"
    assert fortran.examples_dir() == frozen_at / "examples"


def test_source_layout(monkeypatch):
    monkeypatch.delenv("MOBCAL_BIN_DIR", raising=False)
    assert not fortran.frozen()
    assert fortran.examples_dir() == fortran.FORTRAN_DIR
    assert (fortran.examples_dir() / "sample-output" / "Choline_He.out").is_file()


def test_build_refuses_in_an_installed_copy(frozen_at, capsys):
    assert cli.main(["build"]) == 2
    assert "installed copy" in capsys.readouterr().err
