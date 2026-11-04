"""What a split run leaves of its scratch, through the stand-in binary: ``Job.scratch``
(``delete``, ``zip``, ``keep``), the harvest into ``record.json`` before anything goes, a removal
that fails, the runs that keep everything, and ``mobcal clean`` on folders already on disk."""

from __future__ import annotations

import json
import threading
import time
import zipfile
from pathlib import Path

import pytest

from mobcal import clean, cli, methods, run
from mobcal.io.block import BLOCKS_PER_SET, block_name
from mobcal.run import Job, Stop, run_one
from test_run import CHOLINE, launcher, write_input


def _record(job: Job) -> dict:
    return json.loads((job.run_dir / "record.json").read_text(encoding="utf-8"))


def _left(job: Job) -> set[str]:
    return {p.name for p in job.run_dir.iterdir()}


@pytest.mark.parametrize("dealing", ["claimed", "static"])
def test_delete_leaves_the_inputs_the_output_and_the_record(tmp_path, dealing):
    inp = write_input(tmp_path / "ok.mfj", "ok")
    serial = run_one(Job(inp, "he", 5013489, tmp_path / "serial"), launcher)
    job = Job(inp, "he", 5013489, tmp_path / "runs", split=3, dealing=dealing)
    assert job.scratch == "delete"  # the default
    r = run_one(job, launcher)
    assert r.ok, r.message
    assert r.cross_sections == serial.cross_sections
    assert _left(job) == {"ok.mfj", "mobcal.in", "mobcal.out", "stdout.log", "parameters.tab",
                          "settings.tab", "record.json"}
    rec = _record(job)
    s = rec["scratch"]
    assert s["mode"] == "delete" and s["left"] == [] and "zip" not in s
    assert s["removed"] == {"worker_folders": 3, "claim_files": BLOCKS_PER_SET if dealing ==
                            "claimed" else 0, "block_files": BLOCKS_PER_SET}
    h = rec["split"]
    assert [e["worker"] for e in h["workers"]] == [1, 2, 3]
    assert sum(e["blocks"] for e in h["workers"]) == BLOCKS_PER_SET
    assert all(e["returncode"] == 0 for e in h["workers"])
    assert all(0 <= e["start"] <= e["end"] for e in h["workers"])
    assert h["diagnostics"] == []  # the stand-in prints none; test_split has real ones
    if dealing == "claimed":
        (row,) = h["claims"]
        ws = [int(x) for x in row.split()]
        assert len(ws) == BLOCKS_PER_SET and set(ws) <= {1, 2, 3}
        assert [ws.count(w) for w in (1, 2, 3)] == [e["blocks"] for e in h["workers"]]
    else:
        assert h["claims"] is None
        assert [e["blocks"] for e in h["workers"]] == [134, 133, 133]
    # the scratch mode is no setting of the calculation
    assert rec["method"] == methods.DEFAULT and r.job.label == "ok-he-5013489"
    assert Job(inp, "he", 1, tmp_path, split=3, scratch="keep") == Job(inp, "he", 1, tmp_path,
                                                                        split=3)


def test_zip_packs_the_block_files(tmp_path):
    lines = CHOLINE.read_text(encoding="latin-1").splitlines()
    atoms = lines[6:6 + int(lines[2])]
    two = tmp_path / "x.mfj"
    two.write_text("\n".join(["sets 2", "2", *lines[2:6], *atoms, "", *atoms]) + "\n",
                   encoding="latin-1", newline="\n")
    job = Job(two, "he", 7, tmp_path, split=2, scratch="zip")
    r = run_one(job, launcher)
    assert r.ok, r.message
    assert not any(job.run_dir.glob("w0*")) and not any(job.run_dir.glob("claim-*"))
    assert not any(job.run_dir.glob("block-*.dat"))
    with zipfile.ZipFile(job.run_dir / run.BLOCKS_ZIP) as z:
        names = sorted(z.namelist())
    assert names == sorted(block_name(s, k) for s in (1, 2) for k in range(1, BLOCKS_PER_SET + 1))
    s = _record(job)["scratch"]
    assert s["zip"] == run.BLOCKS_ZIP and s["zipped"] == 2 * BLOCKS_PER_SET
    assert s["removed"]["block_files"] == 2 * BLOCKS_PER_SET
    assert len(_record(job)["split"]["claims"]) == 2  # one row per coordinate set


def test_keep_leaves_everything_and_copies_the_blocks(tmp_path):
    job = Job(write_input(tmp_path / "x.mfj", "ok"), "he", 7, tmp_path, split=2, scratch="keep")
    assert run_one(job, launcher).ok
    d = job.run_dir
    assert len(list(d.glob("block-*.dat"))) == BLOCKS_PER_SET
    assert len(list(d.glob("claim-*"))) == BLOCKS_PER_SET
    assert sum(len(list(job.worker_dir(w).glob("block-*.dat"))) for w in (1, 2)) == BLOCKS_PER_SET
    assert (job.worker_dir(1) / "x.mfj").is_file()  # keep keeps the staged copies too
    rec = _record(job)
    assert rec["scratch"] == {"mode": "keep"} and "split" in rec


