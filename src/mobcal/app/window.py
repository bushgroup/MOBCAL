"""The main window: the form, the queue, the progress and the results.

Left, the form makes a ``mobcal.batch.Batch``: the inputs, a Method that fills every field
(the five shipped methods, then the method files loaded or saved, remembered), Basics (gas,
element table, seeds, temperature), an Advanced fold (generator, the five sampling counts, how
the batch uses the cores), and the results folder, one per study, remembered. The method shown
is the one the fields make, or *Custom (from …)* once a field moves off every method; the runs'
records say the same. The gas is a method's field like any other: changing it shows the same
method in the other gas when there is one. Under the form, the estimate for the batch as it
stands.

Above, a menu bar: File ▸ Load method…, Save method… and Exit, and Help ▸ MOBCAL Help (F1,
the guide in a window of its own, ``mobcal.app.help``) and About. Load method adds a method file
to the Method list and Save method writes the form's method fields to one, ``NAME.method.json``,
and adds it; a method's description, when it has one, is its tooltip in the list. The list is
remembered by path and SHA-256, and a file that has gone, changed or no longer loads (a TOML
method file of 2.0 among them) is dropped at the next launch with a message
(``report_dropped_methods``).

Right, the queue, the progress and the results. Every batch control is in the Queue box, and
none has a menu entry or a shortcut. Add batch appends the form's batch to the queue and never
starts it. One toggle follows the queue's state (``state``, the one place that knows it):
*Start queue* with batches waiting and none running or paused, *Pause queue* while one runs,
*Pausing…* (disabled) while the runs in flight of a paused batch finish, *Resume queue* once it
is paused. Pause drains: no new run starts, the runs in flight land as usual, and the batch
stays the queue's top row holding exactly the runs that never started (``Batch.remaining``);
the queue does not move on until Resume. The running or paused batch is that pinned top row,
marked, never dragged and never dropped above; waiting rows reorder by drag. Remove batch takes
the selected waiting rows out, and on the top row asks, then stops the running batch (or forgets
the paused one), leaving the queue paused. Each row shows its estimate (the running row, the
time left), and a line under the list gives the total. The queue, the running or paused batch
first with its runs not complete, is saved on every change and offered back, paused, at the next
launch. Progress is runs done of N, each running run's elapsed time (and blocks written, for a
split run), against the estimate. Results are one row per ion and gas, TM headline, mean ± s.d.
over seeds, with Copy, Save CSV, Show in folder, Open output and Copy methods text. Closing while
a batch runs asks, then kills its runs in flight; the batch is kept as the queue's first entry.

Every control and column header has a tooltip from ``mobcal.options``; a control that an
option of ``mobcal run`` also sets shows that option's description, so the two cannot drift.
"""

from __future__ import annotations

import csv
import dataclasses
import io
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
    QInputDialog,
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
from mobcal.app.help import HelpWindow
from mobcal.app.inputs import InputsPanel
from mobcal.app.store import Store
from mobcal.app.worker import BatchWorker
from mobcal.batch import AUTO, CLASH, DEFAULT_SEED, DONE, Batch, BatchError
from mobcal.io import ion
from mobcal.io.structure import StructureError
from mobcal.run import Job, Launcher, Result, Summary, cores, processors
from mobcal.settings import Settings, Source

GASES = (("He", "he"), ("N2", "n2"))
GENERATORS = (("Philox4x32-10", "philox"), ("RANLUX (the 2012 generator)", "ranlux"))
OTHER_TABLE = "Other file…"
METHOD_FILTER = f"Method (*{methods.SUFFIX})"
RESULT_COLUMNS = ("Ion", "Gas", "TM (Å²)", "PA (Å²)", "EHS (Å²)", "Status", "Time")
CSV_HEADER = ("ion", "input", "gas", "TM", "PA", "EHS", "runs", "status", "seconds", "folder",
              "message")
PINNED = Qt.ItemDataRole.UserRole + 1  # the queue's top row: the running or paused batch
SECONDS = Qt.ItemDataRole.UserRole + 2  # a row's estimate, None when it cannot be made
IDLE, RUNNING, PAUSING, PAUSED, STOPPING = "idle", "running", "pausing", "paused", "stopping"
TOGGLE = {IDLE: ("Start queue", "start_queue"), RUNNING: ("Pause queue", "pause_queue"),
          PAUSING: ("Pausing…", "pausing"), STOPPING: ("Pause queue", "pause_queue"),
          PAUSED: ("Resume queue", "resume_queue")}
