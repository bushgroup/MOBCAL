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

Writes, all regenerated together:
  packaging/icon/mobcal.svg, mobcal-small.svg   the two drawings, the sources of the rest
  packaging/icon/mobcal.ico                     16-256 px; BMP entries to 128 px, PNG at 256
  packaging/icon/mobcal.icns                    16-1024 px, PNG entries, inset tile
  src/mobcal/app/icons/mobcal-<n>.png           16-512 px, the window's icon (QIcon)

Rasterized with Qt's SVG renderer (PySide6, a dependency already), then masked with the tile
shape, so nothing outside the tile survives whatever the renderer makes of ``clipPath``.
"""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mobcal.io.mfj import Mfj  # noqa: E402

ION = ROOT / "fortran" / "Choline.mfj"
ICON_DIR = ROOT / "packaging" / "icon"
APP_ICONS = ROOT / "src" / "mobcal" / "app" / "icons"

VDW = {1: 1.20, 12: 1.70, 14: 1.55, 16: 1.52}  # by the .mfj's mass key
ELEMENT = {1: "H", 12: "C", 14: "N", 16: "O"}

# Orientation (degrees about x, then y, then z, the last in the picture plane) and the box the
# ion's silhouette is fitted into, in the 100 x 100 canvas.
ROTATION = (80.0, 180.0, -30.0)
FIT = dict(cx=61.0, cy=63.0, w=66.0, h=54.0)

TILE = "#0D2240"
HEAVY, LIGHT, BACK, DEPTH = "#3B82D6", "#6FA8EC", "#1E4A86", 0.8
MISS, LONG_RANGE, SCATTERED = "#4E6F9C", "#5FB8D8", "#3FE0D0"

SCATTER_Y = 76.0  # height at which the scattered trajectory comes in
TURN = 16.0  # size of its turn
CLEARANCE = 0.3
LONG_RANGE_PATH = ((-5.0, 27.0), (34.0, 27.0), (72.0, 26.0), (90.0, 38.0), (104.0, 48.0))

VARIANTS = {"full": 5.5, "small": 8.0}  # stroke width
MAC_SCALE = 0.875  # 92 % x 0.875 = 80.5 %, 824 of 1024


def mix(a: str, b: str, t: float) -> str:
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(u + (v - u) * t):02x}" for u, v in zip(pa, pb, strict=True))


def project() -> list[dict]:
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
    s = min(FIT["w"] / (x1 - x0), FIT["h"] / (y1 - y0))
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for p in sorted(pts, key=lambda p: p["z"]):
        t = (z1 - p["z"]) / (z1 - z0)  # 0 at the front, 1 at the back
        out.append(dict(x=FIT["cx"] + (p["x"] - mx) * s, y=FIT["cy"] + (p["y"] - my) * s,
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


def scattered(ion, sw: float) -> tuple[str, dict]:
    """The bottom trajectory, slid right until it touches, and the atom it touches."""
    y0, d = SCATTER_Y, TURN
    shape = [(x, y0) for x in range(int(-5 - d), 1)]
    for k in range(51):
        t = k / 50
        shape.append(((1 - t) ** 2 * -d + t * t * (-d / 2), y0 + t * t * 0.866 * d))
        shape.append((-d / 2 - 24 * t, y0 + 0.866 * d + 41.6 * t))
    kx = 0.0
    while gap(shape, ion, sw, kx + 0.05)[0] > CLEARANCE and kx < 120:
        kx += 0.05
    ex, ey = kx - d / 2, y0 + 0.866 * d
    path = (f"M-5 {y0:g} H{kx - d:.2f} Q{kx:.2f} {y0:g} {ex:.2f} {ey:.2f} "
            f"L{ex - 24:.2f} {ey + 41.6:.2f}")
    return path, gap(shape, ion, sw, kx)[1]


def long_range_points() -> list[tuple[float, float]]:
    (ax, ay), (bx, by), (qx, qy), (cx, cy), (ex, ey) = LONG_RANGE_PATH
    pts = [(ax + (bx - ax) * k / 40, ay) for k in range(41)]
    for k in range(101):
        t = k / 100
        pts.append(((1 - t) ** 2 * bx + 2 * t * (1 - t) * qx + t * t * cx,
                    (1 - t) ** 2 * by + 2 * t * (1 - t) * qy + t * t * cy))
    pts += [(cx + (ex - cx) * k / 20, cy + (ey - cy) * k / 20) for k in range(21)]
    return pts


def svg(ion, sw: float, mac: bool = False) -> str:
    path, _ = scattered(ion, sw)
    (ax, ay), (bx, _), (qx, qy), (cx, cy), (ex, ey) = LONG_RANGE_PATH
    circles = "\n".join(f'    <circle cx="{c["x"]:.2f}" cy="{c["y"]:.2f}" r="{c["r"]:.2f}" '
                        f'fill="{c["fill"]}"/>' for c in ion)
    group = f' transform="translate(50 50) scale({MAC_SCALE}) translate(-50 -50)"' if mac else ""
    bent = f"M{ax:g} {ay:g} H{bx:g} Q{qx:g} {qy:g} {cx:g} {cy:g} L{ex:g} {ey:g}"
    canvas = 'viewBox="0 0 100 100" width="1024" height="1024"'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" {canvas}>
  <title>MOBCAL</title>
  <!-- Generated by tools/make_icon.py from fortran/Choline.mfj; change the script, not this. -->
  <defs><clipPath id="tile"><rect x="4" y="4" width="92" height="92" rx="21"/></clipPath></defs>
  <g{group}>
  <rect x="4" y="4" width="92" height="92" rx="21" fill="{TILE}"/>
  <g clip-path="url(#tile)">
{circles}
    <g fill="none" stroke-width="{sw:g}">
      <path d="M-5 15 H105" stroke="{MISS}"/>
      <path d="{bent}" stroke="{LONG_RANGE}"/>
      <path d="{path}" stroke="{SCATTERED}"/>
    </g>
  </g>
  </g>
</svg>
"""


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
    ion = project()

    for name, sw in VARIANTS.items():
        _, hit = scattered(ion, sw)
        lr, near = gap(long_range_points(), ion, sw)
        top, _ = gap([(x, 15.0) for x in range(-5, 106)], ion, sw)
        print(f"{name}: scattered trajectory touches {ELEMENT[hit['key']]}{hit['i'] + 1} "
              f"(atom {hit['i'] + 1} of {ION.name}); long-range trajectory's closest approach "
              f"{lr:.2f} units, to {ELEMENT[near['key']]}{near['i'] + 1}; missing one {top:.2f}")
        if lr <= 0 or top <= 0:
            raise SystemExit(f"{name}: a trajectory that should miss crosses the ion")

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    APP_ICONS.mkdir(parents=True, exist_ok=True)
    full, small = svg(ion, VARIANTS["full"]), svg(ion, VARIANTS["small"])
    full_mac, small_mac = svg(ion, VARIANTS["full"], True), svg(ion, VARIANTS["small"], True)
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

    for p in sorted([*ICON_DIR.iterdir(), *APP_ICONS.iterdir()]):
        print(f"  {p.relative_to(ROOT).as_posix():42s} {p.stat().st_size:>8,d} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
