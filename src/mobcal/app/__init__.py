"""The window: ``mobcal gui``, a PySide6 client of the same driver the command line uses.

The only Qt-importing package (``tools/check_public.py`` checks). Everything a batch is and does
lives under the seam: the methods (``mobcal.methods``), the batch and the results folder
(``mobcal.batch``), the allocation and the estimate (``mobcal.estimate``), the runs
(``mobcal.run``). The window is a form that makes a ``Batch``, a queue that holds them (saved
between launches), a worker thread that hands one to ``run_many`` and reports back through
signals, and a table of what came back. Nothing runs or blocks on the UI thread: the runs are
the driver's subprocesses, supervised from the worker thread, and reading an input (cclib for
an ORCA output) happens on a thread pool.

    uv run mobcal gui
"""

from __future__ import annotations

import ctypes.util
import html
import os
import sys
from pathlib import Path

ORGANISATION = "bushgroup"
APPLICATION = "MOBCAL"
# The icon at each size tools/make_icon.py renders (16 to 512 px); the bundle carries them here.
ICONS = Path(__file__).resolve().parent / "icons"


def tip(text: str) -> str:
    """A tooltip from ``mobcal.options``' plain text, as rich text: Qt wraps a rich-text
    tooltip at a readable width and draws a plain one on a single line."""
    return f"<qt>{html.escape(text, quote=False)}</qt>"


def missing_platform_library() -> str | None:
    """On Linux, the one host library Qt >= 6.5's xcb plugin needs that a desktop may lack,
    named the way the distributions package it, or None when it is there or not needed."""
    if not sys.platform.startswith("linux"):
        return None
    if os.environ.get("QT_QPA_PLATFORM", "xcb") not in ("xcb", ""):
        return None
    if ctypes.util.find_library("xcb-cursor"):
        return None
    if getattr(sys, "frozen", False):  # the bundle carries its own copy beside Qt's
        base = os.path.dirname(sys.executable)
        for _, _, files in os.walk(base):
            if any(f.startswith("libxcb-cursor.so") for f in files):
                return None
    return "libxcb-cursor0 (Debian, Ubuntu) or xcb-util-cursor (Fedora, Arch)"


def main(argv: list[str] | None = None, check: bool = False) -> int:
    """Open the window and run until it closes. With ``check``, open it, let it draw, close
    it and return 0: the installers' test that the window starts on a clean machine."""
    lib = missing_platform_library()
    if lib:
        print(f"error: the window needs {lib}, which Qt's X11 platform plugin loads; install it "
              "with the system's package manager, or run calculations with `mobcal run`",
              file=sys.stderr)
        return 2
    from PySide6.QtWidgets import QApplication

    from mobcal.app import theme
    from mobcal.app.window import MainWindow

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName(ORGANISATION)
    app.setApplicationName(APPLICATION)
    theme.install(app)
    icon = window_icon()
    app.setWindowIcon(icon)
    if check:  # in a folder of its own, so it never touches the user's settings or queue
        if not icon.availableSizes():
            print(f"error: no window icon in {ICONS}", file=sys.stderr)
            return 1
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QSettings, QTimer

        from mobcal.app.store import Store
        with tempfile.TemporaryDirectory() as d:
            w = MainWindow(Store(QSettings(str(Path(d) / "check.ini"),
                                           QSettings.Format.IniFormat), data_dir=Path(d)))
            w.show()
            QTimer.singleShot(500, w.close)
            rc = app.exec()
        print(f"window opened and closed on {app.platformName()}, Qt {qt_version()}, icon at "
              f"{len(icon.availableSizes())} sizes")
        return rc
    w = MainWindow()
    w.show()
    w.offer_saved_queue()
    return app.exec()


def window_icon():
    """The window's and taskbar's icon, one QIcon holding every size there is."""
    from PySide6.QtGui import QIcon

    icon = QIcon()
    for png in sorted(ICONS.glob("mobcal-*.png")):
        icon.addFile(str(png))
    return icon


def qt_version() -> str:
    from PySide6.QtCore import qVersion
    return qVersion()