MARK = {RUNNING: "Running", PAUSING: "Pausing", STOPPING: "Stopping", PAUSED: "Paused"}


def set_tip(key: str, *widgets: QWidget) -> None:
    """Give each widget, a control and its label, the tooltip ``mobcal.options`` holds."""
    for w in widgets:
        w.setToolTip(tip(options.tooltip(key)))


def form_row(lay: QFormLayout, label: str, widget: QWidget, key: str) -> None:
    lay.addRow(label, widget)
    set_tip(key, widget, lay.labelForField(widget))


def seeds(n: int, first: int = DEFAULT_SEED) -> tuple[int, ...]:
    """The first ``n`` seeds: ``first`` (the method's, the 2012 seed under a method without
    one), then each one after it."""
    return tuple(first + k for k in range(n))


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
        self.cpus = cpus or cores()  # what the batch allocates; the spin box allows processors()
        self.worker: BatchWorker | None = None
        self.current: Batch | None = None  # the queue's top row: running, pausing or paused
        self.help: HelpWindow | None = None
        self.results: list[Result] = []
        self.running: dict[str, tuple[Job, float]] = {}  # label -> job, start time
        self.blocks: dict[str, tuple[int, int]] = {}
        self.plan: estimate.Plan | None = None
        self.batch_started = 0.0
        self._from = methods.DEFAULT  # the method the fields were last filled from, by ref
        self._other_table: tuple[Path, str] | None = None  # a table of one's own and its gas
        self.loaded: dict[str, methods.Method] = {}  # the method files in the list, by path
        self.dropped: list[str] = []  # remembered method files that no longer load, and why
        self._read_remembered_methods()
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
        self.apply_method(self.store.method if self.method(self.store.method) is not None
                          else methods.DEFAULT)

    # --- the menus ------------------------------------------------------------------------

    def _actions(self) -> None:
        """File ▸ Load method…, Save method… and Exit, which closes the window by the same path
        as its close button; Help ▸ MOBCAL Help, at the platform's help key, and About. The
        roles put Exit and About in the application menu on macOS. The batch controls are the
        Queue box's buttons, with no menu entry and no shortcut."""
        self.load_method_action = QAction("&Load method…", self)
        self.load_method_action.setToolTip(options.tooltip("load_method"))
        self.load_method_action.triggered.connect(lambda: self.load_method())
        self.save_method_action = QAction("&Save method…", self)
        self.save_method_action.setToolTip(options.tooltip("save_method"))
        self.save_method_action.triggered.connect(lambda: self.save_method())
        self.exit_action = QAction("E&xit", self)
        self.exit_action.setShortcuts(QKeySequence.StandardKey.Quit)
        self.exit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.exit_action.triggered.connect(self.close)
        self.help_action = QAction("MOBCAL &Help", self)
        self.help_action.setShortcuts(QKeySequence.StandardKey.HelpContents)
        self.help_action.triggered.connect(self.show_help)
        self.about_action = QAction("&About MOBCAL", self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self.show_about)

        bar = self.menuBar()
        file = bar.addMenu("&File")
        file.setToolTipsVisible(True)
        file.addAction(self.load_method_action)
        file.addAction(self.save_method_action)
        file.addSeparator()
        file.addAction(self.exit_action)
        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.help_action)
        help_menu.addAction(self.about_action)

    def show_help(self) -> HelpWindow:
        """Show the guide, made at the first call and brought forward at every later one."""
        if self.help is None:
            self.help = HelpWindow(self)
        self.help.show()
        self.help.raise_()
        self.help.activateWindow()
        return self.help

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
        self._fill_methods()
        self.method_combo.activated.connect(self._method_picked)
        form_row(lay, "Method", self.method_combo, "method")
        return box

    def _basics_box(self) -> QWidget:
        box = QGroupBox("Basics")
        lay = QFormLayout(box)
        self.gas_combo = QComboBox()
        for label, gas in GASES:
            self.gas_combo.addItem(label, gas)
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
        self.mode_combo = QComboBox()
        for m in estimate.MODES:
            self.mode_combo.addItem(estimate.MODE_TITLES[m], m)
        self.mode_combo.setCurrentIndex(estimate.MODES.index(self.store.mode))
        set_tip("mode", self.mode_combo)
        self.mode_combo.currentIndexChanged.connect(self.mode_changed)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, max(1, self.cpus, processors()))
        self.split_spin = QSpinBox()
        self.split_spin.setRange(1, 400)
        self.workers_spin.setValue(self.cpus)
        for w in (self.workers_spin, self.split_spin):
            w.setEnabled(False)
            w.valueChanged.connect(self.update_estimate)
        self.auto_cores.toggled.connect(lambda on: (self.workers_spin.setEnabled(not on),
                                                    self.split_spin.setEnabled(not on),
                                                    self.mode_combo.setEnabled(on),
                                                    self.update_estimate()))
        lay.addWidget(self.auto_cores, 4, 0, 1, 2)
        lay.addWidget(self.mode_combo, 4, 2, 1, 2)
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
    def gas(self) -> str:
        return self.gas_combo.currentData()

    def _fill_tables(self, keep: str | Path | None) -> None:
        self.table_combo.clear()
        for n in parameters.names(self.gas):
            self.table_combo.addItem(f"{n} ({parameters.shipped(self.gas, n).name})", n)
        if self._other_table is not None and self._other_table[1] == self.gas:
            self.table_combo.addItem(self._other_table[0].name, str(self._other_table[0]))
        self.table_combo.addItem(OTHER_TABLE, OTHER_TABLE)
        i = self.table_combo.findData(str(keep) if keep is not None else parameters.DEFAULT)
        self.table_combo.setCurrentIndex(i if i >= 0 else 0)

    # --- the methods ------------------------------------------------------------------------

    def method(self, ref: str) -> methods.Method | None:
        """A shipped method by its key, or a method file in the list by its path."""
        return methods.METHODS.get(ref) or self.loaded.get(ref)

    def _fill_methods(self) -> None:
        """The Method list: the shipped methods, then the method files; ``fields_changed``
        adds Custom when the fields are none of them."""
        self.method_combo.clear()
        for m in [*methods.METHODS.values(), *self.loaded.values()]:
            self.method_combo.addItem(m.title, m.ref)
            if m.description:
                self.method_combo.setItemData(self.method_combo.count() - 1, m.description,
                                              Qt.ItemDataRole.ToolTipRole)

    def _read_remembered_methods(self) -> None:
        """Load the method files the list held at the last close. One that has gone, changed
        since it was added, or no longer loads is dropped, and ``dropped`` says why."""
        kept = []
        for path, sha in self.store.methods:
            if not Path(path).is_file():
                self.dropped.append(f"{path}: the file is no longer there.")
                continue
            try:
                m = methods.load(path)
            except methods.MethodError as e:
                self.dropped.append(f"{e}.")
                continue
            if m.sha256 != sha:
                self.dropped.append(f"{path}: the file has changed since it was added; load it "
                                    "again to use it as it is now.")
                continue
            clash = self._name_clash(m)
            if clash:
                self.dropped.append(clash)
                continue
            self.loaded[m.ref] = m
            kept.append((m.ref, m.sha256))
        if self.dropped:
            self.store.methods = kept

    def report_dropped_methods(self) -> None:
        """At launch: say which remembered method files were dropped, and why."""
        if self.dropped:
            n = len(self.dropped)
            QMessageBox.information(
                self, "Methods", f"{n} method file{'s were' if n != 1 else ' was'} removed from "
                "the Method list:\n\n" + "\n".join(self.dropped))
            self.dropped = []

    def _name_clash(self, m: methods.Method) -> str:
        """Why a method file cannot join the list under its name, or empty."""
        if any(b.name == m.name for b in methods.METHODS.values()):
            return f"{m.path}: {m.name!r} is the name of a shipped method; give the file another."
        other = next((o for o in self.loaded.values()
                      if o.name == m.name and o.ref != m.ref), None)
        if other is not None:
            return (f"{m.path}: the Method list already holds {m.name!r}, from {other.path}; "
                    "give one of them another name.")
        return ""

    def _add_method(self, m: methods.Method) -> None:
        self.loaded[m.ref] = m
        self.store.methods = [(o.ref, o.sha256) for o in self.loaded.values()]
        self._fill_methods()
        self.apply_method(m.ref)

    def load_method(self, path: str | Path | None = None) -> methods.Method | None:
        """File ▸ Load method…: add a method file to the list and fill the fields from it."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Load method", self.store.input_dir,
                                                  METHOD_FILTER)
            if not path:
                return None
        try:
            m = methods.load(Path(path).resolve())
        except methods.MethodError as e:
            QMessageBox.warning(self, "Load method", str(e))
            return None
        clash = self._name_clash(m)
        if clash:
            QMessageBox.warning(self, "Load method", clash)
            return None
        self._add_method(m)
        return m

    def save_method(self, path: str | Path | None = None,
                    name: str | None = None) -> methods.Method | None:
        """File ▸ Save method…: write the gas, table, generator and settings to a method file,
        and the seed and description of the method file the fields came from when it carries
        them, add it to the list and select it. The file is named ``NAME.method.json``."""
        try:
            st = self.form_settings()
        except settings.SettingsError as e:
            QMessageBox.warning(self, "Save method", str(e))
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save method", self.store.input_dir,
                                                  METHOD_FILTER)
            if not path:
                return None
        path = methods.file_name(Path(path).resolve())
        if name is None:
            name, ok = QInputDialog.getText(self, "Save method", "Name in the Method list:",
                                            text=methods.stem(path))
            if not ok:
                return None
        name = name.strip()
        clash = self._name_clash(dataclasses.replace(
            methods.METHODS[methods.DEFAULT], name=name, path=path, shipped=False))
        if clash:
            QMessageBox.warning(self, "Save method", clash)
            return None
        try:
            m = methods.save(path, name, self.gas, self.table_value() or parameters.DEFAULT,
                             self.generator_combo.currentData(), st, seed=self.method_seed,
                             description=self.method_description)
        except methods.MethodError as e:
            QMessageBox.warning(self, "Save method", str(e))
            return None
        self._add_method(m)
        return m

    def apply_method(self, ref: str) -> None:
        """Fill every field from a method, as picking it in the dropdown does."""
        m = self.method(ref)
        self._filling = True
        try:
            self.gas_combo.setCurrentIndex(self.gas_combo.findData(m.gas))
            if m.table is not None:
                self._other_table = (m.table, m.gas)
            self._fill_tables(m.table if m.table is not None else m.parameters)
            self.generator_combo.setCurrentIndex(self.generator_combo.findData(m.generator))
            self.temperature.setValue(m.settings.temperature)
            for name, spin in self.counts.items():
                spin.setValue(getattr(m.settings, name))
            self._from = ref
            self._show_seed()
        finally:
            self._filling = False
        self.store.method = ref
        self.fields_changed()

    @property
    def method_seed(self) -> int | None:
        """The seed of the method the fields came from, when its file carries one."""
        m = self.method(self._from)
        return None if m is None else m.seed

    @property
    def method_description(self) -> str | None:
        """The description of the method file the fields came from, when it has one; a
        shipped method's says what that method is, so Save method does not carry it."""
        m = self.method(self._from)
        return None if m is None or m.shipped else m.description

    def _show_seed(self) -> None:
        """Seeds per ion says the first seed when the method carries one."""
        seed = self.method_seed
        self.seeds_spin.setSuffix("" if seed is None else f", from seed {seed}")

    def _method_picked(self, index: int) -> None:
        ref = self.method_combo.itemData(index)
        if self.method(ref) is not None:
            self.apply_method(ref)

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
                    ps = parameters.load(path, gas=self.gas)
                except parameters.ParameterError as e:
                    QMessageBox.warning(self, "Element table", str(e))
                    path = ""
                else:
                    self._other_table = (ps.path, self.gas)
            self._fill_tables(self._other_table[0] if path else parameters.DEFAULT)
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
        """The method the fields make, by ref: the one they were filled from while they are
        its fields, else the first shipped method or method file they are, else custom."""
        gen = self.generator_combo.currentData()
        try:
            st = self.form_settings()
        except settings.SettingsError:
            return methods.CUSTOM
        gas, table = self.gas, self.table_value()
        if table in parameters.names(gas):
            set_name, sha = table, parameters.SHA256[parameters.SETS[gas][table]]
        else:
            try:
                ps = parameters.load(table, gas=gas)
                set_name, sha = ps.set_name, ps.sha256
            except (parameters.ParameterError, TypeError):
                return methods.CUSTOM
        for ref in (self._from, *methods.METHODS, *self.loaded):
            m = self.method(ref)
            if m is not None and m.matches(gas, set_name, sha, gen, st):
                return ref
        return methods.CUSTOM

    def method_title(self) -> str:
        now = self.method_now()
        if now != methods.CUSTOM:
            return self.method(now).title
        return f"Custom (from {self.method(self._from).title})"

    def fields_changed(self) -> None:
        if self._filling:
            return
        now = self.method_now()
        while self.method_combo.count() > len(methods.METHODS) + len(self.loaded):
            self.method_combo.removeItem(self.method_combo.count() - 1)
        if now == methods.CUSTOM:
            self.method_combo.addItem(self.method_title(), methods.CUSTOM)
            self.method_combo.setCurrentIndex(self.method_combo.count() - 1)
        else:
            self.method_combo.setCurrentIndex(self.method_combo.findData(now))
            if now != self._from:
                self._from = now
                self._show_seed()
        self.update_estimate()

    # --- the batch ------------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """How the batch chooses under the check box: the window's preference."""
        return str(self.mode_combo.currentData())

    def mode_changed(self) -> None:
        self.store.mode = self.mode
        self.update_estimate()

    @property
    def out_dir(self) -> Path:
        return Path(self.out_edit.text().strip() or self.store.default_out_dir())

    def form_batch(self) -> Batch:
        """The batch the form describes, with each import's ion file where it will be
        written. Raises BatchError or SettingsError."""
        out = self.out_dir
        split: int | str | None = AUTO
        workers = None
        if not self.auto_cores.isChecked():
            split = self.split_spin.value() if self.split_spin.value() > 1 else None
            workers = self.workers_spin.value()
        return Batch(tuple(i.run_path(out) for i in self.inputs.items), out, self._from,
                     gas=self.gas,
                     seeds=seeds(self.seeds_spin.value(), self.method_seed or DEFAULT_SEED),
                     parameters=self.table_value(),
                     generator=self.generator_combo.currentData(),
                     settings=self.form_settings(), split=split, workers=workers)

    def update_estimate(self) -> None:
        self.inputs.set_gas(self.gas)
        problems = self.inputs.problems()
        if not self.inputs.items:
            problems = ["add an input"]
        try:
            b = self.form_batch()
        except (BatchError, settings.SettingsError, ValueError) as e:
            self.estimate_label.setText(str(e))
            self.add_batch_button.setEnabled(False)
            return
        if problems:
            self.estimate_label.setText("; ".join(problems))
            self.add_batch_button.setEnabled(False)
            self.cores_label.setText("")
            return
        try:
            p = b.plan(self.cpus, sizes=self.inputs.sizes(self.out_dir), mode=self.mode)
        except (BatchError, ValueError) as e:
            self.estimate_label.setText(str(e))
            self.add_batch_button.setEnabled(False)
            return
        self.estimate_label.setText(f"{self.method_title()}: {estimate.describe(p)}")
        self.cores_label.setText(estimate.describe(p).split(";")[0] + f", of {self.cpus} cores")
        self.add_batch_button.setEnabled(True)

    def add_batch_clicked(self) -> None:
        """Add batch: the form's batch, checked against the results folder, to the end of the
        queue. It never starts anything."""
        if self.inputs.problems() or not self.inputs.items:
            return
        try:
            b = self.form_batch()
            self.out_dir.mkdir(parents=True, exist_ok=True)
            for item in self.inputs.items:
                item.write(self.out_dir, (self.gas,))
        except (BatchError, settings.SettingsError, StructureError, OSError, ValueError) as e:
            QMessageBox.warning(self, "Add batch", str(e))
            return
        found = batches.prior(b.jobs())
        clashes = [p for p in found if p.kind == CLASH]
        if clashes:
            QMessageBox.warning(self, "Add batch", "This folder holds runs of other inputs under "
                                "the same names:\n\n" + "\n".join(f"{p.job.run_dir.name}: "
                                                               f"{p.detail}" for p in clashes)
                                + "\n\nRename the input or choose another results folder.")
            return
        done = [p for p in found if p.kind == DONE]
        if done:
            ask = QMessageBox(QMessageBox.Icon.Question, "Add batch",
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
        self.enqueue(b)

    # --- running ---------------------------------------------------------------------------

    @property
    def state(self) -> str:
        """The queue's state, from the worker and the top row: idle, running, pausing (drained,
        runs still in flight), stopping, or paused."""
        if self.worker is not None:
            return (STOPPING if self.worker.stopping else PAUSING if self.worker.draining
                    else RUNNING)
        return PAUSED if self.current is not None else IDLE

    def _set_controls(self) -> None:
        """The toggle's text, enabled state and tooltip, and the top row's mark, from
        ``state``."""
        s = self.state
        text, key = TOGGLE[s]
        self.toggle_button.setText(text)
        self.toggle_button.setEnabled(s in (RUNNING, PAUSED) or (s == IDLE and bool(
            self.queued())))
        set_tip(key, self.toggle_button)
        self._draw_queue()

    def toggle_clicked(self) -> None:
        """Start queue, Pause queue or Resume queue, by the state."""
        s = self.state
        if s == IDLE and self.queued():
            self.start(self._take_queued(0))
        elif s == RUNNING:
            self.worker.drain()
            self._set_controls()
            self._draw_progress()
        elif s == PAUSED:
            self.start(self.current)

    def start(self, b: Batch) -> None:
        """Run a batch as the queue's top row: the first waiting one, or the paused one."""
        self._pin(b)
        self.worker = BatchWorker(b, {}, self.launcher, self.cpus, self.mode)
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
        self.methods_button.setEnabled(False)
        self._set_controls()
        self.tick.start()
        self.worker.start()

    def _on_planned(self, p: estimate.Plan) -> None:
        self.plan = p
        self.progress.setRange(0, len(p.jobs))
        self.progress.setValue(0)
        self._draw_progress()
        self.save_queue()  # the running batch now names its runs

    def _on_started(self, job: Job) -> None:
        self.running[job.label] = (job, time.monotonic())
        self._draw_progress()

    def _on_blocks(self, job: Job, n: int, total: int) -> None:
        self.blocks[job.label] = (n, total)

    def _on_landed(self, r: Result, done: int, total: int) -> None:
        if r.waiting:  # left for Resume: it ran nowhere
            return
        self.running.pop(r.job.label, None)
        self.results.append(r)
        self.progress.setValue(len(self.results))
        self._draw_results()
        self._draw_progress()
        self.save_queue()

    def _on_finished(self, s: Summary) -> None:
        self.results = [r for r in s.results if not r.waiting]
        self._draw_results()
        out = self.worker.batch.out_dir if self.worker else self.out_dir
        self.status_label.setText(f"{self.current_title}: {s}; summary.csv in {out}")
        self.methods_button.setEnabled(bool(s.ok))

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(f"{self.current_title}: did not run: {message}")

    def _worker_done(self) -> None:
        """The batch's worker has ended: finished, drained or stopped. A finished batch leaves
        the queue and the next one starts; a drained one with runs left stays the top row,
        paused, holding exactly those; a stopped one leaves and the queue waits."""
        if self._closing:
            return
        was, w = self.state, self.worker
        self.tick.stop()
        self.running.clear()
        self.worker = None
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self._draw_running()
        left = [r.job.label for r in w.summary.waiting] if w.summary is not None else []
        if was == PAUSING and left:
            self._pin(dataclasses.replace(w.batch, remaining=tuple(left)))
            n = len(left)
            self.status_label.setText(
                f"{self.current_title}: paused, {n} run{'s' if n != 1 else ''} left; "
                f"{len(self.results)} landed, summary.csv in {w.batch.out_dir}")
        else:
            self._unpin()
            if was == RUNNING and self.queued():
                self.start(self._take_queued(0))
        self._set_controls()
        self.save_queue()
        self.update_estimate()

    def _left(self) -> tuple[str, ...] | None:
        """The running batch's runs not complete, by label: the ones not started and the ones
        stopped. None while the batch has not said what it runs (every run of it, then)."""
        w = self.worker
        if w.summary is not None:
            return tuple(r.job.label for r in w.summary.results if r.stopped or r.waiting)
        if self.plan is None:
            return w.batch.remaining
        landed = {r.job.label for r in self.results if not r.stopped}
        return tuple(j.label for j in self.plan.jobs if j.label not in landed)

    def _draw_progress(self) -> None:
        if self.worker is None:
            return
        elapsed = estimate.duration(time.monotonic() - self.batch_started)
        if self.plan is not None:
            n = len(self.plan.jobs)
            line = (f"{self.current_title}: {len(self.results)} of {n} "
                    f"run{'s' if n != 1 else ''} done, {elapsed} elapsed, estimate about "
                    f"{estimate.duration(self.plan.seconds)}")
            if self.worker.stopping:
                line += " (stopping)"
            elif self.worker.draining:
                k = len(self.running)
                line += (f"; pausing, waiting for {k} run{'s' if k != 1 else ''} in flight"
                         if k else "; pausing")
            self.status_label.setText(line)
        self._draw_running()
        self._draw_queue()

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
        self.queue.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue.model().rowsMoved.connect(self._rows_moved)
        self.queue.setMaximumHeight(120)
        set_tip("queue", self.queue)
        self.queue_total = QLabel()
        self.queue_total.setWordWrap(True)
        row = QHBoxLayout()
        self.add_batch_button = QPushButton("Add batch")
        set_tip("add_batch", self.add_batch_button)
        self.add_batch_button.setEnabled(False)
        self.add_batch_button.clicked.connect(self.add_batch_clicked)
        self.toggle_button = QPushButton()
        self.toggle_button.clicked.connect(self.toggle_clicked)
        self.remove_button = QPushButton("Remove batch")
        set_tip("remove_queued", self.remove_button)
        self.remove_button.clicked.connect(self.remove_clicked)
        row.addWidget(self.add_batch_button)
        row.addWidget(self.toggle_button)
        row.addWidget(self.remove_button)
        row.addStretch(1)
        lay.addWidget(self.queue)
        lay.addWidget(self.queue_total)
        lay.addLayout(row)
        self._set_controls()
        return box

    def queued(self) -> list[Batch]:
        """The waiting batches, in order: every row but the pinned top one."""
        return [self.queue.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.queue.count()) if not self.queue.item(i).data(PINNED)]

    def _estimate(self, b: Batch) -> float | None:
        """The batch's estimate, in seconds, of the runs it has left, from its input files
        as they are now; None when one cannot be read."""
        try:
            jobs = b.to_run()
            if not jobs:
                return 0.0
            p = b.plan(self.cpus, jobs=jobs, sizes={}, mode=self.mode)
        except (BatchError, ValueError, OSError):
            return None
        return None if any(w is None for w in p.walls) else p.seconds

    def _pin(self, b: Batch) -> None:
        """Make the batch the queue's top row, the running or paused one: bold, not draggable,
        and kept first (``_rows_moved``)."""
        if self.current is None:
            item = QListWidgetItem()
            item.setData(PINNED, True)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled
                          & ~Qt.ItemFlag.ItemIsDropEnabled)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.queue.insertItem(0, item)
        self.current = b
        item = self.queue.item(0)
        item.setData(Qt.ItemDataRole.UserRole, b)
        item.setData(SECONDS, self._estimate(b))
        self._draw_queue()

    def _unpin(self) -> None:
        if self.current is not None:
            self.queue.takeItem(0)
            self.current = None
            self._draw_queue()

    def _rows_moved(self, *_) -> None:
        """A drag has reordered the waiting rows; one dropped above the pinned row is put back
        under it, once the move has finished."""
        if self.current is not None and not self.queue.item(0).data(PINNED):
            QTimer.singleShot(0, self._repin)
        self.save_queue()

    def _repin(self) -> None:
        for i in range(self.queue.count()):
            if self.queue.item(i).data(PINNED):
                if i:
                    self.queue.insertItem(0, self.queue.takeItem(i))
                break

    @staticmethod
    def _describe(b: Batch) -> str:
        n = len(b.inputs)
        return (f"{b.title()}: {n} input{'s' if n != 1 else ''}, "
                f"{parameters.GAS[b.resolved_gas]}, {len(b.seeds)} "
                f"seed{'s' if len(b.seeds) != 1 else ''}, to {b.out_dir.name or b.out_dir}")

    def _time_left(self) -> float | None:
        """The top row's estimate: the running batch's plan less its elapsed time (negative
        once overdue), or the paused batch's remaining runs."""
        if self.worker is not None and self.plan is not None:
            if any(w is None for w in self.plan.walls):
                return None
            return self.plan.seconds - (time.monotonic() - self.batch_started)
        return self.queue.item(0).data(SECONDS)

    def _draw_queue(self) -> None:
        """Every row's text, with its estimate, and the total under the list."""
        total, unknown = 0.0, 0
        for i in range(self.queue.count()):
            item = self.queue.item(i)
            b = item.data(Qt.ItemDataRole.UserRole)
            if item.data(PINNED):
                s = self._time_left()
                if s is None:
                    when = "no estimate: an input cannot be read"
                elif s < 0:
                    when = "overdue"
                elif self.worker is not None:
                    when = f"about {estimate.duration(s)} left"
                else:
                    n = len(b.remaining) if b.remaining is not None else len(b.jobs())
                    when = (f"{n} run{'s' if n != 1 else ''} left, about "
                            f"{estimate.duration(s)}")
                item.setText(f"{MARK[self.state]}: {self._describe(b)}; {when}")
            else:
                s = item.data(SECONDS)
                when = ("no estimate: an input cannot be read" if s is None
                        else f"about {estimate.duration(s)}")
                item.setText(f"{self._describe(b)}; {when}")
            item.setToolTip(f"{item.text()}\n\nResults folder: {b.out_dir}")
            if s is None:
                unknown += 1
            else:
                total += max(0.0, s)
        if not self.queue.count():
            self.queue_total.setText("Nothing queued.")
            return
        text = f"In all, about {estimate.duration(total)}"
        if unknown:
            text += (f", not counting {unknown} batch{'es' if unknown != 1 else ''} with no "
                     "estimate")
        self.queue_total.setText(text + ".")

    def enqueue(self, b: Batch) -> None:
        """Append a batch to the queue, waiting; it never starts here."""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, b)
        item.setData(SECONDS, self._estimate(b))
        self.queue.addItem(item)
        self._set_controls()
        self.save_queue()

    def _take_queued(self, index: int) -> Batch:
        """Take the waiting batch at ``index`` (counted among the waiting rows) out."""
        row = index + (1 if self.current is not None else 0)
        b = self.queue.takeItem(row).data(Qt.ItemDataRole.UserRole)
        self.save_queue()
        return b

    def remove_clicked(self) -> None:
        """Remove batch: the selected waiting rows go; the top row asks, then its batch is
        stopped (running) or forgotten (paused), and the queue is left paused."""
        items = self.queue.selectedItems()
        for item in items:
            if not item.data(PINNED):
                self.queue.takeItem(self.queue.row(item))
        if any(item.data(PINNED) for item in items):
            self._remove_current()
        self._set_controls()
        self.save_queue()

    def _remove_current(self) -> None:
        s = self.state
        if s in (RUNNING, PAUSING):
            if QMessageBox.question(self, "Remove batch", "Stop this batch? Runs complete keep "
                                    "their results; runs in flight are killed and start over "
                                    "if it is run again.") != QMessageBox.StandardButton.Yes:
                return
            self.status_label.setText(f"{self.current_title}: stopping…")
            self.worker.stop()  # _worker_done takes it out and starts nothing
        elif s == PAUSED:
            b = self.current
            n = len(b.jobs())
            if b.remaining is not None and len(b.remaining) < n:
                done, left = n - len(b.remaining), len(b.remaining)
                if QMessageBox.question(
                        self, "Remove batch", f"{done} of the {n} runs of this batch are "
                        f"complete and keep their results. Remove it and forget the {left} "
                        f"run{'s' if left != 1 else ''} left?") \
                        != QMessageBox.StandardButton.Yes:
                    return
            self._unpin()

    def save_queue(self, *_) -> None:
        """Write the queue file: the running or paused batch first, holding its runs not
        complete (with none left, it is not written), then the waiting batches."""
        saved = []
        if self.current is not None:
            b = self.current
            if self.worker is not None:
                left = self._left()
                if left is not None:
                    b = dataclasses.replace(b, remaining=left) if left else None
            if b is not None:
                saved.append(b)
        try:
            batches.save(saved + self.queued(), self.store.queue_path)
        except OSError as e:
            self.status_label.setText(f"could not save the queue: {e}")

    def offer_saved_queue(self) -> None:
        """At launch: offer back the batches that were in the queue when the window last
        closed. They come back paused: the first is the top row, for Resume queue."""
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
        text = (f"{n} batch{'es were' if n != 1 else ' was'} in the queue when MOBCAL last "
                "closed. Put them back in the queue, paused?")
        if problems:
            text += "\n\nNot restored:\n" + "\n".join(problems)
        if QMessageBox.question(self, "Queue", text) == QMessageBox.StandardButton.Yes:
            self._pin(saved[0])
            for b in saved[1:]:
                self.enqueue(b)
            self._set_controls()
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
            cells = (ion.stem(r.input), parameters.GAS[r.gas], r.value("TM"), r.value("PA"),
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
            w.writerow((ion.stem(r.input), str(r.input), parameters.GAS[r.gas], r.value("TM"),
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
                                    "Runs in flight are killed; the batch keeps its runs not "
                                    "complete, and it and the queue are kept for next time.") \
                    != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self._closing = True  # the batch's end starts nothing queued
            w = self.worker
            w.stop()
            w.wait(30_000)
        self.save_queue()  # the running batch first, with what it has left (_left)
        self.store.geometry = self.saveGeometry()
        e.accept()
