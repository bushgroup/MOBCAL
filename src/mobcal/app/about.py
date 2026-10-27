"""Help ▸ About MOBCAL: what the program computes, what to cite, the licence, the funding, and the
versions this window is running.

The citations are ``mobcal.methods.REFERENCES``, the source the methods text cites from, never
restated here. The programs are named only when ``mobcal.fortran.verify_binaries`` finds them
not to be the files recorded when they were built; ``mobcal self-check`` says where they are.
"""

from __future__ import annotations

import html
import platform

import PySide6
from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QVBoxLayout,
)

import mobcal
from mobcal import fortran, methods
from mobcal.app import window_icon

CITE = ("mesleh1996", "shvartsburg1996", "kim2008", "campuzano2012")
RELEASES = "https://github.com/bushgroup/"


def programs() -> str:
    """Nothing when the Fortran programs check against their pins; otherwise a paragraph
    saying where they are and what fails, as rich text."""
    d = fortran.binary_dir()
    problems = fortran.verify_binaries(d)
    if not problems:
        return ""
    return (f"<p>The helium and nitrogen programs in {html.escape(str(d))} do not check: "
            + html.escape("; ".join(problems)) + ".</p>")


def text() -> str:
    """The About box's body, as rich text."""
    e = html.escape
    refs = "".join(f"<li>{e(methods.REFERENCES[k])}</li>" for k in CITE)

    def link(name: str) -> str:
        return f'<a href="{RELEASES}{name}">bushgroup/{name}</a>'

    return (
        f"<h3>MOBCAL {e(mobcal.__version__)}</h3>"
        "<p>MOBCAL calculates the collision cross sections of ions in helium and nitrogen by "
        "the trajectory method, and in helium also by the projection approximation and the "
        "exact hard-sphere scattering model.</p>"
        f"<p>Research that uses MOBCAL should cite:</p><ol>{refs}</ol>"
        f"<p>The 2012 release is kept, exactly as published, at {link('MOBCAL-2012')}, and "
        "the Jarrold group's 2000 helium release, from which the 2012 helium program was made, "
        f"as distributed at {link('MOBCAL-2000')}.</p>"
        "<p>MOBCAL is free software under the GNU General Public License, version 3. The new "
        "work in this version is copyright University of Washington. Source: "
        f'<a href="{methods.REPOSITORY}">{e(methods.REPOSITORY)}</a>.</p>'
        "<p>This work is supported by the US National Science Foundation (CHE-2603156) and "
        "the ACS Petroleum Research Fund (68949-ND6).</p>"
        f"<p>Python {e(platform.python_version())}, Qt {e(qVersion())}, PySide6 "
        f"{e(PySide6.__version__)}.</p>{programs()}")


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About MOBCAL")
        icon = QLabel()
        icon.setPixmap(window_icon().pixmap(64, 64))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.body = QLabel(text())
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setOpenExternalLinks(True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.body.setFixedWidth(560)
        row = QHBoxLayout()
        row.addWidget(icon)
        row.addSpacing(12)
        row.addWidget(self.body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(buttons)
        # Sized from the label's height for its width: a dialog sized from its size hint cuts
        # wrapped rich text short where the fonts differ (seen on Linux).
        lay.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
