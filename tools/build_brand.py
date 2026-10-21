"""Build the ozure brand: a cute camera illustration with the name under it.

One geometry description, two renderers: the same shapes produce
`assets/logo.svg` and `assets/logo.png`, so the vector and the raster can never
drift apart. Two dialects of the same drawing exist:

* logo   — pink camera + the wordmark, on a soft blush halo (README / social)
* icon   — cream camera on a pink tile (avatar): no name, reads at 32 px
* wordmark — just the name, for tight spaces like the demo title bar

    python tools/build_brand.py

The script downloads Quicksand (SIL OFL) into .build/ on first run and instances
the weight it needs; only the generated SVG/PNGs are committed.
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

# Canvas shared by every lockup piece (SVG units = px at 1x).
WIDTH, HEIGHT = 512, 578
NAME_SIZE = 74
NAME_BASELINE = 540

Shape = dict[str, Any]


def rgb(hex_colour: str) -> tuple[int, int, int, int]:
    value = hex_colour.lstrip("#")
    return (*[int(value[index : index + 2], 16) for index in (0, 2, 4)], 255)


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
# Drawing primitives (shared model)
# --------------------------------------------------------------------------


def star(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    """Four-point sparkle, the kawaii kind."""
    points = []
    for index in range(8):
        angle = math.radians(index * 45 - 90)
        span = radius if index % 2 == 0 else radius * 0.32
        points.append((cx + span * math.cos(angle), cy + span * math.sin(angle)))
    return points


def camera_shapes(
    *,
    body: str,
    plate: str,
    lens_ring: str,
    lens_inner: str,
    face: str,
    cheek: str,
    highlight: str,
    sparkle: str,
) -> list[Shape]:
    """A cute camera: pink body, big lens, smiley face, sparkle."""
    return [
        # soft halo so the drawing sits on the page instead of floating
        {"type": "circle", "c": (256, 246), "r": 196, "fill": BLUSH},
        {"type": "rrect", "box": (96, 120, 416, 392), "r": 58, "fill": body},
        {"type": "rrect", "box": (190, 84, 322, 132), "r": 20, "fill": plate},
        {"type": "rrect", "box": (338, 96, 382, 114), "r": 9, "fill": plate},
        {"type": "circle", "c": (206, 262), "r": 68, "fill": lens_ring},
        {"type": "circle", "c": (206, 262), "r": 50, "fill": lens_inner},
        {"type": "circle", "c": (228, 238), "r": 12, "fill": highlight},
        {"type": "circle", "c": (298, 244), "r": 9, "fill": face},
        {"type": "circle", "c": (346, 244), "r": 9, "fill": face},
        {
            "type": "curve",
            "points": [(300, 268), (322, 292), (344, 268)],
            "stroke": face,
            "width": 7,
        },
        {"type": "circle", "c": (288, 300), "r": 11, "fill": cheek},
        {"type": "circle", "c": (366, 300), "r": 11, "fill": cheek},
        # Sparkles sit outside the body, so they take their own colour.
        {"type": "polygon", "points": star(448, 140, 15), "fill": sparkle},
        {"type": "polygon", "points": star(470, 196, 9), "fill": sparkle},
    ]


def svg_shape(shape: Shape) -> str:
    if shape["type"] == "rrect":
        x0, y0, x1, y1 = shape["box"]
        return (
            f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" '
            f'rx="{shape["r"]}" fill="{shape["fill"]}"/>'
        )
    if shape["type"] == "circle":
        cx, cy = shape["c"]
        return f'<circle cx="{cx}" cy="{cy}" r="{shape["r"]}" fill="{shape["fill"]}"/>'
    if shape["type"] == "polygon":
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in shape["points"])
        return f'<polygon points="{points}" fill="{shape["fill"]}"/>'
    if shape["type"] == "curve":
        (x0, y0), (cx, cy), (x1, y1) = shape["points"]
        return (
            f'<path d="M {x0} {y0} Q {cx} {cy} {x1} {y1}" fill="none" '
            f'stroke="{shape["stroke"]}" stroke-width="{shape["width"]}" '
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


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------


def lockup_svg(shapes: list[Shape], glyphs: list[dict]) -> str:
    body = "\n".join(f"  {svg_shape(shape)}" for shape in shapes)
    letters = "\n".join(
        f'  <path fill="{PETAL if glyph["char"] == "o" else INK}" d="{glyph["path"]}"/>'
        for glyph in glyphs
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" role="img" aria-label="ozure">
  <title>ozure</title>
  <desc>A cute pastel camera, with the name ozure underneath.</desc>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{CREAM}"/>
{body}
{letters}
</svg>
'''


def render_svg_shapes(shapes: list[Shape], width: int, height: int) -> str:
    body = "\n".join(f"  {svg_shape(shape)}" for shape in shapes)
    return body, width, height


def lockup_png(shapes: list[Shape], glyphs: list[dict], size: int = 900) -> Image.Image:
    scale = size / WIDTH
    supersample = 2
    height = round(HEIGHT * scale)
    image = Image.new("RGBA", (size * supersample, height * supersample), rgb(CREAM))
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        draw_shape(draw, shape, scale * supersample)
    font = ImageFont.truetype(str(font_path()), round(NAME_SIZE * scale * supersample))
    for glyph in glyphs:
        draw.text(
            (glyph["origin"] * scale * supersample, NAME_BASELINE * scale * supersample),
            glyph["char"],
            font=font,
            fill=rgb(PETAL if glyph["char"] == "o" else INK),
            anchor="ls",
        )
    return image.resize((size, height), Image.LANCZOS)


def icon_shapes() -> list[Shape]:
    """Cream camera on a pink tile, no name: reads at avatar sizes."""
    shapes = camera_shapes(
        body=CREAM,
        plate=BLUSH,
        lens_ring=PETAL,
        lens_inner=BLUSH,
        face=INK,
        cheek=PETAL,
        highlight=WHITE,
        sparkle=CREAM,
    )
    # Drop the halo (the tile is the background) and re-centre the drawing.
    return [shape for shape in shapes if not (shape["type"] == "circle" and shape.get("r") == 196)]


def icon_svg(shapes: list[Shape], size: int = 512) -> str:
    scale = size / WIDTH
    offset_y = -(84 + 392) / 2 * scale + size / 2
    body = "\n".join(f"  {svg_shape(shape)}" for shape in shapes)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" aria-label="ozure">
  <title>ozure</title>
  <rect width="{size}" height="{size}" rx="{round(size * 0.225)}" fill="{PETAL}"/>
  <g transform="translate({(size - WIDTH * scale) / 2:.2f} {offset_y:.2f}) scale({scale:.4f})">
{body}
  </g>
</svg>
'''


def icon_png(shapes: list[Shape], size: int = 1024) -> Image.Image:
    supersample = 2
    tile = size * supersample
    scale = tile / WIDTH
    offset_y = -(84 + 392) / 2 * scale + tile / 2
    image = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, tile - 1, tile - 1], radius=round(tile * 0.225), fill=rgb(PETAL))
    shifted = []
    for shape in shapes:
        clone = dict(shape)
        if clone["type"] == "circle":
            cx, cy = clone["c"]
            clone["c"] = (cx, cy + offset_y / scale)
        elif clone["type"] == "rrect":
            x0, y0, x1, y1 = clone["box"]
            clone["box"] = (x0, y0 + offset_y / scale, x1, y1 + offset_y / scale)
        elif clone["type"] == "polygon" or clone["type"] == "curve":
            clone["points"] = [(x, y + offset_y / scale) for x, y in clone["points"]]
        shifted.append(clone)
    for shape in shifted:
        draw_shape(draw, shape, scale)
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

    scale = NAME_SIZE / font["head"].unitsPerEm
    total = word_width(font, scale)
    glyphs = glyph_run(WORD, font, scale=scale, baseline=NAME_BASELINE, left=(WIDTH - total) / 2)

    logo_shapes = camera_shapes(
        body=PETAL,
        plate=PETAL_DEEP,
        lens_ring=CREAM,
        lens_inner=BLUSH,
        face=INK,
        cheek=PETAL_DEEP,
        highlight=CREAM,
        sparkle=PETAL_DEEP,
    )
    (ASSETS / "logo.svg").write_text(lockup_svg(logo_shapes, glyphs), encoding="utf-8")
    lockup_png(logo_shapes, glyphs).save(ASSETS / "logo.png")

    icon = icon_shapes()
    (ASSETS / "icon.svg").write_text(icon_svg(icon), encoding="utf-8")
    icon_png(icon).save(ASSETS / "icon.png")

    # Wordmark only: tight spaces (demo title bar, favicons, docs headers).
    small_scale = 100 / font["head"].unitsPerEm
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
    print("wrote assets/logo.{svg,png}, icon.{svg,png}, wordmark.{svg,png}, palette.md")


if __name__ == "__main__":
    main()
