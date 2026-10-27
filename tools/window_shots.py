"""Screenshots of the window and its About box, light and dark, on the platform this runs on.

    uv run tools/window_shots.py [OUT_DIR]

Opens the window as ``mobcal gui`` does (the theme installed, the native style), in a throwaway
settings folder, with ``fortran/Choline.mfj`` as an input so the form can make a batch, the
Advanced fold open and a row of the inputs selected; grabs it and the About box under each
colour scheme the platform takes, and writes ``window-<platform>-<scheme>.png`` and
``about-<platform>-<scheme>.png`` to OUT_DIR (default ``build/screenshots``). Nothing runs.
A platform that ignores ``setColorScheme`` (offscreen) gets one pair, named for the scheme it
reports. For recording what each native style does with the palette (``mobcal.app.theme``).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str]) -> int:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from mobcal import fortran
    from mobcal.app import APPLICATION, ORGANISATION, theme, window_icon
    from mobcal.app.store import Store
    from mobcal.app.window import MainWindow

    out = Path(argv[0]) if argv else ROOT / "build" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(["window_shots"])
    app.setOrganizationName(ORGANISATION)
    app.setApplicationName(APPLICATION)
    app.setWindowIcon(window_icon())
    theme.install(app)
    hints = QGuiApplication.styleHints()
    plat = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    done = set()
    with tempfile.TemporaryDirectory() as d:
        for scheme in (Qt.ColorScheme.Light, Qt.ColorScheme.Dark):
            hints.setColorScheme(scheme)
            app.processEvents()
            name = hints.colorScheme().name.lower()
            if name in done:
                continue
            done.add(name)
            w = MainWindow(Store(QSettings(str(Path(d) / "shots.ini"),
                                           QSettings.Format.IniFormat), data_dir=Path(d)))
            w.out_edit.setText(str(Path(d) / "results"))
            w.resize(1280, 820)
            w.show()
            w.inputs.add_paths([fortran.FORTRAN_DIR / "Choline.mfj"])
            while w.inputs.busy:
                app.processEvents()
            w.advanced_toggle.setChecked(True)
            w.inputs.table.selectRow(0)
            for _ in range(5):
                app.processEvents()
            w.grab().save(str(out / f"window-{plat}-{name}.png"))
            about = w.show_about()
            for _ in range(5):
                app.processEvents()
            about.grab().save(str(out / f"about-{plat}-{name}.png"))
            about.close()
            w.close()
            app.processEvents()
    style = app.style().baseStyle().name()  # theme.Style is a proxy of the native style
    print(f"{app.platformName()}, style {style}: {', '.join(sorted(done))} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
