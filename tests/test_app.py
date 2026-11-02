"""The window, headless (``QT_QPA_PLATFORM=offscreen``), through pytest-qt and the stand-in binary.

Each test gets its own settings file and queue directory, so nothing reads or writes the
user's. Dialogs the window would show are answered by patching ``QMessageBox`` and
``QFileDialog``; the runs are the stand-in's, milliseconds each, through the same worker thread
and driver as a real batch.
"""

from __future__ import annotations

import dataclasses
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QModelIndex, QRect, QSettings, Qt, QUrl  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QKeySequence,
    QPalette,
)
from PySide6.QtGui import Qt as QtGui_Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import mobcal  # noqa: E402
from mobcal import batch as batches  # noqa: E402
from mobcal import cli, docs, estimate, fortran, methods, options  # noqa: E402
from mobcal.app import inputs, theme, tip  # noqa: E402
from mobcal.app import window as win  # noqa: E402
from mobcal.app.store import Store  # noqa: E402
from mobcal.app.window import MainWindow  # noqa: E402
from mobcal.io.mfj import Atom, Mfj  # noqa: E402
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


def run(w: MainWindow) -> None:
    """Add the form's batch and start the queue, as Add batch then Start queue do."""
    w.add_batch_clicked()
    if w.state == win.IDLE and w.queued():
        w.toggle_clicked()


def wait_idle(qtbot, w: MainWindow, timeout: int = 30_000) -> None:
    qtbot.waitUntil(lambda: w.worker is None and w.queue.count() == 0, timeout=timeout)


# --- the form ------------------------------------------------------------------------------

def combo_items(c: QComboBox) -> list[str]:
    return [c.itemText(i) for i in range(c.count())]


def test_a_method_fills_every_field_and_an_edit_makes_it_custom(window):
    w = window
    assert w.method_combo.currentText() == "MOBCAL 2012 with Philox (He)" and w.gas == "he"
    assert combo_items(w.method_combo) == [m.title for m in methods.METHODS.values()]
    assert combo_items(w.gas_combo) == ["He", "N2"]
    w.apply_method("2000-he")
    assert w.table_value() == "2000" and w.generator_combo.currentData() == "ranlux"
    assert w.temperature.value() == 298.0 and w.counts["imp"].value() == 25
    assert w.method_combo.currentText() == "MOBCAL 2000 (He)"
    w.counts["imp"].setValue(50)
    assert w.method_combo.currentText() == "Custom (from MOBCAL 2000 (He))"
    w.counts["imp"].setValue(25)
    assert w.method_combo.currentText() == "MOBCAL 2000 (He)"
    w.apply_method("2012-he")
    assert w.table_value() == "2012" and w.temperature.value() == 301.0
    w.generator_combo.setCurrentIndex(w.generator_combo.findData("philox"))
    assert w.method_combo.currentText() == "MOBCAL 2012 with Philox (He)"


def test_the_gas_is_a_field_of_the_method(window):
    w = window
    w.apply_method("2012-he")
    w.gas_combo.setCurrentIndex(w.gas_combo.findData("n2"))
    assert w.method_combo.currentText() == "MOBCAL 2012 (N2)"
    assert [w.table_combo.itemData(i) for i in range(w.table_combo.count())] == \
        ["2012", win.OTHER_TABLE]
    w.apply_method("2000-he")
    w.gas_combo.setCurrentIndex(w.gas_combo.findData("n2"))
    assert w.table_value() == "2012"  # nitrogen has no 2000 table
    assert w.method_combo.currentText() == "Custom (from MOBCAL 2000 (He))"
    w.apply_method("2012-philox-n2")
    assert w.gas == "n2" and w.method_combo.currentText() == "MOBCAL 2012 with Philox (N2)"


def test_the_form_makes_the_batch_the_command_line_makes(window, tmp_path):
    w = window
    add_paths = [CHOLINE]
    w.inputs.add_paths(add_paths)
    w.apply_method("2000-he")
    w.seeds_spin.setValue(3)
    b = w.form_batch()
    by_cli = cli.batch_from_args(cli.parser().parse_args(
        ["run", str(CHOLINE), "--method", "2000-he", "--seeds", "5013489,5013490,5013491",
         "--out", w.out_edit.text()]))
    assert b.jobs() == by_cli.jobs() and b.title() == "MOBCAL 2000 (He)"


# --- method files -------------------------------------------------------------------------

def test_save_method_writes_the_fields_and_load_method_adds_the_file(window, qtbot, tmp_path):
    w = window
    w.inputs.add_paths([CHOLINE])
    w.apply_method("2012-n2")
    w.counts["itn"].setValue(5)
    fields = w.form_batch()
    m = w.save_method(tmp_path / "five cycles.toml", "Five cycles (N2)")
    assert m is not None and (m.gas, m.generator, m.settings.itn) == ("n2", "ranlux", 5)
    assert w.method_combo.currentText() == "Five cycles (N2)"
    assert combo_items(w.method_combo)[-1] == "Five cycles (N2)"
    saved = w.form_batch()
    assert saved.jobs() == fields.jobs() and saved.title() == "Five cycles (N2)"
    assert {j.method for j in saved.jobs()} == {"Five cycles (N2)"}
    assert w.store.methods == [(m.ref, m.sha256)]
    # An edit makes it Custom, and picking it fills the fields again.
    w.counts["itn"].setValue(6)
    assert w.method_combo.currentText() == "Custom (from Five cycles (N2))"
    w.apply_method(m.ref)
    assert w.counts["itn"].value() == 5
    # The next launch lists it; loading another file of the same name is refused.
    w2 = MainWindow(w.store, launcher=launcher, cpus=8)
    qtbot.addWidget(w2)
    assert combo_items(w2.method_combo)[-1] == "Five cycles (N2)" and not w2.dropped
    assert w2.method_combo.currentText() == "Five cycles (N2)"  # the method last picked
    twin = tmp_path / "twin.toml"
    twin.write_bytes(m.path.read_bytes())
    assert w2.load_method(twin) is None
    assert "already holds 'Five cycles (N2)'" in w._warnings[-1]  # the patch is the class's
    assert w.save_method(tmp_path / "x.toml", "MOBCAL 2012 (He)") is None
    assert "is the name of a shipped method" in w._warnings[-1]


