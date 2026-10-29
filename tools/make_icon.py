"""Draw the MOBCAL icon from the choline input and write every file the packages use.

    uv run tools/make_icon.py

The picture is the trajectory method itself: three helium trajectories past a space-filling
choline cation, the 2012 test ion, projected from ``fortran/Choline.mfj`` at van der Waals
radii (Bondi: H 1.20, C 1.70, N 1.55, O 1.52 Å) and shaded by depth. The top trajectory misses,
the middle one bends in the long-range potential without reaching the surface, and the bottom
one enters low, is slid along x until it first touches an atom (0.3 units of clearance, so no
part of it crosses the ion), and leaves at 120°. The script prints which atom that is and the
middle trajectory's closest approach, so a change of orientation that alters either is seen.

Two drawings: the full one for 48 px and up, and one with heavier strokes for 16 to 32 px, where
5.5-unit lines are under a pixel. Each comes square-ish (the tile fills 92 % of the canvas, for
Windows, Linux and the window) and inset (80.5 %, Apple's icon grid) for the macOS bundle.

The banner is the same scene, full-bleed on the navy with no tile, for the repository's social
preview, the README's head, and talks: the ion near the right edge, the miss and the long-range
trajectory run in from the left edge, the scattered one slid to contact again in the wide frame,
and the wordmark MOBCAL on the open left between the long-range and scattered trajectories.
The icon is the 100 x 100 case of the same drawing (``Scene``), so its positions are the
banner's, placed and scaled; each canvas's contact atom and gaps are printed, and the drawing
refused if a missing trajectory crosses the ion or the wordmark comes within reach of either.
The wordmark is IBM Plex Sans SemiBold from ``packaging/fonts/`` (OFL), written as outlines, so
the SVG needs no installed font.

Writes, all regenerated together:
  packaging/icon/mobcal.svg, mobcal-small.svg   the two drawings, the sources of the rest
  packaging/icon/mobcal.ico                     16-256 px; BMP entries to 128 px, PNG at 256
  packaging/icon/mobcal.icns                    16-1024 px, PNG entries, inset tile
  src/mobcal/app/icons/mobcal-<n>.png           16-512 px, the window's icon (QIcon)
  packaging/banner/mobcal-banner.svg            2:1, and its PNGs at 1280x640 (the social
                                                preview; under GitHub's 1 MB) and 2560x1280
  packaging/banner/mobcal-banner-16x9.svg       16:9, composed for it, and its PNG at 1920x1080

Rasterized with Qt's SVG renderer (PySide6, a dependency already); the icon is then masked with
the tile shape, so nothing outside the tile survives whatever the renderer makes of ``clipPath``.
"""

from __future__ import annotations

import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mobcal.app.theme import (  # noqa: E402
    BACK,
    HEAVY,
    LIGHT,
    LONG_RANGE,
    MISS,
    SCATTERED,
    TILE,
    WORDMARK,
    mix,
)
from mobcal.io.mfj import Mfj  # noqa: E402

ION = ROOT / "fortran" / "Choline.mfj"
ICON_DIR = ROOT / "packaging" / "icon"
APP_ICONS = ROOT / "src" / "mobcal" / "app" / "icons"
BANNER_DIR = ROOT / "packaging" / "banner"
FONT_DIR = ROOT / "packaging" / "fonts"

VDW = {1: 1.20, 12: 1.70, 14: 1.55, 16: 1.52}  # by the .mfj's mass key
ELEMENT = {1: "H", 12: "C", 14: "N", 16: "O"}

# Orientation (degrees about x, then y, then z, the last in the picture plane) and the box the
# ion's silhouette is fitted into, in the 100 x 100 canvas.
ROTATION = (80.0, 180.0, -30.0)
FIT = dict(cx=61.0, cy=63.0, w=66.0, h=54.0)

# The palette (TILE, HEAVY, LIGHT, BACK, MISS, LONG_RANGE, SCATTERED, WORDMARK) and mix are
# mobcal.app.theme's, which the window uses too. DEPTH is how far the farthest atom is shaded
# toward BACK.
DEPTH = 0.8

