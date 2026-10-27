"""The main window: the form, the queue, the progress and the results.

Left, the form makes a ``mobcal.batch.Batch``: the inputs, a Method that fills every field
(Current, MOBCAL 2012, MOBCAL 2000), Basics (gas, element table, seeds, temperature), an
Advanced fold (generator, the five sampling counts, how the batch uses the cores), and the
results folder, one per study, remembered. The method shown is the one the fields make, or
*Custom (from …)* once a field moves off the method picked; the runs' records say the same.
Under the form, the estimate for the batch as it stands.

Above, a menu bar: File ▸ Exit, Batch ▸ Run and Stop (each one ``QAction`` that owns its text
and enabled state), Help ▸ About. Right, the queue, the progress and the results. Run starts
the batch, or appends it to the queue while one is running; the queue is reorderable, starts
its next batch when the running one ends, and is saved on every change and offered back at the
next launch. Stop asks, then ends every process of the running batch. Progress is runs done
of N, each running run's elapsed time (and blocks written, for a split run), against the
estimate. Results are one row per ion and gas, TM headline, mean ± s.d. over seeds, with Copy,
Save CSV, Show in folder, Open output and Copy methods text. Closing asks, then stops the
running batch; the queue stays saved.

Every control and column header has a tooltip from ``mobcal.options``; a control that an
option of ``mobcal run`` also sets shows that option's description, so the two cannot drift.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import mobcal
from mobcal import batch as batches
from mobcal import estimate, methods, options, parameters, settings
from mobcal.app import tip
from mobcal.app.about import AboutDialog
from mobcal.app.inputs import InputsPanel
from mobcal.app.store import Store
from mobcal.app.worker import BatchWorker
from mobcal.batch import AUTO, CLASH, DEFAULT_SEED, DONE, Batch, BatchError
from mobcal.io.structure import StructureError
from mobcal.run import Job, Launcher, Result, Summary
from mobcal.settings import Settings, Source

GASES = (("He", ("he",)), ("N2", ("n2",)), ("He and N2", ("he", "n2")))
GENERATORS = (("Philox4x32-10", "philox"), ("RANLUX (the 2012 generator)", "ranlux"))
OTHER_TABLE = "Other file…"
RESULT_COLUMNS = ("Ion", "Gas", "TM (Å²)", "PA (Å²)", "EHS (Å²)", "Status", "Time")
CSV_HEADER = ("ion", "input", "gas", "TM", "PA", "EHS", "runs", "status", "seconds", "folder",
              "message")


def set_tip(key: str, *widgets: QWidget) -> None:
    """Give each widget, a control and its label, the tooltip ``mobcal.options`` holds."""
    for w in widgets:
        w.setToolTip(tip(options.tooltip(key)))


def form_row(lay: QFormLayout, label: str, widget: QWidget, key: str) -> None:
    lay.addRow(label, widget)
    set_tip(key, widget, lay.labelForField(widget))


def seeds(n: int) -> tuple[int, ...]:
    """The first ``n`` seeds: the 2012 seed, then each one after it."""
    return tuple(DEFAULT_SEED + k for k in range(n))


def reveal(path: Path) -> None:
    """Show a file or folder in Explorer, the Finder, or the desktop's file manager."""
    path = Path(path)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{path}"] if path.is_file()
                         else ["explorer", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))


def open_file(path: Path) -> None:
    """Open a text file in the desktop's viewer; on Windows, where ``.out`` has no viewer by
    default, in Notepad when nothing else takes it."""
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))) and sys.platform == "win32":
        subprocess.Popen(["notepad.exe", str(path)])