def test_a_file_that_cannot_be_deleted_is_logged_and_left(tmp_path, monkeypatch, caplog):
    job = Job(write_input(tmp_path / "x.mfj", "ok"), "he", 7, tmp_path, split=2)
    held = job.run_dir / "claim-001-00001"
    real = Path.unlink

    def unlink(self, missing_ok=False):
        if self == held:
            raise PermissionError(13, "held open by another process")
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    r = run_one(job, launcher)
    assert r.ok and r.message == ""  # never a run failure
    s = _record(job)["scratch"]
    assert s["left"] == ["claim-001-00001"] and s["removed"]["claim_files"] == BLOCKS_PER_SET - 1
    assert "could not delete claim-001-00001" in caplog.text
    monkeypatch.undo()
    # what it left, clean takes later
    (c,) = clean.plan([tmp_path])
    assert (c.claim_files, c.worker_folders, c.block_files) == (1, 0, 0)
    clean.apply(c)
    assert not held.exists() and clean.plan([tmp_path]) == []


def test_failed_and_stopped_runs_keep_everything(tmp_path):
    lazy = Job(write_input(tmp_path / "lazy.mfj", "lazy"), "he", 1, tmp_path, split=2)
    r = run_one(lazy, launcher)
    assert not r.ok
    assert all(lazy.worker_dir(w).is_dir() for w in (1, 2)) and any(lazy.run_dir.glob("claim-*"))
    rec = _record(lazy)
    assert rec["scratch"] == {"mode": "keep"} and "split" not in rec
    stop, started = Stop(), threading.Event()
    job = Job(write_input(tmp_path / "s.mfj", "sleep 30"), "he", 1, tmp_path, split=2)
    out: list = []
    t = threading.Thread(target=lambda: out.append(
        run_one(job, launcher, _running=stop, on_start=lambda j: started.set())))
    t.start()
    assert started.wait(30)
    time.sleep(1)
    stop()
    t.join(60)
    assert out[0].stopped
    assert all(job.worker_dir(w).is_dir() for w in (1, 2))
    assert _record(job)["scratch"] == {"mode": "keep"}


# --- mobcal clean -------------------------------------------------------------------------

def _old(tmp_path, name: str, label: str = "ok", **kw) -> Job:
    """A finished run as a version before cleanup left it: kept, without its harvest."""
    job = Job(write_input(tmp_path / f"{name}.mfj", label), "he", 3, tmp_path / "study",
              scratch="keep", **kw)
    run_one(job, launcher)
    rec = _record(job)
    rec.pop("split", None)
    rec.pop("scratch", None)
    run.dump_record(rec, job.run_dir / "record.json")
    return job


def test_clean_is_a_dry_run_until_applied_then_finds_nothing(tmp_path, capsys):
    ok = _old(tmp_path, "a", split=3)
    failed = _old(tmp_path, "b", "lazy", split=2)
    serial = _old(tmp_path, "c")
    running = _old(tmp_path, "d", split=2)
    (running.run_dir / "record.json").unlink()  # a run in flight has no record
    before = {j.label: sorted(p.relative_to(j.run_dir) for p in j.run_dir.rglob("*"))
              for j in (ok, failed, serial, running)}
    rec0 = _record(ok)

    assert cli.main(["clean", str(tmp_path / "study")]) == 0
    out = capsys.readouterr().out
    assert ok.label in out and failed.label not in out and "--apply" in out
    assert "3 worker folders, 400 claim files, 400 block files" in out
    for j in (ok, failed, serial, running):  # nothing moved
        assert sorted(p.relative_to(j.run_dir) for p in j.run_dir.rglob("*")) == before[j.label]

    assert cli.main(["clean", str(tmp_path / "study"), "--apply"]) == 0
    assert {p.name for p in ok.run_dir.iterdir()} == {"a.mfj", "mobcal.in", "mobcal.out",
                                                     "stdout.log", "parameters.tab",
                                                     "settings.tab", "record.json"}
    rec = _record(ok)
    assert {k: rec[k] for k in rec0} == rec0  # no field changed, two added
    assert set(rec) - set(rec0) == {"split", "cleaned"}
    assert sum(e["blocks"] for e in rec["split"]["workers"]) == BLOCKS_PER_SET
    assert all(e["returncode"] is None for e in rec["split"]["workers"])
    assert len(rec["split"]["claims"][0].split()) == BLOCKS_PER_SET
    (entry,) = rec["cleaned"]
    assert entry["mode"] == "delete" and entry["removed"]["worker_folders"] == 3
    for j in (failed, serial, running):
        assert sorted(p.relative_to(j.run_dir) for p in j.run_dir.rglob("*")) == before[j.label]

    capsys.readouterr()
    assert cli.main(["clean", str(tmp_path / "study"), "--apply"]) == 0
    assert "nothing to clean" in capsys.readouterr().out
    assert _record(ok) == rec


def test_clean_zip_on_a_run_directory(tmp_path):
    job = _old(tmp_path, "a", split=2, dealing="static")
    (c,) = clean.plan([job.run_dir])
    entry = clean.apply(c, "zip")
    assert entry["zipped"] == BLOCKS_PER_SET and entry["left"] == []
    assert (job.run_dir / run.BLOCKS_ZIP).is_file() and not any(job.run_dir.glob("block-*"))
    assert _record(job)["split"]["claims"] is None