def test_a_method_file_with_its_own_table_fills_the_table(window, tmp_path):
    w = window
    table = tmp_path / "mine_he.toml"
    table.write_bytes(win.parameters.default_path("he").read_bytes().replace(
        b'name = "MOBCAL 2012 helium"', b'name = "my helium"'))
    f = tmp_path / "own.toml"
    methods.save(f, "Own table", "he", table, "philox", win.settings.DEFAULTS)
    m = w.load_method(f)
    assert m is not None and w.table_value() == str(table.resolve())
    assert w.table_combo.currentText() == "mine_he.toml"
    assert w.method_combo.currentText() == "Own table"
    w.gas_combo.setCurrentIndex(w.gas_combo.findData("n2"))
    assert w.table_value() == "2012"  # a helium table does not follow the gas to nitrogen
    assert w.method_combo.currentText() == "MOBCAL 2012 with Philox (N2)"


def test_a_remembered_method_file_gone_or_changed_is_dropped_with_a_message(
        window, qtbot, tmp_path, monkeypatch):
    w = window
    kept, changed, gone = (tmp_path / f"{n}.toml" for n in ("kept", "changed", "gone"))
    for f, name in ((kept, "Kept"), (changed, "Changed"), (gone, "Gone")):
        w.load_method(methods.save(f, name, "he", "2012", "ranlux", win.settings.DEFAULTS).path)
    assert len(w.store.methods) == 3
    changed.write_text(changed.read_text(encoding="utf-8").replace("itn = 10", "itn = 9"),
                       encoding="utf-8")
    gone.unlink()
    w2 = MainWindow(w.store, launcher=launcher, cpus=8)
    qtbot.addWidget(w2)
    assert combo_items(w2.method_combo)[5:] == ["Kept"]
    assert [ref for ref, _ in w2.store.methods] == [str(kept.resolve())]
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda _, title, text: shown.append(text))
    w2.report_dropped_methods()
    assert len(shown) == 1 and shown[0].startswith("2 method files were removed")
    assert "changed.toml: the file has changed since it was added" in shown[0]
    assert "gone.toml: the file is no longer there." in shown[0]
    assert w2.method_combo.currentText() == "MOBCAL 2012 with Philox (He)"  # Gone was picked
    w2.report_dropped_methods()
    assert len(shown) == 1


def test_the_estimate_and_add_batch(window, qtbot):
    w = window
    assert not w.add_batch_button.isEnabled() and "add an input" in w.estimate_label.text()
    add(qtbot, w, CHOLINE)
    assert w.add_batch_button.isEnabled()
    assert w.estimate_label.text().startswith("MOBCAL 2012 with Philox (He): 1 run on 1 "
                                              "worker, each across 8 processes (balanced); "
                                              "about")
    w.counts["itn"].setValue(100)
    w.counts["inp"].setValue(100)  # 100 * 100 * 1000 points: over the program's 9,999,999
    assert not w.add_batch_button.isEnabled() and "points per coordinate set" in \
        w.estimate_label.text()


# --- running ---------------------------------------------------------------------------

def test_the_mode_is_a_preference_the_estimate_follows(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, CHOLINE)
    w.seeds_spin.setValue(4)
    assert w.mode == w.store.mode == estimate.BALANCED
    w.mode_combo.setCurrentIndex(estimate.MODES.index(estimate.IN_ORDER))
    assert w.store.mode == estimate.IN_ORDER and "(finish in order)" in w.estimate_label.text()
    assert Store(w.store._s).mode == estimate.IN_ORDER  # kept for the next launch
    w.auto_cores.setChecked(False)
    assert not w.mode_combo.isEnabled() and "(finish in order)" not in w.estimate_label.text()
    w.auto_cores.setChecked(True)
    assert w.mode_combo.isEnabled()
    assert w.workers_spin.maximum() >= w.cpus  # up to the logical processors


def test_a_batch_runs_and_fills_the_results(window, qtbot, tmp_path):
    w = window
    a = write_input(tmp_path / "a.mfj", "ok")
    bad = write_input(tmp_path / "bad.mfj", "refuse")
    add(qtbot, w, a, bad)
    w.seeds_spin.setValue(3)
    run(w)
    wait_idle(qtbot, w)
    rows = w.result_rows()
    assert [(r.input.stem, r.gas) for r in rows] == [("a", "he"), ("bad", "he")]
    tm = [50 + s % 7 + 0.5 for s in (5013489, 5013490, 5013491)]
    assert rows[0].value("TM") == methods.summary_line(tm)
    assert rows[0].status == "ok (3 seeds)" and rows[1].status == "failed 3 of 3"
    assert w.results_table.item(0, 2).text() == methods.summary_line(tm)
    assert w.results_table.item(0, 3).text() != ""
    assert w.methods_button.isEnabled()
    w.copy_methods_text()
    text = QGuiApplication.clipboard().text()
    assert text.startswith("Collision cross sections were calculated by the trajectory method")
    assert "at 3 seeds per structure" in text
    # Nitrogen is another batch, under its own method, into the same folder.
    w.apply_method("2012-philox-n2")
    w.seeds_spin.setValue(1)
    run(w)
    wait_idle(qtbot, w)
    assert [(r.input.stem, r.gas) for r in w.result_rows()] == [("a", "n2"), ("bad", "n2")]
    assert w.results_table.item(0, 3).text() == ""  # no PA in nitrogen
    summary = json.loads((tmp_path / "results" / "summary.json").read_text(encoding="utf-8"))
    assert len(summary["runs"]) == 8
    assert {r["method"] for r in summary["runs"]} == {"2012-philox-he", "2012-philox-n2"}
    w.copy_methods_text()
    assert "in nitrogen with MOBCAL" in QGuiApplication.clipboard().text()  # this batch's runs
    w.copy_results()
    assert QGuiApplication.clipboard().text().splitlines()[0].startswith("ion\tinput\tgas\tTM")


