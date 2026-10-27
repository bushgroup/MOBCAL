"""The window, headless (``QT_QPA_PLATFORM=offscreen``), through pytest-qt and the stand-in binary.

Each test gets its own settings file and queue directory, so nothing reads or writes the
user's. Dialogs the window would show are answered by patching ``QMessageBox`` and
``QFileDialog``; the runs are the stand-in's, milliseconds each, through the same worker thread
and driver as a real batch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from mobcal import batch as batches  # noqa: E402
from mobcal import cli, fortran, methods  # noqa: E402
from mobcal.app import window as win  # noqa: E402
from mobcal.app.store import Store  # noqa: E402
from mobcal.app.window import MainWindow  # noqa: E402
from mobcal.run import Job  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fake_mobcal.py"
CHOLINE = fortran.FORTRAN_DIR / "Choline.mfj"
ORCA = Path(__file__).resolve().parent / "data" / "qm" / "orca"


def launcher(job: Job) -> list[str]:
    return [sys.executable, str(FAKE), job.gas]


def write_input(path: Path, label: str) -> Path:
    body = CHOLINE.read_text(encoding="latin-1").split("\n", 1)[1]
    path.write_text(f"{label}\n{body}", encoding="latin-1", newline="\n")
    return path


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    store = Store(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
                  data_dir=tmp_path / "appdata")
    w = MainWindow(store, launcher=launcher, cpus=8)
    w.out_edit.setText(str(tmp_path / "results"))
    qtbot.addWidget(w)
    answers: list = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: answers.pop(0) if answers
                        else QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda _, title, text: w._warnings.append(text))
    w._warnings = []
    w._answers = answers
    yield w
    if w.worker is not None:
        w.worker.stop()
        w.worker.wait(10_000)


def add(qtbot, w: MainWindow, *paths: Path) -> None:
    w.inputs.add_paths(list(paths))
    qtbot.waitUntil(lambda: not w.inputs.busy, timeout=60_000)


def wait_idle(qtbot, w: MainWindow, timeout: int = 30_000) -> None:
    qtbot.waitUntil(lambda: w.worker is None and w.queue.count() == 0, timeout=timeout)


# --- the form ------------------------------------------------------------------------------

def test_a_method_fills_every_field_and_an_edit_makes_it_custom(window):
    w = window
    assert w.method_combo.currentText() == "Current" and w.gases == ("he",)
    w.apply_method("2000")
    assert w.table_value() == "2000" and w.generator_combo.currentData() == "ranlux"
    assert w.temperature.value() == 298.0 and w.counts["imp"].value() == 25
    assert w.method_combo.currentText() == "MOBCAL 2000"
    w.counts["imp"].setValue(50)
    assert w.method_combo.currentText() == "Custom (from MOBCAL 2000)"
    w.counts["imp"].setValue(25)
    assert w.method_combo.currentText() == "MOBCAL 2000"
    w.apply_method("2012")
    assert w.table_value() == "2012" and w.temperature.value() == 301.0
    w.generator_combo.setCurrentIndex(w.generator_combo.findData("philox"))
    assert w.method_combo.currentText() == "Current"


def test_both_gases_offer_only_the_tables_both_have(window):
    w = window
    w.apply_method("2000")
    w.gas_combo.setCurrentIndex(2)
    assert w.gases == ("he", "n2") and w.table_value() == "2012"
    assert [w.table_combo.itemData(i) for i in range(w.table_combo.count())] == ["2012"]
    assert w.method_combo.currentText() == "Custom (from MOBCAL 2000)"
    w.apply_method("2000")
    assert w.gases == ("he",)


def test_the_form_makes_the_batch_the_command_line_makes(window, tmp_path):
    w = window
    add_paths = [CHOLINE]
    w.inputs.add_paths(add_paths)
    w.apply_method("2000")
    w.seeds_spin.setValue(3)
    b = w.form_batch()
    by_cli = cli.batch_from_args(cli.parser().parse_args(
        ["run", str(CHOLINE), "--method", "2000", "--seeds", "5013489,5013490,5013491",
         "--out", w.out_edit.text()]))
    assert b.jobs() == by_cli.jobs() and b.title() == "MOBCAL 2000"


def test_the_estimate_and_the_run_button(window, qtbot):
    w = window
    assert not w.run_button.isEnabled() and "add an input" in w.estimate_label.text()
    add(qtbot, w, CHOLINE)
    assert w.run_button.isEnabled()
    assert w.estimate_label.text().startswith("Current: 1 run on 1 worker, each across 8 "
                                              "processes; about")
    w.counts["itn"].setValue(100)
    w.counts["inp"].setValue(100)  # 100 * 100 * 1000 points: over the program's 9,999,999
    assert not w.run_button.isEnabled() and "points per coordinate set" in \
        w.estimate_label.text()


# --- running ---------------------------------------------------------------------------

def test_a_batch_runs_and_fills_the_results(window, qtbot, tmp_path):
    w = window
    a = write_input(tmp_path / "a.mfj", "ok")
    bad = write_input(tmp_path / "bad.mfj", "refuse")
    add(qtbot, w, a, bad)
    w.seeds_spin.setValue(3)
    w.gas_combo.setCurrentIndex(2)
    w.run_clicked()
    wait_idle(qtbot, w)
    rows = w.result_rows()
    assert [(r.input.stem, r.gas) for r in rows] == [("a", "he"), ("a", "n2"), ("bad", "he"),
                                                       ("bad", "n2")]
    tm = [50 + s % 7 + 0.5 for s in (5013489, 5013490, 5013491)]
    assert rows[0].value("TM") == methods.summary_line(tm)
    assert rows[0].status == "ok (3 seeds)" and rows[2].status == "failed 3 of 3"
    assert w.results_table.item(0, 2).text() == methods.summary_line(tm)
    assert w.results_table.item(1, 3).text() == ""  # no PA in nitrogen
    summary = json.loads((tmp_path / "results" / "summary.json").read_text(encoding="utf-8"))
    assert len(summary["runs"]) == 12 and {r["method"] for r in summary["runs"]} == {"current"}
    assert w.methods_button.isEnabled()
    w.copy_methods_text()
    text = QGuiApplication.clipboard().text()
    assert text.startswith("Collision cross sections were calculated by the trajectory method")
    assert "at 3 seeds per structure" in text
    w.copy_results()
    assert QGuiApplication.clipboard().text().splitlines()[0].startswith("ion\tinput\tgas\tTM")


def test_run_while_running_queues_and_the_queue_survives(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 2"))
    w.run_clicked()
    assert w.worker is not None and w.run_button.text() == "Add to queue"
    w.seeds_spin.setValue(2)
    w.run_clicked()
    w.apply_method("2012")
    w.run_clicked()
    assert w.queue.count() == 2
    saved, problems = batches.load(w.store.queue_path)
    assert [b.title() for b in saved] == ["Current", "MOBCAL 2012"] and not problems
    assert saved[0].seeds == (5013489, 5013490)
    # The second launch offers them back.
    w2 = MainWindow(w.store, launcher=launcher, cpus=8)
    qtbot.addWidget(w2)
    w2.offer_saved_queue()
    assert [b.title() for b in w2.queued()] == ["Current", "MOBCAL 2012"]
    w2.queue.clear()
    w2.save_queue()
    wait_idle(qtbot, w, 60_000)
    assert batches.load(w.store.queue_path) == ([], [])


def test_stop_asks_then_stops_the_batch(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 60"))
    w.run_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w._answers.append(QMessageBox.StandardButton.No)
    w.stop_clicked()
    assert not w.worker.stopping
    w.stop_clicked()
    wait_idle(qtbot, w)
    assert w.result_rows()[0].status == "stopped"


def test_closing_asks_then_stops_and_keeps_the_queue(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 60"))
    w.run_clicked()
    w.run_clicked()  # queued
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w._answers.append(QMessageBox.StandardButton.No)
    assert not w.close() and w.worker is not None
    worker = w.worker
    assert w.close()
    assert worker.isFinished() and worker.stopping
    assert len(batches.load(w.store.queue_path)[0]) == 1


def test_a_run_the_folder_holds_is_skipped_or_run_again(window, qtbot, tmp_path, monkeypatch):
    w = window
    add(qtbot, w, write_input(tmp_path / "a.mfj", "ok"))
    w.run_clicked()
    wait_idle(qtbot, w)
    clicked = []

    def exec_(box):
        buttons = {b.text(): b for b in box.buttons()}
        box._clicked = buttons[clicked[0]]
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    clicked[:] = ["Skip them"]
    w.run_clicked()
    wait_idle(qtbot, w)
    assert "did not run: nothing to run" in w.status_label.text()
    clicked[:] = ["Run them again"]
    w.run_clicked()
    wait_idle(qtbot, w)
    assert w.result_rows()[0].status == "ok"


def test_another_input_of_the_same_name_is_refused(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "a.mfj", "ok"))
    w.run_clicked()
    wait_idle(qtbot, w)
    other = tmp_path / "other"
    other.mkdir()
    w.inputs.clear()
    add(qtbot, w, write_input(other / "a.mfj", "sets 2"))
    w.run_clicked()
    assert w.worker is None and "another input of the same name" in w._warnings[-1]


# --- imports ------------------------------------------------------------------------------

def test_an_orca_output_with_chelpg_is_preselected_and_imported_at_run(window, qtbot):
    w = window
    add(qtbot, w, ORCA / "choline_sp" / "choline_sp.out", ORCA / "choline_opt" / "choline_opt.out")
    sp, opt = w.inputs.items
    assert sp.charges == "chelpg" and sp.atoms == 21 and not sp.problem()
    assert opt.charges is None and opt.problem().endswith("choose its charges")
    assert not w.run_button.isEnabled()
    combo = w.inputs.table.cellWidget(1, 3)
    assert combo.itemData(combo.count() - 1) == "uniform"
    combo.setCurrentIndex(combo.findData("mulliken"))
    assert w.run_button.isEnabled()
    b = w.form_batch()
    assert [p.name for p in b.inputs] == ["choline_sp_chelpg.mfj", "choline_opt_mulliken.mfj"]
    w.launcher = launcher
    for item in w.inputs.items:
        item.write(w.out_dir, w.gases)
    rec = json.loads((w.out_dir / "imported" / "choline_sp_chelpg.import.json").read_text(
        encoding="utf-8"))
    assert rec["charges"]["choice"] == "chelpg"


def test_an_xyz_asks_for_its_net_charge(window, qtbot):
    w = window
    add(qtbot, w, ORCA / "choline_opt" / "choline_opt.xyz")
    item = w.inputs.items[0]
    assert item.needs_net_charge and item.charges is None
    combo = w.inputs.table.cellWidget(0, 3)
    combo.setCurrentIndex(combo.findData("uniform"))
    assert item.problem().endswith("give the ion's net charge")
    w.inputs.table.cellWidget(0, 4).setValue(1)
    assert not item.problem() and w.run_button.isEnabled()


def test_an_unreadable_input_says_why(window, qtbot, tmp_path):
    w = window
    junk = tmp_path / "junk.mfj"
    junk.write_text("not a structure\n", encoding="ascii")
    add(qtbot, w, junk)
    assert w.inputs.items[0].state == "error" and not w.run_button.isEnabled()


# --- the platform -------------------------------------------------------------------------

def test_the_window_opens_from_the_command_line(qtbot, monkeypatch):
    calls = []
    import mobcal.app
    monkeypatch.setattr(mobcal.app, "main",
                        lambda argv=None, check=False: calls.append(check) or 0)
    assert cli.main(["gui"]) == 0 and cli.main(["gui", "--check"]) == 0
    assert calls == [False, True]


def test_the_window_starts_and_closes_by_itself():
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    p = subprocess.run([sys.executable, "-m", "mobcal.cli", "gui", "--check"], env=env,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("window opened and closed on offscreen, Qt 6.")


def test_the_linux_platform_library_check(monkeypatch):
    import mobcal.app as app
    monkeypatch.setattr(app.sys, "platform", "linux")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    assert app.missing_platform_library() is None
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.setattr(app.ctypes.util, "find_library", lambda name: None)
    assert "libxcb-cursor0" in app.missing_platform_library()
    monkeypatch.setattr(app.ctypes.util, "find_library", lambda name: "libxcb-cursor.so.0")
    assert app.missing_platform_library() is None


def test_a_calculation_never_loads_qt():
    code = ("import sys; from mobcal import cli, run, batch, estimate, methods; "
            "cli.main(['version']); print('PySide6' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True).stdout.split()
    assert out[-1] == "False"
    assert win.seeds(3) == (5013489, 5013490, 5013491)
