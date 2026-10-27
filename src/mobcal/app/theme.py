"""The icon's colours in the window: the accent, the group-box titles and the toolbar's icons.

The palette is the icon's, and lives here: ``tools/make_icon.py`` imports it, so the two cannot
drift. Each colour has a job set by its contrast (WCAG 2.x, against the native window and base
colours of both schemes): ``BACK`` is text on a light window and ``LIGHT`` on a dark one; the
accent carries text too (the style writes ``HighlightedText`` on it: a checked tool button, a
dialog's default button), which ``HEAVY`` is too light for under white, so the light scheme's
accent is ``HEAVY`` shaded toward ``BACK`` as an atom halfway back is in the icon; ``HEAVY``
itself is the Run icon's, a graphic. The trajectory colours are never text. A test holds every
choice to its threshold.

Native styles honour a palette in part. Qt's ``windows11`` style takes check boxes, the progress
bar's fill and a selected row's marker from ``Accent``, draws a selected row as a faint fill
with its text unchanged, and uses ``Highlight`` for selected text in an edit; Fusion (Linux
without a platform theme) honours every role; macOS draws most controls from the system accent.
Group-box titles come from a proxy of the native style: windows11 takes them from the style
hint ``SH_GroupBox_TextLabelColor``, Fusion and macOS from ``WindowText`` in the box's own style
option, so the proxy sets both, and nothing inside the box changes colour. A style sheet on
``QGroupBox::title`` was not used: it hands the box to the style-sheet style, which moves its
margins. Everything is set from ``QStyleHints.colorScheme()`` and again
on ``colorSchemeChanged``.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleOptionGroupBox

# The icon's palette (tools/make_icon.py): the tile, the atoms (heavy, hydrogen, and the shade
# they fade to with depth), and the three trajectories.
TILE = "#0D2240"
HEAVY, LIGHT, BACK = "#3B82D6", "#6FA8EC", "#1E4A86"
MISS, LONG_RANGE, SCATTERED = "#4E6F9C", "#5FB8D8", "#3FE0D0"


def mix(a: str, b: str, t: float) -> str:
    """``a`` moved a fraction ``t`` of the way to ``b``, channel by channel, as the icon shades
    an atom by its depth."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(u + (v - u) * t):02x}" for u, v in zip(pa, pb, strict=True))


@dataclass(frozen=True)
class Scheme:
    accent: str  # Accent and Highlight: check boxes, the progress bar, a selected row's
    highlighted_text: str  # marker, a checked button, selected text; this written on it
    text: str  # coloured text: links and group-box titles
    run: str  # the toolbar's icons, against the window colour
    stop: str


LIGHT_SCHEME = Scheme(accent=mix(HEAVY, BACK, 0.4), highlighted_text="#FFFFFF", text=BACK,
                      run=HEAVY, stop=BACK)
DARK_SCHEME = Scheme(accent=LIGHT, highlighted_text="#000000", text=LIGHT, run=LIGHT,
                     stop=LONG_RANGE)


def is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def scheme() -> Scheme:
    return DARK_SCHEME if is_dark() else LIGHT_SCHEME


def palette(s: Scheme) -> QPalette:
    """A palette that sets only the scheme's roles, active and inactive; every other role, and
    the disabled group, stays the platform's."""
    p = QPalette()
    roles = ((QPalette.ColorRole.Accent, s.accent), (QPalette.ColorRole.Highlight, s.accent),
             (QPalette.ColorRole.HighlightedText, s.highlighted_text),
             (QPalette.ColorRole.Link, s.text), (QPalette.ColorRole.LinkVisited, s.text))
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, colour in roles:
            p.setColor(group, role, QColor(colour))
    return p


class Style(QProxyStyle):
    """The native style, with group-box titles in the scheme's text colour."""

    def styleHint(self, hint, option=None, widget=None, data=None):  # noqa: N802 -- Qt's name
        if hint == QStyle.StyleHint.SH_GroupBox_TextLabelColor:
            rgba = QColor(scheme().text).rgba()
            return rgba - (1 << 32) if rgba >= 1 << 31 else rgba  # a QRgb in a C int
        return super().styleHint(hint, option, widget, data)

    def drawComplexControl(self, control, option, painter, widget=None):  # noqa: N802
        if control == QStyle.ComplexControl.CC_GroupBox:
            option = QStyleOptionGroupBox(option)
            pal = QPalette(option.palette)
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                pal.setColor(group, QPalette.ColorRole.WindowText, QColor(scheme().text))
            option.palette = pal
        super().drawComplexControl(control, option, painter, widget)


def install(app: QApplication) -> None:
    """Put the scheme's colours on the application now and whenever the scheme changes."""
    app.setStyle(Style(app.style().name()))
    app.setPalette(palette(scheme()))
    QGuiApplication.styleHints().colorSchemeChanged.connect(
        lambda _: app.setPalette(palette(scheme())))


SIZES = (16, 20, 24, 32, 40, 48, 64)


def _icon(draw, colour: str) -> QIcon:
    icon = QIcon()
    for n in SIZES:
        pm = QPixmap(n, n)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(n / 16, n / 16)
        c = QColor(colour)
        p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(c)
        draw(p)
        p.end()
        icon.addPixmap(pm)
    return icon


def run_icon(s: Scheme) -> QIcon:
    """A play triangle, corners rounded, on a 16-unit grid."""
    return _icon(lambda p: p.drawPolygon([QPointF(4.5, 2.75), QPointF(13, 8),
                                          QPointF(4.5, 13.25)]), s.run)


def stop_icon(s: Scheme) -> QIcon:
    """A stop square, corners rounded, the triangle's height."""
    return _icon(lambda p: p.drawRoundedRect(QRectF(3.5, 3.5, 9, 9), 1.25, 1.25), s.stop)