def serial(w: MainWindow, seeds: int) -> None:
    """One run at a time, one process each, so a pause finds one run in flight and the rest
    not started."""
    w.auto_cores.setChecked(False)
    w.workers_spin.setValue(1)
    w.split_spin.setValue(1)
    w.seeds_spin.setValue(seeds)


def labels(b: batches.Batch, *seeds: int) -> tuple[str, ...]:
    return tuple(j.label for j in b.jobs() if j.seed in seeds)


def test_add_batch_only_queues_and_the_queue_survives(window, qtbot, tmp_path):
    w = window
    t = w.toggle_button
    assert t.text() == "Start queue" and not t.isEnabled()  # the queue is empty
    assert w.queue_total.text() == "Nothing queued."
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 60"))
    w.add_batch_clicked()  # nothing running, and still it only queues
    assert w.worker is None and len(w.queued()) == 1 and w.state == win.IDLE
    assert t.text() == "Start queue" and t.isEnabled()
    assert t.toolTip() == tip(options.tooltip("start_queue"))
    assert "; about " in w.queue.item(0).text() and w.queue_total.text().startswith("In all")
    t.click()
    assert w.worker is not None and w.state == win.RUNNING and not w.queued()
    assert w.queue.item(0).text().startswith("Running: MOBCAL 2012 with Philox (He)")
    assert t.text() == "Pause queue" and t.toolTip() == tip(options.tooltip("pause_queue"))
    w.seeds_spin.setValue(2)
    w.add_batch_clicked()
    w.apply_method("2012-n2")
    w.add_batch_clicked()
    assert w.queue.count() == 3 and len(w.queued()) == 2
    assert w.queue.item(2).text().startswith("MOBCAL 2012 (N2): 1 input, N2, 2 seeds")
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    saved, problems = batches.load(w.store.queue_path)
    assert [b.title() for b in saved] == ["MOBCAL 2012 with Philox (He)",
                                          "MOBCAL 2012 with Philox (He)",
                                          "MOBCAL 2012 (N2)"] and not problems
    assert saved[0].remaining == labels(saved[0], 5013489) and saved[1].remaining is None
    assert saved[1].seeds == (5013489, 5013490)
    # The second launch offers them back, paused.
    w2 = MainWindow(w.store, launcher=launcher, cpus=8)
    qtbot.addWidget(w2)
    assert w2.toggle_button.text() == "Start queue" and not w2.toggle_button.isEnabled()
    w2.offer_saved_queue()
    assert w2.state == win.PAUSED and w2.current == saved[0] and w2.queued() == saved[1:]
    assert w2.toggle_button.text() == "Resume queue" and w2.toggle_button.isEnabled()
    assert w2.queue.item(0).text().startswith("Paused: ")
    w.queue.selectAll()
    w.remove_clicked()  # answered yes: the running batch stops and the waiting ones go
    wait_idle(qtbot, w)
    assert batches.load(w.store.queue_path) == ([], [])


