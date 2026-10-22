"""Build the ozure brand: a small kawaii jellyfish next to the name.

A horizontal lockup — the creature on the left, the wordmark on the right — so
it fits a README header, a repo avatar and a terminal title bar without a big
vertical block.

One geometry description, two renderers (SVG + Pillow), transparent background
everywhere so it can sit on any page:

* logo           — mascot + wordmark, for light backgrounds
* logo-dark      — same, name in cream, for dark backgrounds
* icon           — the mascot alone, filling a square (avatar)
* wordmark       — just the name, for tight spaces such as the demo title bar

    python tools/build_brand.py

Quicksand (SIL OFL) is downloaded into .build/ and instanced on first run; only
the generated SVG/PNGs are committed.
"""

from __future__ import annotations

import math
import urllib.request
from pathlib import Path
from typing import Any

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".build"
ASSETS = ROOT / "assets"

WORD = "ozure"
WEIGHT = 600
TRACKING = 8  # font units between letters
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/quicksand/Quicksand%5Bwght%5D.ttf"

# Pastel, low-noise palette: one pink, a deeper pink for details, cream, ink.
PETAL = "#f2a3b6"
PETAL_DEEP = "#e58ea4"
BLUSH = "#fce4ea"
CREAM = "#fff9f7"
INK = "#2c2f38"
WHITE = "#ffffff"

# Horizontal layout: a small jellyfish, then the name.
NAME_SIZE = 92
NAME_BASELINE = 128
JELLY_HEIGHT = 138
NAME_GAP = 30
MARGIN = 26

Shape = dict[str, Any]


def rgb(hex_colour: str) -> tuple[int, int, int, int]:
    value = hex_colour.lstrip("#")
    return (*[int(value[index : index + 2], 16) for index in (0, 2, 4)], 255)


# --------------------------------------------------------------------------
# Shape builders
# --------------------------------------------------------------------------


def blob(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    rotation: float = 0.0,
    wobble: float = 0.0,
    phase: float = 0.0,
    count: int = 96,
) -> list[tuple[float, float]]:
    """A soft, slightly irregular ellipse: the yuru-kyara building block."""
    points = []
    for index in range(count):
        t = 2 * math.pi * index / count
        radius = (
            1 + wobble * math.sin(3 * t + phase) + wobble * 0.45 * math.sin(5 * t + phase * 1.7)
        )
        x = rx * radius * math.cos(t)
        y = ry * radius * math.sin(t)
        cos_r, sin_r = math.cos(rotation), math.sin(rotation)
        points.append((cx + x * cos_r - y * sin_r, cy + x * sin_r + y * cos_r))
    return points


def star(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    """Four-point sparkle, the kawaii kind."""
    points = []
    for index in range(8):
        angle = math.radians(index * 45 - 90)
        span = radius if index % 2 == 0 else radius * 0.3
        points.append((cx + span * math.cos(angle), cy + span * math.sin(angle)))
    return points


def catmull(control: list[tuple[float, float]], samples: int = 24) -> list[tuple[float, float]]:
    """Smooth curve through the control points (Catmull-Rom)."""
    pts = [control[0], *control, control[-1]]
    out: list[tuple[float, float]] = []
    for index in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[index : index + 4]
        for step in range(samples):
            t = step / samples
            t2, t3 = t * t, t * t * t
            out.append(
                (
                    0.5
                    * (
                        2 * p1[0]
                        + (-p0[0] + p2[0]) * t
                        + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                        + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                    ),
                    0.5
                    * (
                        2 * p1[1]
                        + (-p0[1] + p2[1]) * t
                        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                        + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                    ),
                )
            )
    out.append(control[-1])
    return out


def tentacle(
    control: list[tuple[float, float]], amplitude: float, waves: float, samples: int = 24
) -> list[tuple[float, float]]:
    """A smooth path with a lateral sine wave: what makes a tentacle read."""
    centre = catmull(control, samples)
    total = max(1, len(centre) - 1)
    return [
        (x + amplitude * math.sin(2 * math.pi * waves * index / total), y)
        for index, (x, y) in enumerate(centre)
    ]


def bell_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    *,
    scallops: int = 5,
    depth: float = 0.16,
    amplitude: float = 0.13,
    count: int = 140,
) -> list[tuple[float, float]]:
    """A jellyfish bell: smooth dome on top, ruffled hem at the bottom."""
    points = []
    for index in range(count + 1):
        theta = math.pi + math.pi * index / count
        points.append((cx + rx * math.cos(theta), cy + ry * math.sin(theta)))
    for index in range(count + 1):
        t = index / count
        points.append(
            (
                cx + rx - 2 * rx * t,
                cy + ry * depth + ry * amplitude * abs(math.sin(scallops * math.pi * t)),
            )
        )
    return points