MISS_Y = 15.0  # height of the missing trajectory
SCATTER_Y = 76.0  # height at which the scattered trajectory comes in
TURN = 16.0  # size of its turn
CLEARANCE = 0.3
LONG_RANGE_PATH = ((-5.0, 27.0), (34.0, 27.0), (72.0, 26.0), (90.0, 38.0), (104.0, 48.0))

MAC_SCALE = 0.875  # 92 % x 0.875 = 80.5 %, 824 of 1024


@dataclass(frozen=True)
class Scene:
    """A canvas ``width`` x ``height`` units with the icon's scene drawn on it at scale ``s``
    from (``ox``, ``oy``), strokes ``sw`` wide. Every position above is in the icon's 100 x 100
    frame; the trajectories' straight ends run on to 5 units past the canvas's edges."""

    width: float
    height: float
    sw: float
    ox: float = 0.0
    oy: float = 0.0
    s: float = 1.0

    def at(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + self.s * x, self.oy + self.s * y


ICONS = {"full": Scene(100, 100, 5.5), "small": Scene(100, 100, 8.0)}


def u(v: float) -> str:
    """A coordinate as the SVG gets it."""
    return f"{round(v, 2):g}"


def project(scene: Scene) -> list[dict]:
    """The ion's atoms as circles in the canvas, painted back to front."""
    atoms = Mfj.read(ION).sets[0]
    a, b, c = (math.radians(d) for d in ROTATION)
    pts = []
    for i, at in enumerate(atoms):
        y1 = at.y * math.cos(a) - at.z * math.sin(a)
        z1 = at.y * math.sin(a) + at.z * math.cos(a)
        x2 = at.x * math.cos(b) + z1 * math.sin(b)
        z2 = -at.x * math.sin(b) + z1 * math.cos(b)
        x3 = x2 * math.cos(c) - y1 * math.sin(c)
        y3 = x2 * math.sin(c) + y1 * math.cos(c)
        pts.append(dict(x=x3, y=-y3, z=z2, r=VDW[at.key], key=at.key, i=i))
    x0 = min(p["x"] - p["r"] for p in pts)
    x1 = max(p["x"] + p["r"] for p in pts)
    y0 = min(p["y"] - p["r"] for p in pts)
    y1 = max(p["y"] + p["r"] for p in pts)
    z0, z1 = min(p["z"] for p in pts), max(p["z"] for p in pts)
    cx, cy = scene.at(FIT["cx"], FIT["cy"])
    s = min(scene.s * FIT["w"] / (x1 - x0), scene.s * FIT["h"] / (y1 - y0))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for p in sorted(pts, key=lambda p: p["z"]):
        t = (z1 - p["z"]) / (z1 - z0)  # 0 at the front, 1 at the back
        out.append(dict(x=cx + (p["x"] - mx) * s, y=cy + (p["y"] - my) * s,
                        r=p["r"] * s, i=p["i"], key=p["key"],
                        fill=mix(LIGHT if p["key"] == 1 else HEAVY, BACK, t * DEPTH)))
    return out


def gap(points, ion, sw: float, dx: float = 0.0) -> tuple[float, dict]:
    """Smallest distance from a stroke of width ``sw`` through ``points`` (shifted ``dx``) to
    the ion's surface, and the atom it is to."""
    best = (math.inf, ion[0])
    for px, py in points:
        for c in ion:
            d = math.hypot(px + dx - c["x"], py - c["y"]) - c["r"] - sw / 2
            if d < best[0]:
                best = (d, c)
    return best


_SCATTERED: dict = {}


def scattered(ion, scene: Scene) -> tuple[str, list, dict]:
    """The bottom trajectory, slid right until it touches: its path, the points it is checked
    at, and the atom it touches. Its outgoing leg runs at least far enough to leave the canvas.
    The slide takes seconds on a wide canvas, so it is done once per ion and canvas."""
    key = (id(ion), scene)
    if key not in _SCATTERED:
        _SCATTERED[key] = _scattered(ion, scene)
    return _SCATTERED[key]


def _scattered(ion, scene: Scene) -> tuple[str, list, dict]:
    y0, d = scene.at(0, SCATTER_Y)[1], scene.s * TURN
    ey = y0 + 0.866 * d
    k = max(scene.s, (scene.height + 5 - ey) / 41.6)
    shape = [(x, y0) for x in range(int(-5 - d), 1)]
    for j in range(51):
        t = j / 50
        shape.append(((1 - t) ** 2 * -d + t * t * (-d / 2), y0 + t * t * 0.866 * d))
        shape.append((-d / 2 - 24 * k * t, ey + 41.6 * k * t))
    kx = 0.0
    while (gap(shape, ion, scene.sw, kx + 0.05)[0] > scene.s * CLEARANCE
           and kx < scene.width + 20):
        kx += 0.05
    ex = kx - d / 2
    path = (f"M-5 {u(y0)} H{kx - d:.2f} Q{kx:.2f} {u(y0)} {ex:.2f} {ey:.2f} "
            f"L{ex - 24 * k:.2f} {ey + 41.6 * k:.2f}")
    return path, [(x + kx, y) for x, y in shape], gap(shape, ion, scene.sw, kx)[1]


def long_range_path(scene: Scene) -> list[tuple[float, float]]:
    """The middle trajectory's five points: the icon's, placed, starting at the canvas's left
    bleed, and with its last leg carried on out of the canvas if it would end inside."""
    (ax, ay), *rest = LONG_RANGE_PATH
    pts = [(ax, scene.at(ax, ay)[1]), *(scene.at(x, y) for x, y in rest)]
    (cx, cy), (ex, ey) = pts[3:]
    if ex < scene.width + 4:
        pts[4] = (scene.width + 5, cy + (ey - cy) * (scene.width + 5 - cx) / (ex - cx))
    return pts


def long_range_points(scene: Scene) -> list[tuple[float, float]]:
    (ax, ay), (bx, by), (qx, qy), (cx, cy), (ex, ey) = long_range_path(scene)
    pts = [(ax + (bx - ax) * k / 40, ay) for k in range(41)]
    for k in range(101):
        t = k / 100
        pts.append(((1 - t) ** 2 * bx + 2 * t * (1 - t) * qx + t * t * cx,
                    (1 - t) ** 2 * by + 2 * t * (1 - t) * qy + t * t * cy))
    pts += [(cx + (ex - cx) * k / 20, cy + (ey - cy) * k / 20) for k in range(21)]
    return pts


def miss_points(scene: Scene) -> list[tuple[float, float]]:
    y = scene.at(0, MISS_Y)[1]
    return [(x, y) for x in range(-5, int(scene.width) + 6)]


def trajectories(ion, scene: Scene, indent: str = "      ") -> str:
    """The three trajectories' ``<path>`` elements."""
    path, _, _ = scattered(ion, scene)
    (ax, ay), (bx, _), (qx, qy), (cx, cy), (ex, ey) = long_range_path(scene)
    bent = f"M{u(ax)} {u(ay)} H{u(bx)} Q{u(qx)} {u(qy)} {u(cx)} {u(cy)} L{u(ex)} {u(ey)}"
    miss = f"M-5 {u(scene.at(0, MISS_Y)[1])} H{u(scene.width + 5)}"
    return (f'{indent}<path d="{miss}" stroke="{MISS}"/>\n'
            f'{indent}<path d="{bent}" stroke="{LONG_RANGE}"/>\n'
            f'{indent}<path d="{path}" stroke="{SCATTERED}"/>')


def circles(ion, indent: str = "    ") -> str:
    return "\n".join(f'{indent}<circle cx="{c["x"]:.2f}" cy="{c["y"]:.2f}" r="{c["r"]:.2f}" '
                     f'fill="{c["fill"]}"/>' for c in ion)


def check(name: str, ion, scene: Scene) -> list:
    """Print where the trajectories meet the ion, and refuse a drawing where one that should
    miss crosses it. Returns every trajectory's checked points, for the text's clearance."""
    _, shape, hit = scattered(ion, scene)
    bent = long_range_points(scene)
    lr, near = gap(bent, ion, scene.sw)
    top, _ = gap(miss_points(scene), ion, scene.sw)
    print(f"{name}: scattered trajectory touches {ELEMENT[hit['key']]}{hit['i'] + 1} "
          f"(atom {hit['i'] + 1} of {ION.name}); long-range trajectory's closest approach "
          f"{lr:.2f} units, to {ELEMENT[near['key']]}{near['i'] + 1}; missing one {top:.2f}")
    if lr <= 0 or top <= 0:
        raise SystemExit(f"{name}: a trajectory that should miss crosses the ion")
    return [*miss_points(scene), *bent, *shape]


def svg(ion, scene: Scene, mac: bool = False) -> str:
    group = f' transform="translate(50 50) scale({MAC_SCALE}) translate(-50 -50)"' if mac else ""
    canvas = 'viewBox="0 0 100 100" width="1024" height="1024"'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" {canvas}>
  <title>MOBCAL</title>
  <!-- Generated by tools/make_icon.py from fortran/Choline.mfj; change the script, not this. -->
  <defs><clipPath id="tile"><rect x="4" y="4" width="92" height="92" rx="21"/></clipPath></defs>
  <g{group}>
  <rect x="4" y="4" width="92" height="92" rx="21" fill="{TILE}"/>
  <g clip-path="url(#tile)">
{circles(ion)}
    <g fill="none" stroke-width="{scene.sw:g}">
{trajectories(ion, scene)}
    </g>
  </g>
  </g>
</svg>
"""


@dataclass(frozen=True)
class Banner:
    """A wide canvas: the scene on it, the wordmark's cap height, and the PNG widths it is
    written at."""

    scene: Scene
    cap: float
    pngs: tuple[int, ...]


BANNERS = {
    "2x1": Banner(Scene(200, 100, 3.5, ox=96), 16.0, (1280, 2560)),
    "16x9": Banner(Scene(160, 90, 3.0, ox=81.5, oy=7.5, s=0.75), 12.0, (1920,)),
}
FONT = FONT_DIR / "IBMPlexSans-SemiBold.ttf"
LEFT = 0.08  # the wordmark's left edge, as a fraction of the width
TRACKING = 0.02  # extra space between its capitals, in ems


def outline(text: str, font_file: Path, cap: float, x: float, baseline: float,
            tracking: float = 0.0) -> tuple[str, tuple[float, float, float, float]]:
    """``text`` set in the font file ``font_file`` as SVG path data, capitals ``cap`` units tall,
    its ink from ``x`` along ``baseline``; and the ink's box (left, top, right, bottom). The file
    is loaded alone and dropped after, and a face substituted for it is refused."""
    from PySide6.QtGui import (
        QFont,
        QFontDatabase,
        QFontMetricsF,
        QPainterPath,
        QRawFont,
        QTransform,
    )

    raw = QRawFont(str(font_file), 1000, QFont.HintingPreference.PreferNoHinting)
    fid = QFontDatabase.addApplicationFont(str(font_file))
    if fid < 0 or not raw.isValid():
        raise SystemExit(f"cannot load {font_file}")
    try:
        font = QFont(raw.familyName())
        font.setWeight(QFont.Weight(raw.weight()))
        font.setStyle(raw.style())
        font.setPixelSize(1000)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        font.setStyleStrategy(QFont.StyleStrategy.NoFontMerging)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking * 1000)
        if QRawFont.fromFont(font).fontTable("head") != raw.fontTable("head"):
            raise SystemExit(f"{font_file.name}: Qt chose another face for {raw.familyName()}")
        path = QPainterPath()
        path.addText(0, 0, font, text)
        k = cap / QFontMetricsF(font).capHeight()
    finally:
        QFontDatabase.removeApplicationFont(fid)
    box = path.boundingRect()
    path = QTransform().translate(x - box.left() * k, baseline).scale(k, k).map(path)
    box = path.boundingRect()

    kind = QPainterPath.ElementType
    d, i = [], 0
    while i < path.elementCount():
        e = path.elementAt(i)
        if e.type == kind.MoveToElement:
            d.append(("Z" if d else "") + f"M{u(e.x)} {u(e.y)}")
        elif e.type == kind.LineToElement:
            d.append(f"L{u(e.x)} {u(e.y)}")
        else:
            c, f = path.elementAt(i + 1), path.elementAt(i + 2)
            d.append(f"C{u(e.x)} {u(e.y)} {u(c.x)} {u(c.y)} {u(f.x)} {u(f.y)}")
            i += 2
        i += 1
    return "".join(d) + "Z", (box.left(), box.top(), box.right(), box.bottom())


def text_gap(box, points, ion, sw: float) -> float:
    """Smallest distance from the text's box to a trajectory's stroke or to the ion."""
    x0, y0, x1, y1 = box

    def to_box(px, py):
        return math.hypot(max(x0 - px, 0, px - x1), max(y0 - py, 0, py - y1))

    return min(min(to_box(*p) - sw / 2 for p in points),
               min(to_box(c["x"], c["y"]) - c["r"] for c in ion))


def banner_svg(name: str, banner: Banner, ion, points) -> str:
    """A banner: the scene full-bleed, and the wordmark on the left, centred in the band between
    the long-range trajectory and the scattered one; refused if it comes within reach of the ion
    or of ``points``, the trajectories' (from ``check``)."""
    sc = banner.scene
    top = sc.at(0, LONG_RANGE_PATH[0][1])[1] + sc.sw / 2
    bottom = sc.at(0, SCATTER_Y)[1] - sc.sw / 2
    words, box = outline("MOBCAL", FONT, banner.cap, LEFT * sc.width,
                         (top + bottom + banner.cap) / 2, TRACKING)
    clear = text_gap(box, points, ion, sc.sw)
    print(f"{name}: wordmark clears the trajectories and the ion by {clear:.2f} units")
    if clear <= 0:
        raise SystemExit(f"{name}: the wordmark runs into a trajectory or the ion")
    w, h = banner.pngs[0], round(banner.pngs[0] * sc.height / sc.width)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sc.width:g} {sc.height:g}" \
width="{w}" height="{h}">
  <title>MOBCAL</title>
  <!-- Generated by tools/make_icon.py from fortran/Choline.mfj; change the script, not this. -->
  <rect width="{sc.width:g}" height="{sc.height:g}" fill="{TILE}"/>
{circles(ion, "  ")}
  <g fill="none" stroke-width="{sc.sw:g}">
{trajectories(ion, sc, "    ")}
  </g>
  <path d="{words}" fill="{WORDMARK}"/>