def test_pause_drains_and_resume_runs_exactly_the_runs_left(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 2"))
    serial(w, 3)
    w.add_batch_clicked()
    b = w.queued()[0]
    w.toggle_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w.toggle_clicked()  # Pause queue: the run in flight finishes, the other two never start
    assert w.state == win.PAUSING
    assert w.toggle_button.text() == "Pausing…" and not w.toggle_button.isEnabled()
    assert "pausing, waiting for 1 run in flight" in w.status_label.text()
    assert w.queue.item(0).text().startswith("Pausing: ")
    qtbot.waitUntil(lambda: w.state == win.PAUSED, timeout=30_000)
    assert w.current.remaining == labels(b, 5013490, 5013491)
    assert [r.status for r in w.results] == ["ok"]
    assert not any(j.run_dir.exists() for j in w.current.to_run())
    assert w.toggle_button.text() == "Resume queue" and w.toggle_button.isEnabled()
    assert "2 runs left" in w.queue.item(0).text() and "paused, 2 runs left" in \
        w.status_label.text()
    assert batches.load(w.store.queue_path)[0][0].remaining == w.current.remaining
    w.toggle_clicked()  # Resume queue
    qtbot.waitUntil(lambda: w.plan is not None, timeout=20_000)
    assert [j.seed for j in w.plan.jobs] == [5013490, 5013491]
    wait_idle(qtbot, w)
    assert all((j.run_dir / "record.json").is_file() for j in b.jobs())
    assert w.toggle_button.text() == "Start queue" and not w.toggle_button.isEnabled()


def test_a_drained_batch_does_not_move_the_queue_on(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 2"))
    serial(w, 1)  # its one run is in flight when Pause comes: nothing is left to pause
    w.add_batch_clicked()
    w.seeds_spin.setValue(2)
    w.add_batch_clicked()
    w.toggle_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w.toggle_clicked()
    qtbot.waitUntil(lambda: w.worker is None, timeout=30_000)
    assert w.state == win.IDLE and w.current is None and len(w.queued()) == 1
    assert w.toggle_button.text() == "Start queue" and w.toggle_button.isEnabled()
    w.queue.selectAll()
    w.remove_clicked()
    assert w.queue.count() == 0 and not w.toggle_button.isEnabled()


def test_remove_batch_on_the_running_row_asks_then_stops_and_leaves_the_queue_paused(
        window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 60"))
    w.add_batch_clicked()
    w.add_batch_clicked()
    w.toggle_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w.queue.item(0).setSelected(True)
    w._answers.append(QMessageBox.StandardButton.No)
    w.remove_clicked()
    assert w.state == win.RUNNING and not w.worker.stopping
    w.queue.item(0).setSelected(True)
    w.remove_clicked()  # answered yes
    qtbot.waitUntil(lambda: w.worker is None, timeout=30_000)
    assert w.result_rows()[0].status == "stopped"
    assert w.state == win.IDLE and len(w.queued()) == 1 and w.queue.count() == 1
    assert w.toggle_button.text() == "Start queue" and w.toggle_button.isEnabled()
    w.queue.item(0).setSelected(True)
    w.remove_clicked()  # a waiting row goes without a question
    assert w.queue.count() == 0 and not w.toggle_button.isEnabled()


def test_removing_a_paused_batch_asks_only_when_runs_are_complete(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 2"))
    serial(w, 2)
    w.add_batch_clicked()
    w.toggle_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w.toggle_clicked()
    qtbot.waitUntil(lambda: w.state == win.PAUSED, timeout=30_000)
    w.queue.item(0).setSelected(True)
    w._answers.append(QMessageBox.StandardButton.No)
    w.remove_clicked()
    assert w.state == win.PAUSED
    w.queue.item(0).setSelected(True)
    w.remove_clicked()  # answered yes
    assert w.state == win.IDLE and w.queue.count() == 0
    # A paused batch with nothing complete, as a queue put back at launch, goes unasked.
    w._pin(w.form_batch())
    w.queue.item(0).setSelected(True)
    w._answers.append(QMessageBox.StandardButton.No)  # never asked, so never read
    w.remove_clicked()
    assert w.queue.count() == 0 and w._answers


def test_the_running_row_is_pinned_and_waiting_rows_reorder(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 60"))
    w.add_batch_clicked()
    w.toggle_clicked()
    w.seeds_spin.setValue(2)
    w.add_batch_clicked()
    w.seeds_spin.setValue(3)
    w.add_batch_clicked()
    top = w.queue.item(0)
    assert top.data(win.PINNED) and top.font().bold()
    assert not top.flags() & Qt.ItemFlag.ItemIsDragEnabled
    assert w.queue.item(1).flags() & Qt.ItemFlag.ItemIsDragEnabled
    m = w.queue.model()
    assert m.moveRow(QModelIndex(), 2, QModelIndex(), 1)  # a waiting row moves up
    assert [len(b.seeds) for b in w.queued()] == [3, 2]
    assert m.moveRow(QModelIndex(), 2, QModelIndex(), 0)  # dropped above the running row
    qtbot.waitUntil(lambda: w.queue.item(0).data(win.PINNED), timeout=5_000)
    assert [len(b.seeds) for b in w.queued()] == [2, 3]
    assert [len(b.seeds) for b in batches.load(w.store.queue_path)[0]] == [1, 2, 3]
    w.queue.selectAll()
    w.remove_clicked()
    wait_idle(qtbot, w)


def test_closing_while_running_keeps_the_batch_with_its_runs_not_complete(
        window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 60"))
    serial(w, 3)
    w.add_batch_clicked()
    b = w.queued()[0]
    w.add_batch_clicked()  # waiting
    w.toggle_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w._answers.append(QMessageBox.StandardButton.No)
    assert not w.close() and w.worker is not None
    worker = w.worker
    assert w.close()
    assert worker.isFinished() and worker.stopping
    saved, _ = batches.load(w.store.queue_path)
    # The one killed and the two never started, then the waiting batch.
    assert saved == [dataclasses.replace(b, remaining=labels(b, 5013489, 5013490, 5013491)), b]
    w2 = MainWindow(w.store, launcher=launcher, cpus=8)
    qtbot.addWidget(w2)
    w2.offer_saved_queue()
    assert w2.state == win.PAUSED and w2.current == saved[0] and w2.queued() == [b]
    assert w2.toggle_button.text() == "Resume queue"


def test_a_paused_batch_survives_closing_and_comes_back_paused(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 2"))
    serial(w, 3)
    w.add_batch_clicked()
    w.toggle_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w.toggle_clicked()
    qtbot.waitUntil(lambda: w.state == win.PAUSED, timeout=30_000)
    left = w.current.remaining
    assert w.close()  # nothing running: no question
    w2 = MainWindow(w.store, launcher=launcher, cpus=8)
    qtbot.addWidget(w2)
    w2.offer_saved_queue()
    assert w2.state == win.PAUSED and w2.current.remaining == left and len(left) == 2
    assert "2 runs left" in w2.queue.item(0).text()


def test_run_them_again_then_pause_keeps_the_runs_it_never_reached(
        window, qtbot, tmp_path, monkeypatch):
    w = window
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 1"))
    serial(w, 3)
    run(w)
    wait_idle(qtbot, w)
    monkeypatch.setattr(QMessageBox, "exec", lambda box: setattr(box, "_clicked", next(
        b for b in box.buttons() if b.text() == "Run them again")))
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    w.add_batch_clicked()
    b = w.queued()[0]
    assert not b.skip_done
    w.toggle_clicked()
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w.toggle_clicked()
    qtbot.waitUntil(lambda: w.state == win.PAUSED, timeout=30_000)
    # Seeds 2 and 3 are complete in the folder, from the first batch, and still left to run.
    left = w.current.to_run()
    assert [j.seed for j in left] == [5013490, 5013491]
    assert {p.kind for p in batches.prior(left)} == {batches.DONE}
    w.toggle_clicked()
    qtbot.waitUntil(lambda: w.plan is not None, timeout=20_000)
    assert [j.seed for j in w.plan.jobs] == [5013490, 5013491]
    wait_idle(qtbot, w)


# --- the menus and the colours -------------------------------------------------------------

def test_the_menus_are_file_and_help_and_no_queue_control_has_a_shortcut(window):
    w = window
    menus = {m.text(): [a for a in m.menu().actions() if not a.isSeparator()]
             for m in w.menuBar().actions()}
    assert list(menus) == ["&File", "&Help"]
    assert menus["&File"] == [w.load_method_action, w.save_method_action, w.exit_action]
    assert [a.toolTip() for a in menus["&File"][:2]] == [options.tooltip("load_method"),
                                                         options.tooltip("save_method")]
    assert menus["&Help"] == [w.help_action, w.about_action]
    assert w.help_action.shortcuts() == QKeySequence.keyBindings(
        QKeySequence.StandardKey.HelpContents)
    roles = [a.menuRole() for a in (w.exit_action, w.about_action)]
    assert roles == [QAction.MenuRole.QuitRole, QAction.MenuRole.AboutRole]
    assert not w.findChildren(QToolBar)
    keys = {s.toString() for a in w.findChildren(QAction) for s in a.shortcuts()}
    assert not keys & {"Ctrl+R", "F5", "Shift+F5"}
    for b in (w.add_batch_button, w.toggle_button, w.remove_button):
        assert b.shortcut().isEmpty()


def test_exit_while_running_asks_and_no_keeps_the_window(window, qtbot, tmp_path):
    w = window
    w.show()
    add(qtbot, w, write_input(tmp_path / "slow.mfj", "sleep 60"))
    run(w)
    qtbot.waitUntil(lambda: bool(w.running), timeout=20_000)
    w._answers.append(QMessageBox.StandardButton.No)
    w.exit_action.trigger()
    assert w.isVisible() and w.worker is not None and not w.worker.stopping
    w.exit_action.trigger()  # answered yes: stops the batch and closes
    assert not w.isVisible()


def test_about_opens_and_closes(window):
    w = window
    d = w.show_about()
    assert d.isVisible() and d.windowTitle() == "About MOBCAL"
    text = d.body.text()
    assert f"MOBCAL {mobcal.__version__}" in text and methods.REPOSITORY in text
    assert "CHE-2603156" in text and "68949-ND6" in text
    assert html.escape(methods.REFERENCES["campuzano2012"]) in text
    assert "GNU General Public License, version 3" in text and "PySide6 6." in text
    assert d.body.height() >= d.body.heightForWidth(d.body.width())  # nothing cut off
    d.close()
    assert not d.isVisible()


# --- the help viewer -----------------------------------------------------------------------

def test_help_opens_one_viewer_and_a_second_call_raises_it(window, qtbot):
    w = window
    w.show()
    assert w.help is None
    w.help_action.trigger()
    h = w.help
    assert h is not None and h.isVisible() and not h.isModal()
    assert h.current == "window.md" and h.windowTitle() == "The window - MOBCAL Help"
    h.open("settings.md")
    h.close()
    w.help_action.trigger()
    assert w.help is h and h.isVisible() and h.current == "settings.md"
    assert len([c for c in w.findChildren(type(h))]) == 1


def test_every_page_loads_with_githubs_anchors_on_its_headings(window):
    h = window.show_help()
    pages = docs.pages()
    assert list(h.pages) == [p.name for p in pages]
    for p in pages:
        loaded = h.pages[p.name]
        assert loaded.doc.toPlainText().startswith(p.title)
        want = [(lvl, a) for lvl, _, a in docs.anchors(p.path.read_text(encoding="utf-8"))]
        assert [(lvl, a) for _, lvl, _, a in loaded.sections] == want, p.name
    top = [h.contents.topLevelItem(i).text(0) for i in range(h.contents.topLevelItemCount())]
    assert top == [p.title for p in pages]


def test_a_link_to_a_section_of_another_page_is_followed(window, qtbot):
    h = window.show_help()
    h.resize(900, 500)
    qtbot.waitExposed(h)
    h.follow(QUrl("parameters.md#the-2000-helium-set"))
    assert h.current == "parameters.md"
    assert h.view.verticalScrollBar().value() > 0
    assert h.contents.currentItem().text(0) == "The 2000 helium set"
    h.follow(QUrl("#the-file"))
    assert h.current == "parameters.md" and h.contents.currentItem().text(0) == "The file"


def test_a_link_outside_the_guide_opens_on_github_at_the_version(window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    h = window.show_help()
    h.open("mobcal-2012.md")
    h.follow(QUrl("../fortran/README.md"))
    h.follow(QUrl("https://github.com/bushgroup/MOBCAL-2012"))
    h.follow(QUrl("later.md#orca"))  # a page this copy does not carry
    blob = f"{methods.REPOSITORY}/blob/{docs.ref()}"
    assert opened == [f"{blob}/fortran/README.md", "https://github.com/bushgroup/MOBCAL-2012",
                      f"{blob}/docs/later.md#orca"]
    assert h.current == "mobcal-2012.md"


def test_a_search_finds_a_term_on_every_page_that_holds_it(window, qtbot):
    h = window.show_help()
    h.search.setText("Philox4x32-10")
    h.find()
    assert h.lists.currentWidget() is h.results
    found = {h.results.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
             for i in range(h.results.topLevelItemCount())}
    holds = {p.name for p in docs.pages()
             if "philox4x32-10" in p.path.read_text(encoding="utf-8").lower()}
    assert found == holds and "random-numbers.md" in found
    page = next(h.results.topLevelItem(i) for i in range(h.results.topLevelItemCount())
                if h.results.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
                == "random-numbers.md")
    section = page.child(0)
    assert section.text(0) in {s for *_, s, _ in [(0, 0, t, a) for _, _, t, a in
                                                  h.pages["random-numbers.md"].sections]}
    h._go(section.child(0))
    assert h.current == "random-numbers.md"
    assert h.view.textCursor().selectedText().lower() == "philox4x32-10"
    h.search.setText("no such words anywhere")
    h.find()
    assert h.results.topLevelItem(0).text(0).startswith("No page holds")
    h.search.clear()
    h.find()
    assert h.lists.currentWidget() is h.contents


def test_the_help_reads_its_pages_again_when_the_palette_changes(window, qtbot):
    h = window.show_help()
    h.open("settings.md")
    before = h.pages["settings.md"].doc
    pal = QPalette(h.palette())
    pal.setColor(QPalette.ColorRole.Base, QColor("#202020"))
    h.setPalette(pal)
    assert h.pages["settings.md"].doc is not before and h.current == "settings.md"
    assert h.view.document() is h.pages["settings.md"].doc

def contrast(a: str, b: str) -> float:
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# The window and base colours of Qt's windows11 style (Qt 6.11, Windows 11), light and dark, and
# of Fusion (Linux), against which each colour of the scheme does its job.
BACKGROUNDS = {False: ("#F3F3F3", "#FFFFFF", "#EFEFEF"), True: ("#1E1E1E", "#2D2D2D", "#323232")}


@pytest.mark.parametrize("dark", [False, True])
def test_the_schemes_colours_meet_their_contrast(dark):
    s = theme.DARK_SCHEME if dark else theme.LIGHT_SCHEME
    for bg in BACKGROUNDS[dark]:
        assert contrast(s.text, bg) >= 4.5, (s.text, bg)  # text: WCAG 1.4.3
        assert contrast(s.accent, bg) >= 3.0, (s.accent, bg)  # fills: WCAG 1.4.11
    assert contrast(s.highlighted_text, s.accent) >= 4.5  # a checked button's text


def test_the_theme_follows_the_colour_scheme(qtbot, monkeypatch):
    """Through the signal, with the scheme patched: the offscreen platform takes no scheme."""
    app = QApplication.instance()
    hints = QGuiApplication.styleHints()
    style, palette = app.style().name(), app.palette()
    dark = [False]
    monkeypatch.setattr(theme, "is_dark", lambda: dark[0])
    try:
        theme.install(app)
        for dark[0], s in ((True, theme.DARK_SCHEME), (False, theme.LIGHT_SCHEME)):
            hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark if dark[0]
                                          else Qt.ColorScheme.Light)
            for role in (QPalette.ColorRole.Accent, QPalette.ColorRole.Highlight):
                assert app.palette().color(role).name() == s.accent.lower()
            assert app.palette().color(QPalette.ColorRole.Link).name() == s.text.lower()
            hint = app.style().styleHint(QStyle.StyleHint.SH_GroupBox_TextLabelColor)
            assert QColor.fromRgba(hint & 0xFFFFFFFF).name() == s.text.lower()
    finally:
        app.setStyle(style)
        app.setPalette(palette)


@pytest.mark.parametrize("dark", [False, True])
def test_group_titles_take_the_text_colour_and_nothing_inside_does(qtbot, monkeypatch, dark):
    """Under Fusion, which takes the title from the box's WindowText as macOS does."""
    monkeypatch.setattr(theme, "is_dark", lambda: dark)
    s = theme.DARK_SCHEME if dark else theme.LIGHT_SCHEME
    style = theme.Style("fusion")
    box = QGroupBox("MMMMMM")
    label = QLabel("MMMMMM", box)
    QVBoxLayout(box).addWidget(label)
    for w in (box, label):
        w.setStyle(style)
        w.setFont(QFont(w.font().family(), 28, QFont.Weight.Bold))
    qtbot.addWidget(box)
    box.resize(400, 200)
    box.layout().activate()
    want = QColor(s.text)

    def near(widget, rect=None) -> int:
        img = widget.grab(rect or QRect()).toImage()
        return sum(1 for x in range(img.width()) for y in range(img.height())
                   if max(abs(img.pixelColor(x, y).red() - want.red()),
                          abs(img.pixelColor(x, y).green() - want.green()),
                          abs(img.pixelColor(x, y).blue() - want.blue())) < 24)
    # The label grabbed alone: a large title's glyphs can reach into the label's rectangle.
    assert near(box, QRect(0, 0, 400, label.geometry().top())) > 50 and near(label) == 0


def test_a_run_the_folder_holds_is_skipped_or_run_again(window, qtbot, tmp_path, monkeypatch):
    w = window
    add(qtbot, w, write_input(tmp_path / "a.mfj", "ok"))
    run(w)
    wait_idle(qtbot, w)
    clicked = []

    def exec_(box):
        buttons = {b.text(): b for b in box.buttons()}
        box._clicked = buttons[clicked[0]]
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    clicked[:] = ["Skip them"]
    run(w)
    wait_idle(qtbot, w)
    assert "did not run: nothing to run" in w.status_label.text()
    clicked[:] = ["Run them again"]
    run(w)
    wait_idle(qtbot, w)
    assert w.result_rows()[0].status == "ok"


def test_another_input_of_the_same_name_is_refused(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, write_input(tmp_path / "a.mfj", "ok"))
    run(w)
    wait_idle(qtbot, w)
    other = tmp_path / "other"
    other.mkdir()
    w.inputs.clear()
    add(qtbot, w, write_input(other / "a.mfj", "sets 2"))
    run(w)
    assert w.worker is None and "another input of the same name" in w._warnings[-1]


# --- imports ------------------------------------------------------------------------------

def test_an_orca_output_with_chelpg_is_preselected_and_imported_at_run(window, qtbot):
    w = window
    add(qtbot, w, ORCA / "choline_sp" / "choline_sp.out", ORCA / "choline_opt" / "choline_opt.out")
    sp, opt = w.inputs.items
    assert sp.charges == "chelpg" and sp.atoms == 21 and not sp.problem()
    assert opt.charges is None and opt.problem().endswith("choose its charges")
    assert not w.add_batch_button.isEnabled()
    combo = w.inputs.table.cellWidget(1, 3)
    assert combo.itemData(combo.count() - 1) == "uniform"
    combo.setCurrentIndex(combo.findData("mulliken"))
    assert w.add_batch_button.isEnabled()
    b = w.form_batch()
    assert [p.name for p in b.inputs] == ["choline_sp_chelpg.mfj", "choline_opt_mulliken.mfj"]
    w.launcher = launcher
    for item in w.inputs.items:
        item.write(w.out_dir, (w.gas,))
    rec = json.loads((w.out_dir / "imported" / "choline_sp_chelpg.import.json").read_text(
        encoding="utf-8"))
    assert rec["charges"]["choice"] == "chelpg"


def test_a_gaussian_log_preselects_mk_then_chelpg_and_shows_an_untested_version(window, qtbot,
                                                                                tmp_path):
    w = window
    g16 = ORCA.parent / "gaussian"
    log = g16 / "choline_2012_mk" / "choline_2012_mk.log"
    g09 = tmp_path / "g09.log"
    g09.write_text(log.read_text(encoding="ascii").replace("ES64L-G16RevB.01", "ES64L-G09RevD.01"),
                   encoding="ascii", newline="\n")
    add(qtbot, w, log, g16 / "choline_optfreq" / "choline_optfreq.log", g09)
    mk, optfreq, old = w.inputs.items
    assert (mk.charges, optfreq.charges, old.charges) == ("mk", "chelpg", "mk")
    assert w.inputs.table.item(0, 5).text() == "ready"
    assert w.inputs.table.item(2, 5).text() == "ready (untested version)"
    assert "tested on Gaussian 16" in w.inputs.table.item(2, 5).toolTip()


def test_an_xyz_asks_for_its_net_charge(window, qtbot):
    w = window
    add(qtbot, w, ORCA / "choline_opt" / "choline_opt.xyz")
    item = w.inputs.items[0]
    assert item.needs_net_charge and item.charges is None
    combo = w.inputs.table.cellWidget(0, 3)
    combo.setCurrentIndex(combo.findData("uniform"))
    assert item.problem().endswith("give the ion's net charge")
    w.inputs.table.cellWidget(0, 4).setValue(1)
    assert not item.problem() and w.add_batch_button.isEnabled()


def mfj_file(tmp_path: Path, name: str, mode: str, charges: list[list[float] | None]) -> Path:
    """A synthetic ``.mfj``: one set per entry of ``charges``, each a charge per atom or None
    for a four-column file."""
    sets = tuple(tuple(Atom(float(i), 0.0, 0.0, 1, None if c is None else c[i])
                       for i in range(len(c or [0, 0]))) for c in charges)
    return Mfj("test", "ang", mode, 1.0, sets).write(tmp_path / name)


@pytest.mark.parametrize(("q", "shown"), [
    (1.0, "+1"), (-2.0, "−2"), (0.0, "0"), (-0.004, "0"), (0.873, "+0.873"),
    (-0.873, "−0.873"), (1.009, "+1"), (1.011, "+1.011"), (0.991, "+1"), (0.989, "+0.989"),
])
def test_a_net_charge_is_an_integer_within_a_hundredth_of_one(q, shown):
    assert inputs.format_charge(q) == shown


def test_the_mfj_cells_follow_line_five():
    assert inputs.mfj_charge_cells("calc", (1.0,))[::2] == ("from file", "+1")
    assert inputs.mfj_charge_cells("equal", (2.0,))[::2] == ("uniform", "+1 He / +2 N2")
    assert inputs.mfj_charge_cells("equal", ())[::2] == ("uniform", "+1 He / — N2")
    assert inputs.mfj_charge_cells("none", (3.0,))[::2] == ("none", "0")
    assert inputs.mfj_charge_cells("none", ())[::2] == ("none", "0")
    assert "1.234568" in inputs.mfj_charge_cells("calc", (1.2345678,))[3]
    assert "by set" not in inputs.mfj_charge_cells("calc", (1.0, 1.005))[3]
    assert "by set: 1.000000, 2.000000" in inputs.mfj_charge_cells("calc", (1.0, 2.0))[3]
    assert "−2.000000" in inputs.mfj_charge_cells("calc", (-2.0,))[3]


def cells(w: MainWindow, row: int) -> tuple[str, str]:
    return w.inputs.table.item(row, 3).text(), w.inputs.table.item(row, 4).text()


def test_an_mfj_row_shows_its_charges_and_net_charge(window, qtbot, tmp_path):
    w = window
    add(qtbot, w, CHOLINE)
    assert cells(w, 0) == ("from file", "+1")
    assert w.inputs.table.item(0, 5).text() == "ready"
    two = mfj_file(tmp_path, "two.mfj", "equal", [[1.0, 1.0, 0.0]])
    four = mfj_file(tmp_path, "four.mfj", "equal", [None])
    none = mfj_file(tmp_path, "none.mfj", "none", [[1.0, 1.0, 1.0]])
    add(qtbot, w, two, four, none)
    assert [cells(w, r) for r in (1, 2, 3)] == [
        ("uniform", "+1 He / +2 N2"), ("uniform", "+1 He / — N2"), ("none", "0")]
    assert "equal" in w.inputs.table.item(1, 3).toolTip()


def test_a_two_set_file_lists_its_sums_when_they_differ(window, qtbot, tmp_path):
    w = window
    same = mfj_file(tmp_path, "same.mfj", "calc", [[1.0, 0.0], [0.0, 1.0]])
    differ = mfj_file(tmp_path, "differ.mfj", "calc", [[1.0, 0.0], [1.0, 1.0]])
    add(qtbot, w, same, differ)
    assert "by set" not in w.inputs.table.item(0, 4).toolTip()
    assert "by set: 1.000000, 2.000000" in w.inputs.table.item(1, 4).toolTip()
    assert w.inputs.table.item(1, 4).text() == "+1"
    assert w.inputs.table.item(1, 5).text() == "ready"


def test_a_four_column_file_blocks_nitrogen_and_not_helium(window, qtbot, tmp_path):
    w = window
    four = mfj_file(tmp_path, "four.mfj", "equal", [None])
    add(qtbot, w, four)
    assert w.gas == "he" and w.add_batch_button.isEnabled()
    w.gas_combo.setCurrentIndex(w.gas_combo.findData("n2"))
    assert not w.add_batch_button.isEnabled()
    assert "fifth column" in w.inputs.table.item(0, 5).text()
    assert "fifth column" in w.estimate_label.text()
    w.gas_combo.setCurrentIndex(w.gas_combo.findData("he"))
    assert w.add_batch_button.isEnabled() and w.inputs.table.item(0, 5).text() == "ready"


def test_an_unreadable_input_says_why(window, qtbot, tmp_path):
    w = window
    junk = tmp_path / "junk.mfj"
    junk.write_text("not a structure\n", encoding="ascii")
    add(qtbot, w, junk)
    assert w.inputs.items[0].state == "error" and not w.add_batch_button.isEnabled()


# --- the tooltips -------------------------------------------------------------------------

def controls(w: MainWindow) -> list:
    """Every widget a user sets or presses, found by walking the window, without Qt's own
    parts of them: a spin box's line edit, a table's header view and corner button, the menu
    bar's overflow button, a combo box's list, which is a window of its own."""
    kinds = (QAbstractButton, QAbstractSpinBox, QComboBox, QLineEdit, QAbstractItemView,
             QProgressBar)
    inner = (QAbstractSpinBox, QAbstractItemView, QMenuBar)
    return [x for x in w.findChildren(QWidget)
            if isinstance(x, kinds) and not isinstance(x, QHeaderView) and x.window() is w
            and not isinstance(x.parentWidget(), inner)]


def test_every_control_and_column_has_a_tooltip(window, qtbot):
    w = window
    add(qtbot, w, CHOLINE, ORCA / "choline_sp" / "choline_sp.out",
        ORCA / "choline_opt" / "choline_opt.xyz")
    found = controls(w)
    assert len(found) >= 30
    bare = [f"{type(x).__name__} {getattr(x, 'text', lambda: '')()!r}" for x in found
            if not x.toolTip()]
    assert not bare
    for table in (w.inputs.table, w.results_table):
        for c in range(table.columnCount()):
            assert table.horizontalHeaderItem(c).toolTip(), table.horizontalHeaderItem(c).text()


def test_the_tooltips_are_the_command_lines_descriptions(window):
    """A control the command line also sets carries the option's shared text, and the window's
    own addition; nothing in the window restates or rewords it."""
    w = window
    by_key = {"method": w.method_combo, "parameters": w.table_combo,
              "seeds": w.seeds_spin, "temperature": w.temperature, "rng": w.generator_combo,
              "workers": w.workers_spin, "split": w.split_spin, "out": w.out_edit,
              "mode": w.mode_combo,
              "methods_text": w.methods_button, "inputs": w.inputs.table,
              **{name: spin for name, spin in w.counts.items()}}
    for key, widget in by_key.items():
        assert widget.toolTip() == tip(options.tooltip(key)), key
        assert widget.toolTip().startswith(tip(options.SHARED[key].text).removesuffix("</qt>"))
    assert options.AUTO_RULE in html.unescape(w.auto_cores.toolTip())


def test_a_tooltip_wraps_and_says_what_it_is_given():
    assert tip("Å² & <b>") == "<qt>Å² &amp; &lt;b&gt;</qt>"
    assert QtGui_Qt.mightBeRichText(tip(options.tooltip("method")))


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


def test_the_window_has_its_icon_at_every_size(qtbot):
    import mobcal.app as app
    sizes = sorted(s.width() for s in app.window_icon().availableSizes())
    assert sizes == [16, 24, 32, 48, 64, 128, 256, 512]


def test_the_packages_icons_hold_every_size():
    icon = Path(__file__).resolve().parent.parent / "packaging" / "icon"
    ico = (icon / "mobcal.ico").read_bytes()
    assert ico[:4] == b"\0\0\1\0" and int.from_bytes(ico[4:6], "little") == 7
    icns = (icon / "mobcal.icns").read_bytes()
    assert icns[:4] == b"icns" and int.from_bytes(icns[4:8], "big") == len(icns)
    kinds, i = [], 8
    while i < len(icns):
        kinds.append(icns[i:i + 4].decode())
        i += int.from_bytes(icns[i + 4:i + 8], "big")
    assert kinds == ["icp4", "icp5", "ic11", "ic12", "ic07", "ic13", "ic08", "ic14", "ic09",
                     "ic10"]


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
