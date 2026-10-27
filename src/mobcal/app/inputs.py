"""The inputs: ``.mfj`` files, or ORCA outputs and ``.xyz`` files the window imports.

Every file is read on the thread pool as it is added: an ``.mfj`` for its atom and set counts
(the estimate's), anything else through ``mobcal.io.structure.read`` (cclib for an ORCA output,
whose first import takes seconds). An import's row shows its charge choice: CHELPG preselected
when the file holds it, otherwise nothing until the user picks, and ``uniform`` (Q/N, written
as ``calc``) offered last and never preselected. An ``.xyz`` asks for the ion's net charge. At
Run the import is written as ``mobcal import`` writes it, ``.mfj`` and ``.import.json``, into
``imported/`` in the results folder, so the study folder holds what was run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mobcal.io import structure
from mobcal.io.mfj import Mfj, MfjError

PRESELECT = "chelpg"
IMPORTED = "imported"
FILTER = ("Structures (*.mfj *.xyz *.out *.log);;MOBCAL inputs (*.mfj);;"
          "ORCA outputs (*.out *.log);;XYZ files (*.xyz);;All files (*)")
COLUMNS = ("File", "Atoms", "Sets", "Charges", "Net charge", "Status")


@dataclass
class Input:
    path: Path
    kind: str  # "mfj", or "import" for an ORCA output or an .xyz
    state: str = "reading"  # reading | ready | error
    error: str = ""
    atoms: int | None = None
    sets: int | None = None
    structure: structure.Structure | None = field(default=None, repr=False)
    charges: str | None = None  # an import's choice
    net_charge: int | None = None  # an .xyz's, given by the user

    @property
    def needs_net_charge(self) -> bool:
        return self.structure is not None and self.structure.net_charge is None

    def problem(self) -> str:
        """What stops this input from running, or empty."""
        if self.state == "reading":
            return f"{self.path.name} is still being read"
        if self.state == "error":
            return f"{self.path.name}: {self.error}"
        if self.kind == "import" and self.charges is None:
            return f"{self.path.name}: choose its charges"
        if self.kind == "import" and self.needs_net_charge and self.net_charge is None:
            return f"{self.path.name}: give the ion's net charge"
        return ""

    def mfj_path(self, out_dir: Path) -> Path:
        """The file the run reads: the input itself, or where its import is written."""
        if self.kind == "mfj":
            return self.path
        return Path(out_dir) / IMPORTED / f"{self.path.stem}_{self.charges}.mfj"

    def write(self, out_dir: Path, gases: tuple[str, ...]) -> Path:
        """Write an import's ``.mfj`` and record (replacing an earlier one, which is the same
        source's same choice); an ``.mfj`` is used where it is. Raises StructureError."""
        if self.kind == "mfj":
            return self.path
        imp = structure.convert(self.structure, self.charges, self.net_charge, gases)
        out = self.mfj_path(out_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        mfj, _ = structure.write(imp, out, overwrite=True)
        return mfj


class _Signals(QObject):
    read = Signal(str, object, str)  # path, Mfj or Structure (None on error), error


class _Read(QRunnable):
    def __init__(self, path: Path, kind: str, signals: _Signals) -> None:
        super().__init__()
        self.path, self.kind, self.signals = path, kind, signals

    def run(self) -> None:
        try:
            got = Mfj.read(self.path) if self.kind == "mfj" else structure.read(self.path)
            self.signals.read.emit(str(self.path), got, "")
        except (OSError, MfjError, structure.StructureError) as e:
            self.signals.read.emit(str(self.path), None, str(e))
        except Exception as e:  # cclib on a file it does not expect: shown, not lost
            self.signals.read.emit(str(self.path), None, f"{type(e).__name__}: {e}")


class InputsPanel(QWidget):
    changed = Signal()
    browse_dir_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self.items: list[Input] = []
        self.start_dir = ""
        self._pool = pool or QThreadPool.globalInstance()
        self._signals = _Signals()
        self._signals.read.connect(self._on_read)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        for c in range(len(COLUMNS) - 1):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        h.setMinimumSectionSize(48)
        self.add_button = QPushButton("Add files…")
        self.remove_button = QPushButton("Remove")
        self.add_button.clicked.connect(self._browse)
        self.remove_button.clicked.connect(self.remove_selected)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table)
        lay.addLayout(buttons)
        self.setAcceptDrops(True)

    # --- adding and removing -------------------------------------------------------------

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add structures", self.start_dir, FILTER)
        if paths:
            self.start_dir = str(Path(paths[0]).parent)
            self.browse_dir_changed.emit(self.start_dir)
            self.add_paths([Path(p) for p in paths])

    def dragEnterEvent(self, e) -> None:  # noqa: N802 -- Qt's name
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802 -- Qt's name
        self.add_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    def add_paths(self, paths: list[Path]) -> None:
        for p in paths:
            p = p.resolve()
            if any(i.path == p for i in self.items):
                continue
            kind = "mfj" if p.suffix.lower() == ".mfj" else "import"
            self.items.append(Input(p, kind))
            self._pool.start(_Read(p, kind, self._signals))
        self._redraw()
        self.changed.emit()

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.items[r]
        self._redraw()
        self.changed.emit()

    def clear(self) -> None:
        self.items.clear()
        self._redraw()
        self.changed.emit()

    def _on_read(self, path: str, got: object, error: str) -> None:
        item = next((i for i in self.items if str(i.path) == path), None)
        if item is None:  # removed while it was read
            return
        if got is None:
            item.state, item.error = "error", error
        elif isinstance(got, Mfj):
            item.state, item.atoms, item.sets = "ready", got.atoms, got.coordinate_sets
        else:
            item.state, item.structure = "ready", got
            item.atoms, item.sets = len(got.symbols), 1
            if PRESELECT in got.charges:
                item.charges = PRESELECT
        self._redraw()
        self.changed.emit()

    # --- what the window asks -------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return any(i.state == "reading" for i in self.items)

    def problems(self) -> list[str]:
        return [p for p in (i.problem() for i in self.items) if p]

    def sizes(self, out_dir: Path) -> dict:
        """(atoms, sets) by the path each run will read, for the estimate."""
        return {i.mfj_path(out_dir): (i.atoms, i.sets) for i in self.items
                if i.state == "ready" and i.atoms and (i.kind == "mfj" or i.charges)}

    # --- drawing --------------------------------------------------------------------------

    def _redraw(self) -> None:
        self.table.setRowCount(len(self.items))
        for r, item in enumerate(self.items):
            name = QTableWidgetItem(item.path.name)
            name.setToolTip(str(item.path))
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, QTableWidgetItem("" if item.atoms is None else
                                                      f"{item.atoms:,}"))
            self.table.setItem(r, 2, QTableWidgetItem("" if item.sets is None else
                                                      str(item.sets)))
            self.table.setCellWidget(r, 3, self._charges_widget(item))
            self.table.setCellWidget(r, 4, self._net_charge_widget(item))
            status = {"reading": "reading…", "error": item.error}.get(item.state, "") \
                or item.problem().split(": ", 1)[-1] or "ready"
            cell = QTableWidgetItem(status)
            cell.setToolTip(item.error or item.problem())
            self.table.setItem(r, 5, cell)

    def _charges_widget(self, item: Input) -> QWidget | None:
        if item.kind == "mfj" or item.structure is None:
            return None
        combo = QComboBox()
        combo.setPlaceholderText("choose…")
        for key in item.structure.choices:
            label = f"{key} (Q/N on every atom)" if key == structure.UNIFORM else key
            combo.addItem(label, key)
        combo.setCurrentIndex(-1 if item.charges is None else combo.findData(item.charges))
        combo.setToolTip(item.structure.offer())

        def chosen(i: int) -> None:
            item.charges = combo.itemData(i) if i >= 0 else None
            self.table.item(self.items.index(item), 5).setText(
                item.problem().split(": ", 1)[-1] or "ready")
            self.changed.emit()
        combo.currentIndexChanged.connect(chosen)
        return combo

    def _net_charge_widget(self, item: Input) -> QWidget | None:
        if item.structure is None:
            return None
        spin = QSpinBox()
        spin.setRange(-99, 99)
        if not item.needs_net_charge:
            spin.setValue(item.structure.net_charge)
            spin.setEnabled(False)
            spin.setToolTip("the charge the output was computed at")
            return spin
        spin.setSpecialValueText("give…")
        spin.setRange(-100, 99)  # -100 is the "not given" value the special text shows
        spin.setValue(-100 if item.net_charge is None else item.net_charge)

        def given(v: int) -> None:
            item.net_charge = None if v == -100 else v
            self.table.item(self.items.index(item), 5).setText(
                item.problem().split(": ", 1)[-1] or "ready")
            self.changed.emit()
        spin.valueChanged.connect(given)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        return spin