def jelly_shapes(
    *,
    body: str = PETAL,
    tentacle_colour: str = PETAL_DEEP,
    spot: str = BLUSH,
    with_sparkles: bool = False,
    with_tentacles: bool = True,
) -> list[Shape]:
    """A small, faceless kawaii jellyfish, drawn in a 300x330 box.

    Simple on purpose: a spotted bell with a ruffled hem and four short, wavy
    tentacles. No face, no wrapping loop — in a horizontal lockup the creature
    sits next to the name, not around it.
    """
    shapes: list[Shape] = []

    if with_tentacles:
        for x, length, colour in (
            (108, 168, tentacle_colour),
            (140, 205, body),
            (168, 205, body),
            (200, 168, tentacle_colour),
        ):
            shapes.append(
                {
                    "type": "polyline",
                    "points": tentacle(
                        [
                            (x, 112),
                            (x + (x - 150) * 0.05, 112 + length * 0.5),
                            (x + (x - 150) * 0.1, 112 + length),
                        ],
                        9,
                        2.4,
                    ),
                    "stroke": colour,
                    "width": 11,
                }
            )

    shapes.append({"type": "polygon", "points": bell_points(150, 96, 128, 88), "fill": body})
    for sx, sy, radius in ((112, 68, 12), (152, 50, 8), (194, 72, 13), (130, 96, 6), (176, 98, 7)):
        shapes.append({"type": "circle", "c": (sx, sy), "r": radius, "fill": spot})

    if with_sparkles:
        shapes.append({"type": "polygon", "points": star(268, 40, 11), "fill": tentacle_colour})
    return shapes


def place_shapes(shapes: list[Shape], scale: float, left: float, top: float) -> list[Shape]:
    """Scale the drawing and move its top-left corner to (left, top)."""
    x0, y0, _, _ = bounds_of(shapes)
    placed = []
    for shape in shapes:
        clone = dict(shape)
        if clone["type"] == "circle":
            clone["c"] = (
                left + (clone["c"][0] - x0) * scale,
                top + (clone["c"][1] - y0) * scale,
            )
            clone["r"] = clone["r"] * scale
        elif clone["type"] == "rrect":
            bx0, by0, bx1, by1 = clone["box"]
            clone["box"] = (
                left + (bx0 - x0) * scale,
                top + (by0 - y0) * scale,
                left + (bx1 - x0) * scale,
                top + (by1 - y0) * scale,
            )
            clone["r"] = clone["r"] * scale
        else:
            clone["points"] = [
                (left + (x - x0) * scale, top + (y - y0) * scale) for x, y in clone["points"]
            ]
            if "width" in clone:
                clone["width"] = clone["width"] * scale
        placed.append(clone)
    return placed


def shift_shapes(shapes: list[Shape], *, dx: float = 0.0, dy: float = 0.0) -> list[Shape]:
    moved = []
    for shape in shapes:
        clone = dict(shape)
        if clone["type"] == "circle":
            cx, cy = clone["c"]
            clone["c"] = (cx + dx, cy + dy)
        elif clone["type"] == "rrect":
            x0, y0, x1, y1 = clone["box"]
            clone["box"] = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        else:
            clone["points"] = [(x + dx, y + dy) for x, y in clone["points"]]
        moved.append(clone)
    return moved


