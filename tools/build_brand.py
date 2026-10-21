"""Build the ozure brand: a wordmark that *is* the logo, plus a square icon.

The name is the mark: "ozure" set in Quicksand SemiBold, lowercase, with the
"o" — the lens — in pastel pink. Real outlines, not live text, so the SVG looks
the same everywhere.

    python tools/build_brand.py

The tool downloads Quicksand (SIL OFL) into .build/ on first run and instances
the weight it needs; only the generated SVG/PNGs are committed.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

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

# Pastel, low-noise palette: one pink, one soft ink, one cream.
PETAL = "#f2a3b6"
BLUSH = "#fce4ea"
CREAM = "#fff9f7"
INK = "#2c2f38"


def washed(hex_colour: str) -> tuple[int, int, int]:
    value = hex_colour.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def font_path() -> Path:
    BUILD.mkdir(exist_ok=True)
    static = BUILD / "quicksand-600.ttf"
    if static.exists():
        return static
    source = BUILD / "quicksand.ttf"
    if not source.exists():
        urllib.request.urlretrieve(FONT_URL, source)
    variable = TTFont(source)
    instance = instantiateVariableFont(variable, {"wght": WEIGHT}, inplace=False)
    instance.save(static)
    return static


def glyph_run(text: str, font: TTFont, baseline: float = 0.0) -> list[dict]:
    """Outline each glyph, laid out left to right, in SVG coordinates (y down)."""
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    x = 0.0
    glyphs = []
    for char in text:
        name = cmap[ord(char)]
        glyph = glyph_set[name]
        pen = SVGPathPen(glyph_set)
        glyph.draw(TransformPen(pen, (1, 0, 0, -1, x, baseline)))
        bounds_pen = BoundsPen(glyph_set)
        glyph.draw(TransformPen(bounds_pen, (1, 0, 0, -1, x, baseline)))
        glyphs.append(
            {
                "char": char,
                "path": pen.getCommands(),
                "bounds": bounds_pen.bounds,
                "origin": x,
            }
        )
        x += hmtx[name][0] + TRACKING
    return glyphs


def bounds_of(glyphs: list[dict]) -> tuple[float, float, float, float]:
    boxes = [glyph["bounds"] for glyph in glyphs if glyph["bounds"]]
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[2] for box in boxes)
    y1 = max(box[3] for box in boxes)
    return x0, y0, x1, y1


def wordmark_svg(
    glyphs: list[dict], pad: float = 26
) -> tuple[str, tuple[float, float, float, float]]:
    x0, y0, x1, y1 = bounds_of(glyphs)
    view = (x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
    paths = []
    for glyph in glyphs:
        colour = PETAL if glyph["char"] == "o" else INK
        paths.append(f'  <path fill="{colour}" d="{glyph["path"]}"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view[0]:.1f} {view[1]:.1f} {view[2]:.1f} {view[3]:.1f}" role="img" aria-label="ozure">
  <title>ozure</title>
  <desc>Wordmark: the name is the logo. The o is a pastel-pink lens.</desc>
{chr(10).join(paths)}
</svg>
'''
    return svg, view


def draw_glyph(
    draw, glyph: dict, origin: float, baseline: float, font, size: float, colour
) -> None:
    """Draw one glyph so its pen origin lands exactly on (origin, baseline)."""
    draw.text((origin, baseline), glyph["char"], font=font, fill=colour, anchor="ls")
    del size


def wordmark_png(
    glyphs: list[dict], view: tuple[float, float, float, float], width: int = 1600
) -> Image.Image:
    scale = width / view[2]
    height = round(view[3] * scale)
    supersample = 2
    font_size = round(1000 * scale * supersample)
    image = Image.new("RGBA", (width * supersample, height * supersample), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path()), font_size)
    baseline = -view[1] * scale * supersample
    for glyph in glyphs:
        colour = washed(PETAL if glyph["char"] == "o" else INK)
        origin = (glyph["origin"] - view[0]) * scale * supersample
        draw_glyph(draw, glyph, origin, baseline, font, font_size, colour)
    return image.resize((width, height), Image.LANCZOS)


def icon_svg(glyphs: list[dict], view: tuple[float, float, float, float], size: int = 512) -> str:
    o = glyphs[0]
    ox0, oy0, ox1, oy1 = o["bounds"]
    tile = size
    scale = tile * 0.62 / max(ox1 - ox0, oy1 - oy0)
    dx = tile / 2 - (ox0 + (ox1 - ox0) / 2) * scale
    dy = tile / 2 - (oy0 + (oy1 - oy0) / 2) * scale
    dot = (ox1 - ox0) * scale * 0.147
    cx = tile / 2
    cy = tile / 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {tile} {tile}" role="img" aria-label="ozure">
  <title>ozure</title>
  <rect width="{tile}" height="{tile}" rx="{tile * 0.225:.0f}" fill="{PETAL}"/>
  <g transform="translate({dx:.1f} {dy:.1f}) scale({scale:.4f})">
    <path fill="{CREAM}" d="{o["path"]}"/>
  </g>
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{dot:.1f}" fill="{CREAM}"/>
</svg>
'''


def icon_png(glyphs: list[dict], glyph_font: TTFont, size: int = 1024) -> Image.Image:
    o = glyphs[0]
    x0, y0, x1, y1 = o["bounds"]
    supersample = 2
    tile = size * supersample
    image = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [0, 0, tile - 1, tile - 1], radius=round(tile * 0.225), fill=washed(PETAL)
    )
    units = glyph_font["head"].unitsPerEm
    font_size = round(0.62 * tile * units / max(x1 - x0, y1 - y0))
    scale = font_size / units
    font = ImageFont.truetype(str(font_path()), font_size)
    # `bounds` are already in SVG coordinates (y down), so the ink centre sits
    # at baseline + (y0 + y1) / 2 * scale.
    origin = tile / 2 - (x0 + x1) / 2 * scale
    baseline = tile / 2 - (y0 + y1) / 2 * scale
    draw_glyph(draw, o, origin, baseline, font, font_size, washed(CREAM))
    dot = tile * 0.058
    draw.ellipse(
        [tile / 2 - dot, tile / 2 - dot, tile / 2 + dot, tile / 2 + dot], fill=washed(CREAM)
    )
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    font = TTFont(font_path())
    glyphs = glyph_run(WORD, font, baseline=0)
    svg, view = wordmark_svg(glyphs)
    (ASSETS / "logo.svg").write_text(svg, encoding="utf-8")
    wordmark_png(glyphs, view).save(ASSETS / "logo.png")
    (ASSETS / "icon.svg").write_text(icon_svg(glyphs, view), encoding="utf-8")
    icon_png(glyphs, font).save(ASSETS / "icon.png")
    (ASSETS / "palette.md").write_text(
        "# Palette\n\n"
        f"| role | hex |\n| --- | --- |\n"
        f"| primary (pastel pink) | `{PETAL}` |\n"
        f"| surface (blush) | `{BLUSH}` |\n"
        f"| background (cream) | `{CREAM}` |\n"
        f"| ink | `{INK}` |\n",
        encoding="utf-8",
    )
    print("wrote assets/logo.svg, logo.png, icon.svg, icon.png, palette.md")


if __name__ == "__main__":
    main()
