"""Import the Discover collections from fuji-ptp-android into catalog folders.

The Android app hardcodes ~9 curated collections as Kotlin literals: a name, a
film simulation enum and a human description like

    Film Simulation: Classic Chrome · Grain Effect: Weak, Small · Color Chrome
    Effect: Strong · White Balance: Daylight, +2 Red & -5 Blue · Dynamic Range:
    DR200 · Highlight: 0 · Shadow: +0.5 · Color: +2 · Sharpness: +1 · High ISO
    NR: -4 · Clarity: +3

This script parses that text into real recipes, validates them with ozure's own
model, and writes one catalog per collection:

    catalog/<collection-id>/catalog.json     collection metadata
    catalog/<collection-id>/<recipe-slug>.json

Run: python tools/import_discover.py [--source PATH_OR_URL] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ozure.catalog import slugify  # noqa: E402
from ozure.recipe import Recipe  # noqa: E402

SOURCE_URL = (
    "https://raw.githubusercontent.com/AlPeFe/fuji-ptp-android/main/"
    "android/app/src/main/kotlin/com/alpefe/fujiptp/data/DiscoverData.kt"
)
CACHE = ROOT / ".build" / "DiscoverData.kt"

FILM_MAP = {
    "Provia": "provia",
    "Velvia": "velvia",
    "Astia": "astia",
    "ProNegHigh": "pro_neg_hi",
    "ProNegStandard": "pro_neg_std",
    "Monochrome": "monochrome",
    "MonochromeYellow": "monochrome_ye",
    "MonochromeRed": "monochrome_r",
    "MonochromeGreen": "monochrome_g",
    "Sepia": "sepia",
    "ClassicChrome": "classic_chrome",
    "Acros": "acros",
    "AcrosYellow": "acros_ye",
    "AcrosRed": "acros_r",
    "AcrosGreen": "acros_g",
    "Eterna": "eterna",
    "ClassicNegative": "classic_negative",
    "EternaBleachBypass": "eterna_bleach_bypass",
    "NostalgicNegative": "nostalgic_negative",
    "RealaAce": "reala_ace",
}

FILM_LABELS = {
    "classic chrome",
    "classic negative",
    "nostalgic neg.",
    "nostalgic neg",
    "reala ace",
    "provia",
    "velvia",
    "astia",
    "eterna",
    "eterna bleach bypass",
    "acros",
    "acros + r filter",
    "monochrome",
}

UNICODE_FIXES = {"\u2212": "-", "\u2013": "-", "\u2014": "-", "\u00a0": " "}


def clean(text: str) -> str:
    for old, new in UNICODE_FIXES.items():
        text = text.replace(old, new)
    return text


def unescape_kotlin(text: str) -> str:
    return text.replace('\\"', '"').replace("\\n", " ").replace("\\t", " ").replace("\\\\", "\\")


# --------------------------------------------------------------------------
# DiscoverData.kt
# --------------------------------------------------------------------------

COLLECTION_HEADER_RE = re.compile(
    r'\s*id = "(?P<id>[^"]*)",\s*'
    r'name = "(?P<name>[^"]*)",\s*'
    r'tagline = "(?P<tagline>[^"]*)",\s*'
    r'logo = "(?P<logo>[^"]*)",\s*'
    r"colorHex = (?P<color>0x[0-9A-Fa-f]+),\s*"
    r'source = "(?P<source>[^"]*)",\s*'
    r"recipes = listOf\(",
    re.S,
)
RECIPE_RE = re.compile(
    r'\br\(\s*"(?P<name>(?:[^"\\]|\\.)*)",\s*'
    r'"(?P<film>[A-Za-z]+)",\s*'
    r'"(?P<desc>(?:[^"\\]|\\.)*)",\s*'
    r'"(?P<source>(?:[^"\\]|\\.)*)"\s*,?\s*\)',
    re.S,
)


def parse_collections(text: str) -> list[dict]:
    """Split on the constructor instead of one big regex: recipes contain `),`
    themselves, which defeats a non-greedy group."""
    collections = []
    for block in text.split("DiscoverCollection(")[1:]:
        header = COLLECTION_HEADER_RE.match(block)
        if not header:
            continue
        recipes = [
            {
                "name": unescape_kotlin(item.group("name")).strip(),
                "film": item.group("film"),
                "description": clean(unescape_kotlin(item.group("desc"))).strip(),
                "source": unescape_kotlin(item.group("source")).strip(),
            }
            for item in RECIPE_RE.finditer(block)
        ]
        collections.append(
            {
                "id": header.group("id"),
                "name": unescape_kotlin(header.group("name")),
                "tagline": unescape_kotlin(header.group("tagline")),
                "logo": header.group("logo"),
                "color": header.group("color"),
                "source": unescape_kotlin(header.group("source")),
                "recipes": recipes,
            }
        )
    return collections


# --------------------------------------------------------------------------
# Description -> recipe
# --------------------------------------------------------------------------

NUMBER = r"[+-]?\d+(?:\.\d+)?"
GRAIN_WORDS = {
    ("off", ""): "off",
    ("weak", "small"): "weak_small",
    ("strong", "small"): "strong_small",
    ("weak", "large"): "weak_large",
    ("strong", "large"): "strong_large",
}
STRENGTHS = {"off": "off", "weak": "weak", "strong": "strong"}


def number(text: str) -> float | None:
    match = re.search(NUMBER, text)
    return float(match.group(0)) if match else None


def strength(text: str) -> str | None:
    if "off" in text:
        return "off"
    if "weak" in text:
        return "weak"
    if "strong" in text:
        return "strong"
    return None


def grain_of(text: str) -> str | None:
    if "off" in text:
        return "off"
    strength_word = "strong" if "strong" in text else "weak" if "weak" in text else None
    size_word = "large" if "large" in text else "small" if "small" in text else None
    if strength_word is None:
        return None
    if size_word is None:
        size_word = "small"
    return GRAIN_WORDS[(strength_word, size_word)]


def white_balance_of(segment: str) -> dict | None:
    text = segment.split(":", 1)[1] if ":" in segment else segment
    text = text.strip()
    mode = None
    for needle, value in (
        ("auto white priority", "ambience_priority"),
        ("auto ambience priority", "ambience_priority"),
        ("ambience", "ambience_priority"),
        ("daylight", "daylight"),
        ("shade", "shade"),
        ("incandescent", "incandescent"),
        ("fluorescent 3", "fluorescent_3"),
        ("fluorescent 2", "fluorescent_2"),
        ("fluorescent 1", "fluorescent_1"),
        ("underwater", "underwater"),
        ("auto", "auto"),
    ):
        if needle in text:
            mode = value
            break
    temperature = re.search(r"(\d{4})\s*k\b", text)
    if temperature:
        mode = "color_temperature"
    shift_r, shift_b = shifts_of(text)
    if mode is None:
        if not (shift_r or shift_b):
            return None
        # "WB Shift: R -4, B -3" with no mode word means the auto mode.
        mode = "auto"
    wb = {"mode": mode, "shift_r": shift_r, "shift_b": shift_b}
    if temperature:
        wb["color_temperature"] = int(temperature.group(1))
    return wb


def shifts_of(text: str) -> tuple[int, int]:
    """Read the white balance shift in any of the shapes these recipes use:
    "R -4, B -3", "-4 Red & -3 Blue", "(R +4, B -4)", "+2R/-4B"."""
    patterns = (
        (r"([+-]?\d+)\s*r(?:ed)?\b[\s,&/]*(?:and\s*)?([+-]?\d+)\s*b(?:lue)?\b", "rb"),
        (r"([+-]?\d+)\s*b(?:lue)?\b[\s,&/]*(?:and\s*)?([+-]?\d+)\s*r(?:ed)?\b", "br"),
        (r"r(?:ed)?\s*([+-]?\d+)\s*[,&/]\s*(?:and\s*)?b(?:lue)?\s*([+-]?\d+)", "rb"),
        (r"b(?:lue)?\s*([+-]?\d+)\s*[,&/]\s*(?:and\s*)?r(?:ed)?\s*([+-]?\d+)", "br"),
        (r"([+-]?\d+)\s*r\s*/\s*([+-]?\d+)\s*b\b", "rb"),
    )
    for pattern, order in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        first, second = int(match.group(1)), int(match.group(2))
        return (first, second) if order == "rb" else (second, first)
    return (0, 0)


def tone_curve(segment: str) -> tuple[float | None, float | None]:
    text = segment.split(":", 1)[1] if ":" in segment else segment
    highlight = re.search(rf"h\s*({NUMBER})", text)
    shadow = re.search(rf"s\s*({NUMBER})", text)
    return (
        float(highlight.group(1)) if highlight else None,
        float(shadow.group(1)) if shadow else None,
    )


def parse_description(description: str, film_enum: str) -> tuple[dict, list[str]]:
    data: dict = {"film_simulation": FILM_MAP.get(film_enum, "classic_chrome")}
    notes: list[str] = []
    segments = [segment.strip() for segment in description.split("·") if segment.strip()]

    for segment in segments:
        lowered = segment.lower()
        if "film sim" in lowered or lowered.startswith("para "):
            continue
        if "nr" in lowered or "noise reduction" in lowered:
            value = number(lowered)
            if value is not None:
                data["noise_reduction"] = int(value)
            continue
        informational = ("look ", "suele ", "iso", "exposure compensation", "notas", "consejo")
        if any(word in lowered for word in informational):
            continue
        if lowered in set(FILM_LABELS):
            continue
        if "iso" in lowered or "exposure compensation" in lowered:
            continue
        if "grain" in lowered:
            value = grain_of(lowered)
            if value:
                data["grain_effect"] = value
            continue
        if "fx blue" in lowered or "fxblue" in lowered:
            value = strength(lowered)
            if value:
                data["color_chrome_fx_blue"] = value
            continue
        if (
            "color chrome" in lowered
            or "colour chrome" in lowered
            or lowered.startswith("cc")
            or "chrome effect" in lowered
        ):
            value = strength(lowered)
            if value:
                data["color_chrome"] = value
            continue
        if "monochromatic" in lowered or "mono color" in lowered or "mono colour" in lowered:
            wc = re.search(rf"wc\s*({NUMBER})", lowered)
            mg = re.search(rf"mg\s*({NUMBER})", lowered)
            if wc:
                data["monochrome_wc"] = float(wc.group(1))
            if mg:
                data["monochrome_mg"] = float(mg.group(1))
            continue
        if "white balance" in lowered or re.match(r"^wb\b", lowered) or "wb shift" in lowered:
            wb = white_balance_of(lowered)
            if wb:
                data["white_balance"] = wb
            else:
                notes.append(f"white balance not understood: {segment}")
            continue
        if "dr-p" in lowered or "d-range priority" in lowered or "drange prio" in lowered:
            if "off" not in lowered:
                notes.append(f"dynamic range priority not representable: {segment}")
            continue
        if "dynamic range" in lowered or "drange" in lowered or re.match(r"^dr", lowered):
            match = re.search(r"(auto|100|200|400)", lowered)
            if match:
                value = match.group(1)
                data["dynamic_range"] = "dr100" if value == "auto" else f"dr{value}"
            continue
        if "tone curve" in lowered or "curve" in lowered or re.match(r"^h\s*[+-]?\d", lowered):
            highlight, shadow = tone_curve(lowered)
            if highlight is not None:
                data["highlight"] = highlight
            if shadow is not None:
                data["shadow"] = shadow
            continue
        if "highlight" in lowered:
            value = number(lowered)
            if value is not None:
                data["highlight"] = value
            continue
        if "shadow" in lowered:
            value = number(lowered)
            if value is not None:
                data["shadow"] = value
            continue
        if "sharp" in lowered:
            value = number(lowered)
            if value is not None:
                data["sharpness"] = value
            continue
        if "clarity" in lowered:
            value = number(lowered)
            if value is not None:
                data["clarity"] = value
            continue
        if re.search(r"\bnr\b", lowered) or "noise reduction" in lowered:
            value = number(lowered)
            if value is not None:
                data["noise_reduction"] = int(value)
            continue
        if re.match(r"^colou?r\b", lowered) and "chrome" not in lowered:
            value = re.search(rf"colou?r\s*[:]?\s*({NUMBER})", lowered)
            if value:
                data["color"] = float(value.group(1))
            continue
        notes.append(f"ignored: {segment}")
    return data, notes


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def build(source: Path, out: Path) -> dict[str, int]:
    text = source.read_text(encoding="utf-8")
    collections = parse_collections(text)
    total = 0
    problems = 0
    for collection in collections:
        if not collection["recipes"]:
            continue
        directory = out / collection["id"]
        directory.mkdir(parents=True, exist_ok=True)
        # Regenerating: drop the old files so slug changes do not leave
        # duplicates behind.
        for stale in directory.glob("*.json"):
            if stale.name != "catalog.json":
                stale.unlink()
        (directory / "catalog.json").write_text(
            json.dumps(
                {
                    "name": collection["name"],
                    "tagline": collection["tagline"],
                    "source": collection["source"],
                    "logo": collection["logo"],
                    "color": collection["color"],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        used: set[str] = set()
        for item in collection["recipes"]:
            data, notes = parse_description(item["description"], item["film"])
            data["name"] = item["name"]
            try:
                recipe = Recipe.from_dict(data)
            except Exception as exc:
                problems += 1
                print(f"  ! {collection['id']}/{item['name']}: {exc}")
                continue
            slug = slugify(item["name"])
            while slug in used:
                slug += "-2"
            used.add(slug)
            entry = {
                "slug": slug,
                "name": item["name"],
                "source": item["source"] or collection["source"],
                "notes": item["description"],
                "tags": ["imported", collection["id"]],
                "recipe": recipe.to_dict(),
            }
            if notes:
                entry["parse_notes"] = notes
            (directory / f"{slug}.json").write_text(
                json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            total += 1
    return {"collections": len(collections), "recipes": total, "problems": problems}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="DiscoverData.kt path or URL")
    parser.add_argument("--out", default=str(ROOT / "catalog"))
    args = parser.parse_args()

    if args.source:
        source = Path(args.source).expanduser()
        if not source.exists():
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(args.source, CACHE)
            source = CACHE
    else:
        source = CACHE
        if not source.exists():
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(SOURCE_URL, CACHE)

    stats = build(source, Path(args.out))
    print(
        f"{stats['recipes']} recipes in {stats['collections']} collections "
        f"({stats['problems']} could not be parsed)"
    )
    return 0 if stats["problems"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