</svg>
"""


def render_banner(svg_text: str, w: int, h: int):
    from PySide6.QtCore import QByteArray, QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(TILE))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg_text.encode("utf-8"))).render(p, QRectF(0, 0, w, h))
    p.end()
    return img


def render(svg_text: str, px: int, mac: bool = False):
    """Rasterize at ``px`` square, then keep only what lies inside the tile."""
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    def canvas():
        img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return img, p

    # The tile's shape over the whole canvas: composition acts only where the source paints,
    # so the mask must cover every pixel, transparent outside the tile.
    mask, p = canvas()
    k = px / 100 * (MAC_SCALE if mac else 1.0)
    off = (px - 100 * k) / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 255))
    p.drawRoundedRect(QRectF(off + 4 * k, off + 4 * k, 92 * k, 92 * k), 21 * k, 21 * k)
    p.end()

    img, p = canvas()
    QSvgRenderer(QByteArray(svg_text.encode("utf-8"))).render(p, QRectF(0, 0, px, px))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.drawImage(0, 0, mask)
    p.end()
    return img.convertToFormat(QImage.Format.Format_ARGB32)


def png_bytes(img) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(data)


def dib_bytes(img) -> bytes:
    """An ICO entry as a 32-bit DIB: BITMAPINFOHEADER, bottom-up BGRA rows, an all-zero AND
    mask (the alpha channel carries the shape)."""
    n = img.width()
    rows = [bytes(img.constScanLine(y))[:4 * n] for y in range(n)]  # BGRA on little-endian
    mask_row = b"\0" * (((n + 31) // 32) * 4)
    header = struct.pack("<IiiHHIIiiII", 40, n, 2 * n, 1, 32, 0, 0, 0, 0, 0, 0)
    return header + b"".join(reversed(rows)) + mask_row * n


def write_ico(path: Path, images: dict[int, object]) -> None:
    entries = [(n, png_bytes(img) if n >= 256 else dib_bytes(img))
               for n, img in sorted(images.items())]
    out = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    for n, data in entries:
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(out + b"".join(data for _, data in entries))


# icns entry types holding PNG data, by pixel size; 2x types share a size with a 1x one.
ICNS_TYPES = [(b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"ic12", 64), (b"ic07", 128),
              (b"ic13", 256), (b"ic08", 256), (b"ic14", 512), (b"ic09", 512), (b"ic10", 1024)]


def write_icns(path: Path, images: dict[int, object]) -> None:
    body = b""
    for kind, n in ICNS_TYPES:
        data = png_bytes(images[n])
        body += kind + struct.pack(">I", 8 + len(data)) + data
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.instance() or QGuiApplication(["make_icon"])
    ion = project(ICONS["full"])
    for name, scene in ICONS.items():
        check(name, ion, scene)

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    APP_ICONS.mkdir(parents=True, exist_ok=True)
    full, small = svg(ion, ICONS["full"]), svg(ion, ICONS["small"])
    full_mac, small_mac = svg(ion, ICONS["full"], True), svg(ion, ICONS["small"], True)
    for p, text in ((ICON_DIR / "mobcal.svg", full), (ICON_DIR / "mobcal-small.svg", small)):
        p.write_text(text, encoding="utf-8", newline="\n")

    def square(n):
        return render(small if n <= 32 else full, n)

    def inset(n):
        return render(small_mac if n <= 32 else full_mac, n, mac=True)

    write_ico(ICON_DIR / "mobcal.ico", {n: square(n) for n in (16, 24, 32, 48, 64, 128, 256)})
    write_icns(ICON_DIR / "mobcal.icns",
               {n: inset(n) for n in sorted({n for _, n in ICNS_TYPES})})
    for old in APP_ICONS.glob("mobcal-*.png"):
        old.unlink()
    for n in (16, 24, 32, 48, 64, 128, 256, 512):
        (APP_ICONS / f"mobcal-{n}.png").write_bytes(png_bytes(square(n)))

    BANNER_DIR.mkdir(parents=True, exist_ok=True)
    for old in BANNER_DIR.glob("mobcal-banner*"):
        old.unlink()
    for key, banner in BANNERS.items():
        sc = banner.scene
        ion = project(sc)
        text = banner_svg(f"banner {key}", banner, ion, check(f"banner {key}", ion, sc))
        stem = "mobcal-banner" + ("" if key == "2x1" else f"-{key}")
        (BANNER_DIR / f"{stem}.svg").write_text(text, encoding="utf-8", newline="\n")
        for w in banner.pngs:
            h = round(w * sc.height / sc.width)
            (BANNER_DIR / f"{stem}-{w}x{h}.png").write_bytes(png_bytes(render_banner(text, w, h)))

    for p in sorted([*ICON_DIR.iterdir(), *APP_ICONS.iterdir(), *BANNER_DIR.iterdir()]):
        print(f"  {p.relative_to(ROOT).as_posix():54s} {p.stat().st_size:>8,d} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
