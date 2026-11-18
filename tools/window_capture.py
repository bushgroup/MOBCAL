"""A picture of the window during a real nitrogen batch, light and dark, for the README and guide.

    uv run tools/window_capture.py                 # run the batch, write the two pictures
    uv run tools/window_capture.py --plan          # fill the form and print the batch's plan only
    uv run tools/window_capture.py --out DIR --keep DIR

Opens the window as ``mobcal gui`` does (the theme installed, the native style, a throwaway
settings file) and drives it through its own slots: ``fortran/Choline.mfj`` and the ORCA and
Gaussian outputs of choline under ``tests/data/qm/`` are added to Inputs, with the charges the
window proposes; **MOBCAL 2012 with Philox (N2)** is chosen; the batch is added and the queue
started. The batch is real, run by the built nitrogen program. ``INTO_THIRD`` seconds after the
third run starts (by default one run at a time, each divided among the cores), the window is
rendered at 1280 logical pixels wide and its minimum height, at device pixel ratio 2, under the
light and then the dark colour scheme at the same moment, and the menu bar is cropped off the
top. Writes ``window-light.png`` and ``window-dark.png`` to ``--out`` (default ``docs/images``).

The batch runs in the window's default results folder, ``MOBCAL results`` in Documents, which
the picture shows; the script refuses to start if it exists, and moves it to ``--keep`` (default
``build/window-capture/<date>``) when the batch ends, so that the cross sections in the picture
can be checked against the result files. About 7 minutes on a 36-core workstation.

The picture is a ``QWidget.render`` into an image, not a screen grab, so it does not depend on
the scale of the screen, and the title bar, which the platform draws, is not in it. The loop
turns the event loop as ``exec()`` does, deleted widgets included: without that, the cell
widgets the Inputs table replaces survive and show over its first row.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

WIDTH = 1280  # logical pixels; the height is the window's minimum
DPR = 2
LANDED = 2  # runs complete when the picture is taken; the third is in flight
INTO_THIRD = 40  # seconds into the third run, so that it has counted some blocks
METHOD = "2012-philox-n2"
INPUTS = ("fortran/Choline.mfj", "tests/data/qm/orca/choline_sp/choline_sp.out",
          "tests/data/qm/gaussian/choline_2012_mk/choline_2012_mk.log")


def visible_rows(table) -> int:
    """Rows of a table wholly inside its viewport."""
    vp = table.viewport().height()
    return sum(1 for r in range(table.rowCount())
               if table.rowViewportPosition(r) >= 0
               and table.rowViewportPosition(r) + table.rowHeight(r) <= vp)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true", help="fill the form, print the plan, stop")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "images",
                    help="where the two pictures go (default docs/images)")
    ap.add_argument("--keep", type=Path, default=None,
                    help="where the batch's results folder is moved at the end "
                         "(default build/window-capture/<date>)")
    args = ap.parse_args(argv)

    from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt, QTimer
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtWidgets import QApplication

    import mobcal
    from mobcal import estimate
    from mobcal.app import APPLICATION, ORGANISATION, theme, window_icon
    from mobcal.app.store import Store
    from mobcal.app.window import MainWindow

    paths = [ROOT / p for p in INPUTS]
    for p in paths:
        if not p.is_file():
            raise SystemExit(f"missing input: {p}")
    keep = args.keep or ROOT / "build" / "window-capture" / dt.datetime.now().strftime(
        "%Y-%m-%d-%H%M")
    if keep.exists() and not args.plan:
        raise SystemExit(f"{keep} exists; give --keep a new folder")

    app = QApplication.instance() or QApplication(["window_capture"])
    app.setOrganizationName(ORGANISATION)
    app.setApplicationName(APPLICATION)
    app.setWindowIcon(window_icon())
    theme.install(app)
    hints = QGuiApplication.styleHints()

    def pump() -> None:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)

    def settle(n: int = 10) -> None:
        for _ in range(n):
            pump()

    hints.setColorScheme(Qt.ColorScheme.Light)
    settle()
    scratch = tempfile.TemporaryDirectory()
    store = Store(QSettings(str(Path(scratch.name) / "capture.ini"),
                            QSettings.Format.IniFormat), data_dir=Path(scratch.name))
    w = MainWindow(store)
    out = w.out_dir  # the window's default results folder
    if out.exists() and not args.plan:
        raise SystemExit(f"{out} exists; move it away first (the picture shows this folder)")
    w.resize(WIDTH, 1)  # the layout raises it to the minimum height
    w.show()
    settle()

    w.inputs.add_paths(paths)
    while w.inputs.busy:
        pump()
    w.method_combo.setCurrentIndex(w.method_combo.findData(METHOD))
    w._method_picked(w.method_combo.currentIndex())  # what choosing it in the list runs
    settle()
    problems = w.inputs.problems()
    if problems:
        raise SystemExit(f"inputs: {problems}")
    p = w.form_batch().plan(w.cpus, sizes=w.inputs.sizes(out), mode=w.mode)
    print(f"mobcal {mobcal.__version__}; {w.cpus} cores; window {w.width()} x {w.height()}")
    print(f"batch: {w.method_title()}: {estimate.describe(p)}")
    if args.plan:
        w.close()
        settle()
        return 0

    state = {"taken": False, "due": False}

    def take() -> None:
        if not w.running:
            print("nothing in flight when the picture was due; none written")
            return
        args.out.mkdir(parents=True, exist_ok=True)
        for scheme in (Qt.ColorScheme.Light, Qt.ColorScheme.Dark):
            hints.setColorScheme(scheme)
            settle(20)
            img = QImage(w.size() * DPR, QImage.Format.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(DPR)
            img.fill(0)
            w.render(img)
            menu = w.menuBar().height() * DPR
            img = img.copy(0, menu, img.width(), img.height() - menu)
            path = args.out / f"window-{hints.colorScheme().name.lower()}.png"
            img.save(str(path))
            print(f"wrote {path}: {img.width()} x {img.height()} px")
        hints.setColorScheme(Qt.ColorScheme.Light)
        settle()
        print(f"  status: {w.status_label.text()}")
        print(f"  in flight: {[w.running_list.item(i).text() for i in range(w.running_list.count())]}")
        print(f"  rows shown: inputs {visible_rows(w.inputs.table)} of "
              f"{w.inputs.table.rowCount()}, results {visible_rows(w.results_table)} of "
              f"{w.results_table.rowCount()}")
        state["taken"] = True

    def started(*_) -> None:
        # a landing is reported before the next run starts, so the start is the trigger
        if state["due"] or len(w.results) < LANDED:
            return
        state["due"] = True
        QTimer.singleShot(INTO_THIRD * 1000, take)

    w.add_batch_clicked()
    w.toggle_clicked()
    if w.worker is None:
        raise SystemExit("the queue did not start")
    w.worker.run_started.connect(lambda *_: QTimer.singleShot(0, started))
    while w.worker is not None or w.current is not None:
        pump()
        if w.worker is not None:
            w.worker.wait(50)
    settle()
    w.close()
    settle()
    keep.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(out), str(keep))
    print(f"results folder moved to {keep}")
    for r in sorted(keep.glob("*/*.result.json")):
        d = json.loads(r.read_text(encoding="utf-8"))
        tm = d["results"]["cross_sections"]["TM"]["value"]
        print(f"  {r.name}: {d['status']}, TM {tm} A^2, seed {d['seed']}, {d['seconds']} s")
    return 0 if state["taken"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