def shape_points(shape: Shape) -> list[tuple[float, float]]:
    if shape["type"] == "circle":
        cx, cy = shape["c"]
        r = shape["r"]
        return [(cx - r, cy - r), (cx + r, cy + r)]
    if shape["type"] == "rrect":
        x0, y0, x1, y1 = shape["box"]
        return [(x0, y0), (x1, y1)]
    return list(shape["points"])


def bounds_of(shapes: list[Shape]) -> tuple[float, float, float, float]:
    points = [point for shape in shapes for point in shape_points(shape)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def fit_shapes(shapes: list[Shape], size: float, padding: float = 0.05) -> list[Shape]:
    """Scale and centre the drawing inside a square of `size` units."""
    x0, y0, x1, y1 = bounds_of(shapes)
    span = max(x1 - x0, y1 - y0)
    target = size * (1 - 2 * padding)
    factor = target / span
    dx = (size - (x1 - x0) * factor) / 2 - x0 * factor
    dy = (size - (y1 - y0) * factor) / 2 - y0 * factor
    scaled = []
    for shape in shapes:
        clone = dict(shape)
        if clone["type"] == "circle":
            clone["c"] = (clone["c"][0] * factor + dx, clone["c"][1] * factor + dy)
            clone["r"] = clone["r"] * factor
        elif clone["type"] == "rrect":
            x0_, y0_, x1_, y1_ = clone["box"]
            clone["box"] = (
                x0_ * factor + dx,
                y0_ * factor + dy,
                x1_ * factor + dx,
                y1_ * factor + dy,
            )
            clone["r"] = clone["r"] * factor
        else:
            clone["points"] = [(x * factor + dx, y * factor + dy) for x, y in clone["points"]]
            if clone["type"] == "curve":
                clone["width"] = clone["width"] * factor
        scaled.append(clone)
    return scaled


# --------------------------------------------------------------------------
# Font
# --------------------------------------------------------------------------


def font_path() -> Path:
    BUILD.mkdir(exist_ok=True)
    static = BUILD / "quicksand-600.ttf"
    if static.exists():
        return static
    source = BUILD / "quicksand.ttf"
    if not source.exists():
        urllib.request.urlretrieve(FONT_URL, source)
    instance = instantiateVariableFont(TTFont(source), {"wght": WEIGHT}, inplace=False)
    instance.save(static)
    return static


def glyph_run(text: str, font: TTFont, *, scale: float, baseline: float, left: float) -> list[dict]:
    """Outline glyphs, laid out left to right in SVG coordinates (y down)."""
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    pen_x = 0.0
    out = []
    for char in text:
        name = cmap[ord(char)]
        glyph = glyph_set[name]
        transform = (scale, 0, 0, -scale, left + pen_x, baseline)
        pen = SVGPathPen(glyph_set)
        glyph.draw(TransformPen(pen, transform))
        bounds_pen = BoundsPen(glyph_set)
        glyph.draw(TransformPen(bounds_pen, transform))
        out.append(
            {
                "char": char,
                "path": pen.getCommands(),
                "bounds": bounds_pen.bounds,
                "origin": left + pen_x,
            }
        )
        pen_x += (hmtx[name][0] + TRACKING) * scale
    return out


def word_width(font: TTFont, scale: float, text: str = WORD) -> float:
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    return sum(hmtx[cmap[ord(char)]][0] * scale for char in text) + TRACKING * scale * (
        len(text) - 1
    )


# --------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------


def svg_shape(shape: Shape) -> str:
    if shape["type"] == "rrect":
        x0, y0, x1, y1 = shape["box"]
        return (
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
            f'rx="{shape["r"]:.2f}" fill="{shape["fill"]}"/>'
        )
    if shape["type"] == "circle":
        cx, cy = shape["c"]
        return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{shape["r"]:.2f}" fill="{shape["fill"]}"/>'
    if shape["type"] == "polygon":
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in shape["points"])
        return f'<polygon points="{points}" fill="{shape["fill"]}"/>'
    if shape["type"] == "polyline":
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in shape["points"])
        return (
            f'<polyline points="{points}" fill="none" stroke="{shape["stroke"]}" '
            f'stroke-width="{shape["width"]:.2f}" stroke-linecap="round" '
            'stroke-linejoin="round"/>'
        )
    if shape["type"] == "curve":
        (x0, y0), (cx, cy), (x1, y1) = shape["points"]
        return (
            f'<path d="M {x0:.2f} {y0:.2f} Q {cx:.2f} {cy:.2f} {x1:.2f} {y1:.2f}" '
            f'fill="none" stroke="{shape["stroke"]}" stroke-width="{shape["width"]:.2f}" '
            'stroke-linecap="round"/>'
        )
    raise ValueError(shape["type"])