class MainWindow(QMainWindow):
    def __init__(self, store: Store | None = None, launcher: Launcher | None = None,
                 cpus: int | None = None) -> None:
        super().__init__()
        self.store = store or Store()
        self.launcher = launcher  # tests run a stand-in binary
        self.cpus = cpus or os.cpu_count() or 1
        self.worker: BatchWorker | None = None
        self.results: list[Result] = []
        self.running: dict[str, tuple[Job, float]] = {}  # label -> job, start time
        self.blocks: dict[str, tuple[int, int]] = {}
        self.plan: estimate.Plan | None = None
        self.batch_started = 0.0
        self._from = methods.CURRENT  # the method the fields were last filled from
        self._other_table: Path | None = None
        self._filling = False
        self._closing = False
        self.setWindowTitle(f"MOBCAL {mobcal.__version__}")

        left = QWidget()
        lv = QVBoxLayout(left)
        self.inputs = InputsPanel()
        self.inputs.start_dir = self.store.input_dir
        self.inputs.browse_dir_changed.connect(lambda d: setattr(self.store, "input_dir", d))
        box = QGroupBox("Inputs")
        QVBoxLayout(box).addWidget(self.inputs)
        lv.addWidget(box, 1)
        lv.addWidget(self._method_box())
        lv.addWidget(self._basics_box())
        lv.addWidget(self._advanced_box())
        lv.addWidget(self._folder_box())
        self.estimate_label = QLabel()
        self.estimate_label.setWordWrap(True)
        lv.addWidget(self.estimate_label)
        self._actions()

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(self._queue_box())
        rv.addWidget(self._progress_box())
        rv.addWidget(self._results_box(), 1)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([620, 780])
        self.setCentralWidget(split)
        if self.store.geometry is not None:
            self.restoreGeometry(self.store.geometry)
        else:
            self.resize(1280, 820)

        self.inputs.changed.connect(self.update_estimate)
        self.tick = QTimer(self)
        self.tick.setInterval(1000)
        self.tick.timeout.connect(self._draw_progress)
        self.apply_method(self.store.method if self.store.method in methods.METHODS
                          else methods.CURRENT)

    # --- the menus ------------------------------------------------------------------------

    def _actions(self) -> None:
        """Run, Stop and Resume queue as actions, in the Batch menu; File ▸ Exit, which closes
        the window by the same path as its close button; Help ▸ About. The roles put Exit and
        About in the application menu on macOS. Resume queue is enabled only while the queue
        holds batches and nothing runs, which is a queue put back at launch: otherwise the queue
        starts its next batch itself when one ends."""
        self.run_action = QAction("&Run", self)
        self.run_action.setShortcuts([QKeySequence("Ctrl+R"), QKeySequence("F5")])
        self.run_action.triggered.connect(self.run_clicked)
        self.stop_action = QAction("&Stop…", self)
        self.stop_action.setShortcut(QKeySequence("Shift+F5"))
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(self.stop_clicked)
        self.resume_action = QAction("Res&ume queue", self)
        self.resume_action.setEnabled(False)
        self.resume_action.triggered.connect(self.resume_queue)
        self.exit_action = QAction("E&xit", self)
        self.exit_action.setShortcuts(QKeySequence.StandardKey.Quit)
        self.exit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.exit_action.triggered.connect(self.close)
        self.about_action = QAction("&About MOBCAL", self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self.show_about)

        bar = self.menuBar()
        bar.addMenu("&File").addAction(self.exit_action)
        batch = bar.addMenu("&Batch")
        batch.addAction(self.run_action)
        batch.addAction(self.stop_action)
        batch.addSeparator()
        batch.addAction(self.resume_action)
        bar.addMenu("&Help").addAction(self.about_action)

    def resume_queue(self) -> None:
        if self.worker is None and self.queue.count():
            self.start(self._take_queued(0))

    def show_about(self) -> AboutDialog:
        """Open the About box, window-modal, and return it."""
        self.about = AboutDialog(self)
        self.about.open()
        return self.about

    # --- the form -------------------------------------------------------------------------

    def _method_box(self) -> QWidget:
        box = QGroupBox("Method")
        lay = QFormLayout(box)
        self.method_combo = QComboBox()
        for key, m in methods.METHODS.items():
            self.method_combo.addItem(m.title, key)
        self.method_combo.activated.connect(self._method_picked)
        form_row(lay, "Method", self.method_combo, "method")
        return box

    def _basics_box(self) -> QWidget:
        box = QGroupBox("Basics")
        lay = QFormLayout(box)
        self.gas_combo = QComboBox()
        for label, gases in GASES:
            self.gas_combo.addItem(label, gases)
        self.table_combo = QComboBox()
        self.seeds_spin = QSpinBox()
        self.seeds_spin.setRange(1, 1000)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.01, 100000.0)
        self.temperature.setDecimals(2)
        self.temperature.setSuffix(" K")
        form_row(lay, "Gas", self.gas_combo, "gas")
        form_row(lay, "Element table", self.table_combo, "parameters")
        form_row(lay, "Seeds per ion", self.seeds_spin, "seeds")
        form_row(lay, "Temperature", self.temperature, "temperature")
        self.gas_combo.currentIndexChanged.connect(self._gas_changed)
        self.table_combo.activated.connect(self._table_picked)
        self.seeds_spin.valueChanged.connect(self.update_estimate)
        self.temperature.valueChanged.connect(self.fields_changed)
        return box

    def _advanced_box(self) -> QWidget:
        outer = QWidget()
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        set_tip("advanced", self.advanced_toggle)
        self.advanced = QGroupBox()
        self.advanced.setVisible(False)

        def fold(on: bool) -> None:
            self.advanced.setVisible(on)
            self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if on
                                              else Qt.ArrowType.RightArrow)
        self.advanced_toggle.toggled.connect(fold)
        ov.addWidget(self.advanced_toggle)
        ov.addWidget(self.advanced)

        lay = QGridLayout(self.advanced)
        self.generator_combo = QComboBox()
        for label, g in GENERATORS:
            self.generator_combo.addItem(label, g)
        self.generator_combo.currentIndexChanged.connect(self.fields_changed)
        label = QLabel("Generator")
        set_tip("rng", self.generator_combo, label)
        lay.addWidget(label, 0, 0)
        lay.addWidget(self.generator_combo, 0, 1, 1, 3)
        self.counts: dict[str, QSpinBox] = {}
        for k, name in enumerate(settings.COUNTS):
            spin = QSpinBox()
            spin.setRange(*settings.BOUNDS[name])
            spin.setGroupSeparatorShown(True)
            spin.valueChanged.connect(self.fields_changed)
            self.counts[name] = spin
            label = QLabel(name)
            set_tip(name, spin, label)
            r, c = 1 + k // 2, (k % 2) * 2
            lay.addWidget(label, r, c)
            lay.addWidget(spin, r, c + 1)
        self.auto_cores = QCheckBox("Choose how the batch uses the cores")
        self.auto_cores.setChecked(True)
        set_tip("auto_cores", self.auto_cores)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, max(1, self.cpus))
        self.split_spin = QSpinBox()
        self.split_spin.setRange(1, 400)
        self.workers_spin.setValue(self.cpus)
        for w in (self.workers_spin, self.split_spin):
            w.setEnabled(False)
            w.valueChanged.connect(self.update_estimate)
        self.auto_cores.toggled.connect(lambda on: (self.workers_spin.setEnabled(not on),
                                                    self.split_spin.setEnabled(not on),
                                                    self.update_estimate()))
        lay.addWidget(self.auto_cores, 4, 0, 1, 4)
        for c, (text, key, spin) in enumerate((("Runs at once", "workers", self.workers_spin),
                                               ("Processes per run", "split", self.split_spin))):
            label = QLabel(text)
            set_tip(key, spin, label)
            lay.addWidget(label, 5, 2 * c)
            lay.addWidget(spin, 5, 2 * c + 1)
        self.cores_label = QLabel()
        self.cores_label.setWordWrap(True)
        lay.addWidget(self.cores_label, 6, 0, 1, 4)
        return outer

    def _folder_box(self) -> QWidget:
        box = QGroupBox("Results folder")
        lay = QHBoxLayout(box)
        self.out_edit = QLineEdit(self.store.default_out_dir())
        set_tip("out", self.out_edit)
        self.out_edit.editingFinished.connect(self.update_estimate)
        choose = QPushButton("Choose…")
        set_tip("choose_folder", choose)
        choose.clicked.connect(self._choose_folder)
        lay.addWidget(self.out_edit, 1)
        lay.addWidget(choose)
        return box

    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Results folder", self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self.update_estimate()

    @property
    def gases(self) -> tuple[str, ...]:
        return self.gas_combo.currentData()

    def _fill_tables(self, keep: str | Path | None) -> None:
        names = [n for n in parameters.names() if all(n in parameters.names(g)
                                                       for g in self.gases)]
        self.table_combo.clear()
        for n in names:
            label = (n if len(self.gases) > 1
                     else f"{n} ({parameters.shipped(self.gases[0], n).name})")
            self.table_combo.addItem(label, n)
        if len(self.gases) == 1:
            if self._other_table is not None:
                self.table_combo.addItem(self._other_table.name, str(self._other_table))
            self.table_combo.addItem(OTHER_TABLE, OTHER_TABLE)
        i = self.table_combo.findData(str(keep) if keep is not None else parameters.DEFAULT)
        self.table_combo.setCurrentIndex(i if i >= 0 else 0)

    def apply_method(self, key: str) -> None:
        """Fill every field from a method, as picking it in the dropdown does."""
        m = methods.get(key)
        self._filling = True
        try:
            if not all(g in m.gases for g in self.gases):
                self.gas_combo.setCurrentIndex(0)
            self._fill_tables(m.parameters)
            self.generator_combo.setCurrentIndex(self.generator_combo.findData(m.generator))
            self.temperature.setValue(m.settings.temperature)
            for name, spin in self.counts.items():
                spin.setValue(getattr(m.settings, name))
            self._from = key
        finally:
            self._filling = False
        self.store.method = key
        self.fields_changed()

    def _method_picked(self, index: int) -> None:
        key = self.method_combo.itemData(index)
        if key in methods.METHODS:
            self.apply_method(key)

    def _gas_changed(self) -> None:
        if self._filling:
            return
        keep = self.table_combo.currentData()
        self._fill_tables(keep if keep != OTHER_TABLE else None)
        self.fields_changed()

    def _table_picked(self, index: int) -> None:
        if self.table_combo.itemData(index) == OTHER_TABLE:
            path, _ = QFileDialog.getOpenFileName(self, "Element table", "", "TOML (*.toml)")
            if path:
                try:
                    ps = parameters.load(path, gas=self.gases[0])
                except parameters.ParameterError as e:
                    QMessageBox.warning(self, "Element table", str(e))
                    path = ""
                else:
                    self._other_table = ps.path
            self._fill_tables(self._other_table if path else parameters.DEFAULT)
        self.fields_changed()

    def table_value(self) -> str | None:
        v = self.table_combo.currentData()
        return None if v in (None, OTHER_TABLE) else v

    def form_settings(self) -> Settings:
        values = {"temperature": self.temperature.value(),
                  **{k: s.value() for k, s in self.counts.items()}}
        given = {k: v for k, v in values.items() if v != getattr(settings.DEFAULTS, k)}
        return Settings(**values, source=Source(overrides=given))

    def method_now(self) -> str:
        """The method the fields make, for every gas chosen, else custom."""
        gen = self.generator_combo.currentData()
        try:
            st = self.form_settings()
        except settings.SettingsError:
            return methods.CUSTOM
        table = self.table_value()
        found = set()
        for gas in self.gases:
            if table in parameters.names(gas):
                set_name = table
            else:
                try:
                    set_name = parameters.load(table, gas=gas).set_name if table else None
                except parameters.ParameterError:
                    set_name = None
            found.add(methods.identify(gas, set_name, gen, st))
        return found.pop() if len(found) == 1 else methods.CUSTOM

    def method_title(self) -> str:
        now = self.method_now()
        if now != methods.CUSTOM:
            return methods.TITLES[now]
        return f"Custom (from {methods.TITLES[self._from]})"

    def fields_changed(self) -> None:
        if self._filling:
            return
        now = self.method_now()
        while self.method_combo.count() > len(methods.METHODS):
            self.method_combo.removeItem(self.method_combo.count() - 1)
        if now == methods.CUSTOM:
            self.method_combo.addItem(self.method_title(), methods.CUSTOM)
            self.method_combo.setCurrentIndex(self.method_combo.count() - 1)
        else:
            self.method_combo.setCurrentIndex(self.method_combo.findData(now))
            if now != self._from:
                self._from = now
        self.update_estimate()

    # --- the batch ------------------------------------------------------------------------

    @property
    def out_dir(self) -> Path:
        return Path(self.out_edit.text().strip() or self.store.default_out_dir())

    def form_batch(self) -> Batch:
        """The batch the form describes, with each import's ``.mfj`` where it will be
        written. Raises BatchError or SettingsError."""
        out = self.out_dir
        base = self._from if all(g in methods.get(self._from).gases for g in self.gases) \
            else methods.CURRENT
        split: int | str | None = AUTO
        workers = None
        if not self.auto_cores.isChecked():
            split = self.split_spin.value() if self.split_spin.value() > 1 else None
            workers = self.workers_spin.value()
        return Batch(tuple(i.mfj_path(out) for i in self.inputs.items), out, self.gases,
                     seeds(self.seeds_spin.value()), base, parameters=self.table_value(),
                     generator=self.generator_combo.currentData(),
                     settings=self.form_settings(), split=split, workers=workers)

    def update_estimate(self) -> None:
        problems = self.inputs.problems()
        if not self.inputs.items:
            problems = ["add an input"]
        try:
            b = self.form_batch()
        except (BatchError, settings.SettingsError, ValueError) as e:
            self.estimate_label.setText(str(e))
            self.run_action.setEnabled(False)
            return
        if problems:
            self.estimate_label.setText("; ".join(problems))
            self.run_action.setEnabled(False)
            self.cores_label.setText("")
            return
        try:
            p = b.plan(self.cpus, sizes=self.inputs.sizes(self.out_dir))
        except (BatchError, ValueError) as e:
            self.estimate_label.setText(str(e))
            self.run_action.setEnabled(False)
            return
        self.estimate_label.setText(f"{self.method_title()}: {estimate.describe(p)}")
        self.cores_label.setText(estimate.describe(p).split(";")[0] + f", of {self.cpus} CPUs")
        self.run_action.setEnabled(True)
        self.run_action.setText("Add to &queue" if self.worker is not None else "&Run")

    def run_clicked(self) -> None:
        if self.inputs.problems() or not self.inputs.items:
            return
        try:
            b = self.form_batch()
            self.out_dir.mkdir(parents=True, exist_ok=True)
            for item in self.inputs.items:
                item.write(self.out_dir, self.gases)
        except (BatchError, settings.SettingsError, StructureError, OSError, ValueError) as e:
            QMessageBox.warning(self, "Run", str(e))
            return
        found = batches.prior(b.jobs())
        clashes = [p for p in found if p.kind == CLASH]
        if clashes:
            QMessageBox.warning(self, "Run", "This folder holds runs of other inputs under the "
                                "same names:\n\n" + "\n".join(f"{p.job.run_dir.name}: "
                                                               f"{p.detail}" for p in clashes)
                                + "\n\nRename the input or choose another results folder.")
            return
        done = [p for p in found if p.kind == DONE]
        if done:
            ask = QMessageBox(QMessageBox.Icon.Question, "Run",
                              f"{len(done)} of these {len(b.jobs())} runs are already in this "
                              "folder, complete.", parent=self)
            skip = ask.addButton("Skip them", QMessageBox.ButtonRole.AcceptRole)
            again = ask.addButton("Run them again", QMessageBox.ButtonRole.DestructiveRole)
            ask.addButton(QMessageBox.StandardButton.Cancel)
            ask.exec()
            if ask.clickedButton() not in (skip, again):
                return
            if ask.clickedButton() is skip:
                b = dataclasses.replace(b, skip_done=True)
        self.store.out_dir = str(self.out_dir)
        if self.worker is not None:
            self.enqueue(b)
        else:
            self.start(b)

    # --- running ---------------------------------------------------------------------------

    def start(self, b: Batch) -> None:
        self.worker = BatchWorker(b, self.inputs.sizes(b.out_dir), self.launcher, self.cpus)
        self.worker.planned.connect(self._on_planned)
        self.worker.run_started.connect(self._on_started)
        self.worker.run_landed.connect(self._on_landed)
        self.worker.blocks.connect(self._on_blocks)
        self.worker.finished_batch.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._worker_done)
        self.results, self.running, self.blocks, self.plan = [], {}, {}, None
        self.batch_started = time.monotonic()
        self.current_title = b.title()
        self.status_label.setText(f"{self.current_title}: starting…")
        self.progress.setRange(0, 0)
        self.results_table.setRowCount(0)
        self.stop_action.setEnabled(True)
        self.resume_action.setEnabled(False)
        self.methods_button.setEnabled(False)
        self.run_action.setText("Add to &queue")
        self.tick.start()
        self.worker.start()

    def _on_planned(self, p: estimate.Plan) -> None:
        self.plan = p
        self.progress.setRange(0, len(p.jobs))
        self.progress.setValue(0)
        self._draw_progress()

    def _on_started(self, job: Job) -> None:
        self.running[job.label] = (job, time.monotonic())
        self._draw_progress()

    def _on_blocks(self, job: Job, n: int, total: int) -> None:
        self.blocks[job.label] = (n, total)

    def _on_landed(self, r: Result, done: int, total: int) -> None:
        self.running.pop(r.job.label, None)
        self.results.append(r)
        self.progress.setValue(done)
        self._draw_results()
        self._draw_progress()

    def _on_finished(self, s: Summary) -> None:
        self.results = list(s.results)
        self._draw_results()
        self.last_summary = s
        out = self.worker.batch.out_dir if self.worker else self.out_dir
        self.status_label.setText(f"{self.current_title}: {s}; summary.csv in {out}")
        self.methods_button.setEnabled(bool(s.ok))

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(f"{self.current_title}: did not run: {message}")

    def _worker_done(self) -> None:
        if self._closing:
            return
        self.tick.stop()
        self.running.clear()
        self.last_batch = self.worker.batch if self.worker else None
        self.worker = None
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.stop_action.setEnabled(False)
        self.run_action.setText("&Run")
        self._draw_running()
        if self.queue.count():
            self.start(self._take_queued(0))
        else:
            self.resume_action.setEnabled(False)
        self.update_estimate()

    def stop_clicked(self) -> None:
        if self.worker is None:
            return
        if QMessageBox.question(self, "Stop", "Stop every run of this batch? Runs already "
                                "complete keep their results; the stopped ones keep their "
                                "folders as partial records.") \
                != QMessageBox.StandardButton.Yes:
            return
        self.status_label.setText(f"{self.current_title}: stopping…")
        self.worker.stop()

    def _draw_progress(self) -> None:
        if self.worker is None:
            return
        elapsed = estimate.duration(time.monotonic() - self.batch_started)
        if self.plan is not None:
            n = len(self.plan.jobs)
            self.status_label.setText(
                f"{self.current_title}: {len(self.results)} of {n} run{'s' if n != 1 else ''} "
                f"done, {elapsed} elapsed, estimate about {estimate.duration(self.plan.seconds)}"
                + (" (stopping)" if self.worker.stopping else ""))
        self._draw_running()

    def _draw_running(self) -> None:
        self.running_list.clear()
        now = time.monotonic()
        for label, (job, t0) in self.running.items():
            text = f"{label}: {estimate.duration(now - t0)}"
            if job.split:
                n, total = self.blocks.get(label, (0, 0))
                text += f", {job.split} processes" + (f", {n} of {total} blocks" if total else "")
            self.running_list.addItem(text)

    # --- the queue -------------------------------------------------------------------------

    def _queue_box(self) -> QWidget:
        box = QGroupBox("Queue")
        lay = QVBoxLayout(box)
        self.queue = QListWidget()
        self.queue.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.queue.model().rowsMoved.connect(self.save_queue)
        self.queue.setMaximumHeight(120)
        set_tip("queue", self.queue)
        row = QHBoxLayout()
        remove = QPushButton("Remove")
        set_tip("remove_queued", remove)
        remove.clicked.connect(self._remove_queued)
        row.addWidget(remove)
        row.addStretch(1)
        lay.addWidget(self.queue)
        lay.addLayout(row)
        return box

    def queued(self) -> list[Batch]:
        return [self.queue.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.queue.count())]

    def enqueue(self, b: Batch) -> None:
        n = len(b.inputs)
        text = (f"{b.title()}: {n} input{'s' if n != 1 else ''}, "
                f"{' and '.join(parameters.GAS[g] for g in b.gases)}, {len(b.seeds)} "
                f"seed{'s' if len(b.seeds) != 1 else ''}, to {b.out_dir}")
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, b)
        self.queue.addItem(item)
        self.resume_action.setEnabled(self.worker is None)
        self.save_queue()

    def _take_queued(self, row: int) -> Batch:
        b = self.queue.takeItem(row).data(Qt.ItemDataRole.UserRole)
        self.save_queue()
        return b

    def _remove_queued(self) -> None:
        for item in self.queue.selectedItems():
            self.queue.takeItem(self.queue.row(item))
        self.resume_action.setEnabled(self.worker is None and self.queue.count() > 0)
        self.save_queue()

    def save_queue(self, *_) -> None:
        try:
            batches.save(self.queued(), self.store.queue_path)
        except OSError as e:
            self.status_label.setText(f"could not save the queue: {e}")

    def offer_saved_queue(self) -> None:
        """At launch: offer back the batches that were queued when the window last closed."""
        path = self.store.queue_path
        if not path.is_file():
            return
        try:
            saved, problems = batches.load(path)
        except (OSError, ValueError) as e:
            saved, problems = [], [str(e)]
        if not saved:
            return
        n = len(saved)
        text = (f"{n} batch{'es were' if n != 1 else ' was'} queued when MOBCAL last closed. "
                "Put them back in the queue?")
        if problems:
            text += "\n\nNot restored:\n" + "\n".join(problems)
        if QMessageBox.question(self, "Queue", text) == QMessageBox.StandardButton.Yes:
            for b in saved:
                self.enqueue(b)
        else:
            self.save_queue()

    # --- progress and results ----------------------------------------------------------

    def _progress_box(self) -> QWidget:
        box = QGroupBox("Progress")
        lay = QVBoxLayout(box)
        self.status_label = QLabel("Nothing running.")
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.running_list = QListWidget()
        self.running_list.setMaximumHeight(100)
        set_tip("progress", self.progress)
        set_tip("running", self.running_list)
        lay.addWidget(self.status_label)
        lay.addWidget(self.progress)
        lay.addWidget(self.running_list)
        return box

    def _results_box(self) -> QWidget:
        box = QGroupBox("Results")
        lay = QVBoxLayout(box)
        self.results_table = QTableWidget(0, len(RESULT_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        set_tip("results", self.results_table)
        for c, name in enumerate(RESULT_COLUMNS):
            self.results_table.horizontalHeaderItem(c).setToolTip(
                tip(options.COLUMNS["results"][name]))
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.verticalHeader().setVisible(False)
        h = self.results_table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(RESULT_COLUMNS.index("Status"), QHeaderView.ResizeMode.Stretch)
        self.results_table.doubleClicked.connect(lambda _: self.open_output())
        row = QHBoxLayout()
        buttons = (("Copy", "copy", self.copy_results), ("Save CSV…", "save_csv", self.save_csv),
                   ("Show in folder", "show_in_folder", self.show_in_folder),
                   ("Open output", "open_output", self.open_output))
        for text, key, slot in buttons:
            b = QPushButton(text)
            set_tip(key, b)
            b.clicked.connect(slot)
            row.addWidget(b)
        self.methods_button = QPushButton("Copy methods text")
        self.methods_button.setEnabled(False)
        set_tip("methods_text", self.methods_button)
        self.methods_button.clicked.connect(self.copy_methods_text)
        row.addWidget(self.methods_button)
        row.addStretch(1)
        lay.addWidget(self.results_table)
        lay.addLayout(row)
        return box

    def result_rows(self) -> list[batches.Row]:
        """One row per ion and gas, in the batch's order, whatever order the runs land in."""
        order = {j.label: i for i, j in enumerate(self.plan.jobs)} if self.plan else {}
        return batches.rows(sorted(self.results, key=lambda r: order.get(r.job.label, 0)))

    def _draw_results(self) -> None:
        rows = self.result_rows()
        self.results_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cells = (r.input.stem, parameters.GAS[r.gas], r.value("TM"), r.value("PA"),
                     r.value("EHS"), r.status, estimate.duration(r.seconds) if r.seconds else "")
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if c == 5 and r.message:
                    item.setToolTip(r.message)
                self.results_table.setItem(i, c, item)

    def _selected_row(self) -> batches.Row | None:
        rows = self.result_rows()
        i = self.results_table.currentRow()
        return rows[i] if 0 <= i < len(rows) else (rows[0] if len(rows) == 1 else None)

    def csv_text(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(CSV_HEADER)
        for r in self.result_rows():
            w.writerow((r.input.stem, str(r.input), parameters.GAS[r.gas], r.value("TM"),
                        r.value("PA"), r.value("EHS"), len(r.results), r.status,
                        round(r.seconds, 1), str(r.run_dir.parent), r.message))
        return buf.getvalue()

    def copy_results(self) -> None:
        QGuiApplication.clipboard().setText(self.csv_text().replace(",", "\t"))

    def save_csv(self) -> None:
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save results", str(
            self.out_dir / "results.csv"), "CSV (*.csv)")
        if path:
            Path(path).write_text(self.csv_text(), encoding="utf-8", newline="")

    def show_in_folder(self) -> None:
        r = self._selected_row()
        if r is not None and r.run_dir.exists():
            reveal(r.run_dir)
        elif self.out_dir.exists():
            reveal(self.out_dir)

    def open_output(self) -> None:
        r = self._selected_row()
        if r is not None and r.output is not None and r.output.is_file():
            open_file(r.output)

    def copy_methods_text(self) -> None:
        dirs = [r.job.run_dir for r in self.results if r.ok]
        try:
            text = methods.text(methods.read_records(dirs))
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "Methods text", str(e))
            return
        QGuiApplication.clipboard().setText(text)
        self.status_label.setText(self.status_label.text().split(" Methods text")[0]
                                  + " Methods text copied.")

    # --- closing ---------------------------------------------------------------------------

    def closeEvent(self, e) -> None:  # noqa: N802 -- Qt's name
        if self.worker is not None:
            if QMessageBox.question(self, "Close", "A batch is running. Stop it and close? "
                                    "Queued batches are kept for next time.") \
                    != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self._closing = True  # the batch's end starts nothing queued
            w = self.worker
            w.stop()
            w.wait(30_000)
        self.save_queue()
        self.store.geometry = self.saveGeometry()
        e.accept()