def draw_shape(draw: ImageDraw.ImageDraw, shape: Shape, scale: float) -> None:
    if shape["type"] == "rrect":
        x0, y0, x1, y1 = shape["box"]
        draw.rounded_rectangle(
            [x0 * scale, y0 * scale, x1 * scale, y1 * scale],
            radius=shape["r"] * scale,
            fill=rgb(shape["fill"]),
        )
    elif shape["type"] == "circle":
        cx, cy = shape["c"]
        r = shape["r"] * scale
        draw.ellipse(
            [cx * scale - r, cy * scale - r, cx * scale + r, cy * scale + r],
            fill=rgb(shape["fill"]),
        )
    elif shape["type"] == "polygon":
        draw.polygon([(x * scale, y * scale) for x, y in shape["points"]], fill=rgb(shape["fill"]))
    elif shape["type"] == "polyline":
        points = [(x * scale, y * scale) for x, y in shape["points"]]
        width = max(1, round(shape["width"] * scale))
        draw.line(points, fill=rgb(shape["stroke"]), width=width, joint="curve")
        for point in (points[0], points[-1]):
            radius = width / 2
            draw.ellipse(
                [point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius],
                fill=rgb(shape["stroke"]),
            )
    elif shape["type"] == "curve":
        (x0, y0), (cx, cy), (x1, y1) = shape["points"]
        points = []
        for step in range(25):
            t = step / 24
            points.append(
                (
                    ((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t**2 * x1) * scale,
                    ((1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t**2 * y1) * scale,
                )
            )
        width = max(1, round(shape["width"] * scale))
        draw.line(points, fill=rgb(shape["stroke"]), width=width, joint="curve")
        for point in (points[0], points[-1]):
            radius = width / 2
            draw.ellipse(
                [point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius],
                fill=rgb(shape["stroke"]),
            )
    else:
        raise ValueError(shape["type"])


def lockup_svg(
    shapes: list[Shape], glyphs: list[dict], name_colour: str, width: float, height: float
) -> str:
    body = "\n".join(f"  {svg_shape(shape)}" for shape in shapes)
    letters = "\n".join(
        f'  <path fill="{PETAL if glyph["char"] == "o" else name_colour}" d="{glyph["path"]}"/>'
        for glyph in glyphs
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}" role="img" aria-label="ozure">
  <title>ozure</title>
  <desc>A small kawaii jellyfish, with the name ozure next to it.</desc>
{body}
{letters}
</svg>
'''


def lockup_png(
    shapes: list[Shape],
    glyphs: list[dict],
    name_colour: str,
    width: float,
    height: float,
    size: int = 900,
) -> Image.Image:
    scale = size / width
    supersample = 2
    height_px = round(height * scale)
    image = Image.new("RGBA", (size * supersample, height_px * supersample), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        draw_shape(draw, shape, scale * supersample)
    font = ImageFont.truetype(str(font_path()), round(NAME_SIZE * scale * supersample))
    for glyph in glyphs:
        draw.text(
            (glyph["origin"] * scale * supersample, NAME_BASELINE * scale * supersample),
            glyph["char"],
            font=font,
            fill=rgb(PETAL if glyph["char"] == "o" else name_colour),
            anchor="ls",
        )
    return image.resize((size, height_px), Image.LANCZOS)


def icon_svg(shapes: list[Shape], size: int = 512) -> str:
    body = "\n".join(f"  {svg_shape(shape)}" for shape in shapes)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" aria-label="ozure">
  <title>ozure</title>
{body}
</svg>
'''


def icon_png(shapes: list[Shape], size: int = 1024) -> Image.Image:
    supersample = 2
    tile = size * supersample
    image = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # `shapes` are already laid out in the 512-unit icon canvas.
    for shape in shapes:
        draw_shape(draw, shape, tile / 512)
    return image.resize((size, size), Image.LANCZOS)


def wordmark_svg(glyphs: list[dict], width: float, height: float) -> str:
    letters = "\n".join(
        f'  <path fill="{PETAL if glyph["char"] == "o" else INK}" d="{glyph["path"]}"/>'
        for glyph in glyphs
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="ozure">
  <title>ozure</title>
{letters}
</svg>
"""


def wordmark_png(glyphs: list[dict], width: float, height: float, scale: int = 4) -> Image.Image:
    image = Image.new("RGBA", (round(width * scale), round(height * scale)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path()), round(100 * scale))
    for glyph in glyphs:
        draw.text(
            (glyph["origin"] * scale, (height - 12) * scale),
            glyph["char"],
            font=font,
            fill=rgb(PETAL if glyph["char"] == "o" else INK),
            anchor="ls",
        )
    return image


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    font = TTFont(font_path())
    units = font["head"].unitsPerEm

    # Horizontal lockup: the jellyfish on the left, the name on its right.
    jelly = jelly_shapes()
    jx0, jy0, jx1, jy1 = bounds_of(jelly)
    jelly_scale = JELLY_HEIGHT / (jy1 - jy0)
    jelly_width = (jx1 - jx0) * jelly_scale
    name_scale = NAME_SIZE / units
    total = word_width(font, name_scale)
    name_left = MARGIN + jelly_width + NAME_GAP

    glyphs = glyph_run(WORD, font, scale=name_scale, baseline=NAME_BASELINE, left=name_left)
    # Sit the creature on the optical centre of the lowercase word, not on the
    # canvas centre: that is what makes the lockup read as one unit.
    word_top = min(glyph["bounds"][1] for glyph in glyphs if glyph["bounds"])
    optical_centre = (word_top + NAME_BASELINE) / 2
    jelly_top = optical_centre - JELLY_HEIGHT / 2
    height = max(jelly_top + JELLY_HEIGHT, NAME_BASELINE) + MARGIN
    width = name_left + total + MARGIN
    placed = place_shapes(jelly, jelly_scale, MARGIN, jelly_top)

    (ASSETS / "logo.svg").write_text(
        lockup_svg(placed, glyphs, INK, width, height), encoding="utf-8"
    )
    lockup_png(placed, glyphs, INK, width, height).save(ASSETS / "logo.png")
    (ASSETS / "logo-dark.svg").write_text(
        lockup_svg(placed, glyphs, CREAM, width, height), encoding="utf-8"
    )
    lockup_png(placed, glyphs, CREAM, width, height).save(ASSETS / "logo-dark.png")

    # The avatar is the creature alone, centred in a square.
    icon = fit_shapes(jelly_shapes(with_sparkles=True), 512, padding=0.06)
    (ASSETS / "icon.svg").write_text(icon_svg(icon), encoding="utf-8")
    icon_png(icon).save(ASSETS / "icon.png")

    small_scale = 100 / units
    small_width = word_width(font, small_scale)
    small_glyphs = glyph_run(WORD, font, scale=small_scale, baseline=96, left=6)
    (ASSETS / "wordmark.svg").write_text(
        wordmark_svg(small_glyphs, small_width + 12, 130), encoding="utf-8"
    )
    wordmark_png(small_glyphs, small_width + 12, 130).save(ASSETS / "wordmark.png")

    (ASSETS / "palette.md").write_text(
        "# Palette\n\n"
        "| role | hex |\n| --- | --- |\n"
        f"| primary (pastel pink) | `{PETAL}` |\n"
        f"| primary deep | `{PETAL_DEEP}` |\n"
        f"| surface (blush) | `{BLUSH}` |\n"
        f"| background (cream) | `{CREAM}` |\n"
        f"| ink | `{INK}` |\n"
        f"| highlight | `{WHITE}` |\n",
        encoding="utf-8",
    )
    print("wrote assets/logo{,-dark}.{svg,png}, icon.{svg,png}, wordmark.{svg,png}, palette.md")


if __name__ == "__main__":
    main()
