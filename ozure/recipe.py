"""The Fujifilm custom recipe domain model, plus the PTP wire codecs.

Naming follows fuji-ptp-core's serde representation (snake_case) so a recipe
dumped by one tool can be loaded by the other.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .errors import InvalidRecipe

# --------------------------------------------------------------------------
# Catalogs of allowed values
# --------------------------------------------------------------------------

FILM_SIMULATIONS: dict[str, int] = {
    "provia": 1,
    "velvia": 2,
    "astia": 3,
    "pro_neg_hi": 4,
    "pro_neg_std": 5,
    "monochrome": 6,
    "monochrome_ye": 7,
    "monochrome_r": 8,
    "monochrome_g": 9,
    "sepia": 10,
    "classic_chrome": 11,
    "acros": 12,
    "acros_ye": 13,
    "acros_r": 14,
    "acros_g": 15,
    "eterna": 16,
    "classic_negative": 17,
    "eterna_bleach_bypass": 18,
    "nostalgic_negative": 19,
    "reala_ace": 20,
}

GRAIN_EFFECTS: dict[str, int] = {
    "off": 1,
    "weak_small": 2,
    "strong_small": 3,
    "weak_large": 4,
    "strong_large": 5,
}

EFFECT_STRENGTHS: dict[str, int] = {"off": 1, "weak": 2, "strong": 3}

WHITE_BALANCE_MODES: dict[str, int] = {
    "auto": 2,
    "daylight": 4,
    "shade": 0x8006,
    "fluorescent_1": 0x8001,
    "fluorescent_2": 0x8002,
    "fluorescent_3": 0x8003,
    "incandescent": 6,
    "underwater": 8,
    "color_temperature": 0x8007,
    "ambience_priority": 0x8021,
}

DYNAMIC_RANGES: dict[str, int] = {"dr100": 100, "dr200": 200, "dr400": 400}

DR_PRIORITIES: dict[str, int] = {"auto": 0, "dr100": 1, "dr200": 2, "dr400": 32768}

NR_VALUES: dict[int, int] = {
    -4: 0x8000,
    -3: 28672,
    -2: 16384,
    -1: 12288,
    0: 8192,
    1: 4096,
    2: 0,
    3: 24576,
    4: 20480,
}
NR_FROM_WIRE: dict[int, int] = {wire: value for value, wire in NR_VALUES.items()}

MONO_FILM_SIMULATIONS = {
    "monochrome",
    "monochrome_ye",
    "monochrome_r",
    "monochrome_g",
    "sepia",
    "acros",
    "acros_ye",
    "acros_r",
    "acros_g",
}

# Input aliases an agent or a human is likely to type. Keys are normalised
# with `_slug()` before lookup, so "Classic Negative" also lands here.
ALIASES: dict[str, str] = {
    "provia_standard": "provia",
    "standard": "provia",
    "pro_neg_high": "pro_neg_hi",
    "pro_neg_standard": "pro_neg_std",
    "pro_neg_std_": "pro_neg_std",
    "acros_yellow": "acros_ye",
    "acros_red": "acros_r",
    "acros_green": "acros_g",
    "monochrome_yellow": "monochrome_ye",
    "monochrome_red": "monochrome_r",
    "monochrome_green": "monochrome_g",
    "classic_neg": "classic_negative",
    "eterna_bb": "eterna_bleach_bypass",
    "bleach_bypass": "eterna_bleach_bypass",
    "reala": "reala_ace",
    "nostalgic": "nostalgic_negative",
    "fluorescent1": "fluorescent_1",
    "fluorescent2": "fluorescent_2",
    "fluorescent3": "fluorescent_3",
    "fluorescent": "fluorescent_1",
    "kelvin": "color_temperature",
    "temp": "color_temperature",
    "awb": "auto",
    "ambience": "ambience_priority",
    "ws": "weak_small",
    "ss": "strong_small",
    "wl": "weak_large",
    "sl": "strong_large",
    "dr_auto": "auto",
}

SLOTS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")


def _slug(value: Any) -> str:
    """Normalise a human/agent-supplied enum value: 'Classic Negative' -> classic_negative."""
    text = str(value).strip().lower()
    for ch in (" ", "-", "."):
        text = text.replace(ch, "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _canon(value: Any, catalog: dict[str, Any], label: str) -> str:
    key = _slug(value)
    key = ALIASES.get(key, key)
    # "dr200" / "200" -> "dr200"
    if label == "dynamic_range":
        if key.isdigit():
            key = f"dr{key}"
        elif key in ("auto", "dr_auto"):
            key = "dr100"
        key = ALIASES.get(key, key)
    if key not in catalog:
        allowed = ", ".join(sorted(catalog))
        raise InvalidRecipe(f"unknown {label} {value!r}", hint=f"allowed: {allowed}")
    return key


def parse_slot(value: Any) -> int:
    """Accept 'C3', 'c3', '3' or 3 and return 1..7."""
    text = str(value).strip().upper().removeprefix("C")
    if not text.isdigit() or not 1 <= int(text) <= 7:
        raise InvalidRecipe(f"invalid slot {value!r}", hint="slots are C1..C7")
    return int(text)


def slot_name(slot: int) -> str:
    return f"C{slot}"


# --------------------------------------------------------------------------
# Recipe
# --------------------------------------------------------------------------


@dataclass
class WhiteBalance:
    mode: str = "auto"
    shift_r: int = 0
    shift_b: int = 0
    color_temperature: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mode": self.mode,
            "shift_r": self.shift_r,
            "shift_b": self.shift_b,
        }
        if self.color_temperature is not None:
            data["color_temperature"] = self.color_temperature
        return data


@dataclass
class Recipe:
    name: str = ""
    film_simulation: str = "classic_chrome"
    dynamic_range: str = "dr100"
    grain_effect: str = "off"
    smooth_skin: str = "off"
    color_chrome: str = "off"
    color_chrome_fx_blue: str = "off"
    white_balance: WhiteBalance = field(default_factory=WhiteBalance)
    highlight: float = 0.0
    shadow: float = 0.0
    color: float = 0.0
    sharpness: float = 0.0
    noise_reduction: int = 0
    clarity: float = 0.0
    exposure: float = 0.0
    dynamic_range_priority: int = 0
    monochrome_wc: float = 0.0
    monochrome_mg: float = 0.0
    # Empty slots on the camera read back as all-0xFFFF; we keep the flag so a
    # backup/restore round-trip does not invent values for them.
    empty: bool = False
    warnings: list[str] = field(default_factory=list)

    # -- construction ------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, validate: bool = True) -> Recipe:
        if not isinstance(data, dict):
            raise InvalidRecipe("recipe must be a JSON object")
        # Accept the catalog shape too: {"slug": ..., "recipe": {...}}.
        if "recipe" in data and isinstance(data["recipe"], dict):
            data = {**data, **data["recipe"]}
        unknown = {
            key
            for key in data
            if key
            not in {
                "name",
                "film_simulation",
                "dynamic_range",
                "grain_effect",
                "smooth_skin",
                "color_chrome",
                "color_chrome_fx_blue",
                "white_balance",
                "highlight",
                "shadow",
                "color",
                "sharpness",
                "noise_reduction",
                "clarity",
                "exposure",
                "dynamic_range_priority",
                "monochrome_wc",
                "monochrome_mg",
                "empty",
                "slug",
                "recipe",
                "author",
                "source",
                "notes",
                "tags",
                "description",
                "version",
                "recipes",
            }
        }
        if unknown:
            raise InvalidRecipe(
                f"unknown recipe field(s): {', '.join(sorted(unknown))}",
                hint="run `ozure catalog format` for the accepted fields",
            )
        wb_data = data.get("white_balance") or {}
        if isinstance(wb_data, str):
            wb_data = {"mode": wb_data}
        wb = WhiteBalance(
            mode=wb_data.get("mode", "auto"),
            shift_r=_int(wb_data.get("shift_r", 0), "white_balance.shift_r"),
            shift_b=_int(wb_data.get("shift_b", 0), "white_balance.shift_b"),
            color_temperature=(
                _int(wb_data["color_temperature"], "white_balance.color_temperature")
                if wb_data.get("color_temperature") is not None
                else None
            ),
        )
        recipe = cls(
            name=str(data.get("name", "")),
            film_simulation=str(data.get("film_simulation", "classic_chrome")),
            dynamic_range=str(data.get("dynamic_range", "dr100")),
            grain_effect=str(data.get("grain_effect", "off")),
            smooth_skin=str(data.get("smooth_skin", "off")),
            color_chrome=str(data.get("color_chrome", "off")),
            color_chrome_fx_blue=str(data.get("color_chrome_fx_blue", "off")),
            white_balance=wb,
            highlight=_num(data.get("highlight", 0), "highlight"),
            shadow=_num(data.get("shadow", 0), "shadow"),
            color=_num(data.get("color", 0), "color"),
            sharpness=_num(data.get("sharpness", 0), "sharpness"),
            noise_reduction=_int(data.get("noise_reduction", 0), "noise_reduction"),
            clarity=_num(data.get("clarity", 0), "clarity"),
            exposure=_num(data.get("exposure", 0), "exposure"),
            dynamic_range_priority=_int(
                data.get("dynamic_range_priority", 0), "dynamic_range_priority"
            ),
            monochrome_wc=_num(data.get("monochrome_wc", 0), "monochrome_wc"),
            monochrome_mg=_num(data.get("monochrome_mg", 0), "monochrome_mg"),
            empty=bool(data.get("empty", False)),
        )
        if validate:
            recipe.normalise()
        return recipe

    def normalise(self) -> None:
        """Canonicalise enums and check the values a camera will accept."""
        self.film_simulation = _canon(self.film_simulation, FILM_SIMULATIONS, "film simulation")
        self.dynamic_range = _canon(self.dynamic_range, DYNAMIC_RANGES, "dynamic range")
        self.grain_effect = _canon(self.grain_effect, GRAIN_EFFECTS, "grain effect")
        self.smooth_skin = _canon(self.smooth_skin, EFFECT_STRENGTHS, "smooth skin")
        self.color_chrome = _canon(self.color_chrome, EFFECT_STRENGTHS, "color chrome")
        self.color_chrome_fx_blue = _canon(
            self.color_chrome_fx_blue, EFFECT_STRENGTHS, "color chrome fx blue"
        )
        self.white_balance.mode = _canon(
            self.white_balance.mode, WHITE_BALANCE_MODES, "white balance mode"
        )
        self.validate()

    def validate(self) -> None:
        """Hard limits from the wire format, plus soft ranges as warnings."""
        if len(self.name.encode("utf-16-le")) // 2 > 254:
            raise InvalidRecipe("recipe name is longer than 254 characters")
        if chr(0) in self.name:
            raise InvalidRecipe("recipe name cannot contain a NUL character")
        if self.exposure:
            raise InvalidRecipe(
                "exposure is not part of the C1-C7 recipe block",
                hint="the camera has no exposure property in this block; use the dial",
            )
        if self.white_balance.mode == "color_temperature":
            if self.white_balance.color_temperature is None:
                raise InvalidRecipe(
                    "white_balance.mode is color_temperature but color_temperature is missing",
                    hint="set white_balance.color_temperature (2500..10000)",
                )
        elif self.white_balance.color_temperature is not None:
            # Harmless: the value is simply not written.
            self.white_balance.color_temperature = None

        for name, value, low, high in (
            ("white_balance.shift_r", self.white_balance.shift_r, -9, 9),
            ("white_balance.shift_b", self.white_balance.shift_b, -9, 9),
        ):
            if not low <= value <= high:
                raise InvalidRecipe(f"{name} must be between {low} and {high}")

        if self.noise_reduction not in NR_VALUES:
            raise InvalidRecipe("noise_reduction must be between -4 and 4")

        if self.dynamic_range_priority not in DR_PRIORITIES.values():
            raise InvalidRecipe(
                "dynamic_range_priority must be one of 0 (auto), 1 (DR100), "
                "2 (DR200), 32768 (DR400)"
            )
        if self.dynamic_range_priority != 0 and not any(
            "dynamic_range is ignored" in warning for warning in self.warnings
        ):
            self.warnings.append("dynamic_range is ignored while dynamic_range_priority is set")

        # Real dials end at these values on every body we know about. Beyond
        # them the camera rejects the write, so refuse locally instead.
        for name, value in (
            ("highlight", self.highlight),
            ("shadow", self.shadow),
            ("color", self.color),
            ("sharpness", self.sharpness),
            ("clarity", self.clarity),
            ("monochrome_wc", self.monochrome_wc),
            ("monochrome_mg", self.monochrome_mg),
        ):
            if abs(value) > 20:
                raise InvalidRecipe(f"{name} must be between -20 and 20")

        # Soft range: plausible on a real Fuji body. Warn, do not block.
        typical = {
            "highlight": (-2.0, 4.0),
            "shadow": (-2.0, 4.0),
            "color": (-4.0, 4.0),
            "sharpness": (-4.0, 4.0),
            "clarity": (-5.0, 5.0),
        }
        for name, (low, high) in typical.items():
            value = getattr(self, name)
            if not low <= value <= high:
                self.warnings.append(f"{name}={value} is outside the usual {low}..{high} range")
        if self.white_balance.color_temperature is not None and not (
            2500 <= self.white_balance.color_temperature <= 10000
        ):
            self.warnings.append("color_temperature outside 2500..10000 K")

    # -- views -------------------------------------------------------------

    def to_dict(self, *, include_meta: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "film_simulation": self.film_simulation,
            "dynamic_range": self.dynamic_range,
            "grain_effect": self.grain_effect,
            "smooth_skin": self.smooth_skin,
            "color_chrome": self.color_chrome,
            "color_chrome_fx_blue": self.color_chrome_fx_blue,
            "white_balance": self.white_balance.to_dict(),
            "highlight": _pretty_number(self.highlight),
            "shadow": _pretty_number(self.shadow),
            "color": _pretty_number(self.color),
            "sharpness": _pretty_number(self.sharpness),
            "noise_reduction": self.noise_reduction,
            "clarity": _pretty_number(self.clarity),
            "dynamic_range_priority": self.dynamic_range_priority,
            "monochrome_wc": _pretty_number(self.monochrome_wc),
            "monochrome_mg": _pretty_number(self.monochrome_mg),
        }
        if self.empty:
            data["empty"] = True
        if include_meta and self.warnings:
            data["warnings"] = list(self.warnings)
        return data

    def summary(self) -> str:
        if self.empty:
            return "(empty slot)"
        bits = [self.film_simulation.upper().replace("_", " ")]
        bits.append(f"HL{_signed(self.highlight)} SH{_signed(self.shadow)}")
        bits.append(f"C{_signed(self.color)} S{_signed(self.sharpness)}")
        if self.clarity:
            bits.append(f"CL{_signed(self.clarity)}")
        if self.grain_effect != "off":
            bits.append(f"GR {self.grain_effect.replace('_', ' ')}")
        return "  ".join(bits)


def _num(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidRecipe(f"{label} must be a number, got {value!r}") from exc


def _int(value: Any, label: str) -> int:
    """Integers only: 2 is fine, 2.5 is a typo we refuse to round silently."""
    number = _num(value, label)
    if number != int(number):
        raise InvalidRecipe(f"{label} must be a whole number, got {value!r}")
    return int(number)


def _pretty_number(value: float) -> float | int:
    rounded = round(float(value), 2)
    return int(rounded) if rounded == int(rounded) else rounded


def _signed(value: float) -> str:
    number = _pretty_number(value)
    return f"+{number}" if number > 0 else str(number)


# --------------------------------------------------------------------------
# Wire codecs (mirror of fuji-ptp-core's read/write conversions)
# --------------------------------------------------------------------------

GRAIN_FROM_WIRE = {
    1: "off",
    6: "off",  # older firmware
    7: "off",  # X100VI stores Off as 7
    2: "weak_small",
    3: "strong_small",
    4: "weak_large",
    5: "strong_large",
}
STRENGTH_FROM_WIRE = {1: "off", 2: "weak", 3: "strong"}
FILM_FROM_WIRE = {value: key for key, value in FILM_SIMULATIONS.items()}
DR_FROM_WIRE = {100: "dr100", 200: "dr200", 400: "dr400", 0: "dr100"}
WB_FROM_WIRE = {
    2: "auto",
    0x8020: "auto",
    4: "daylight",
    6: "incandescent",
    8: "underwater",
    0x8001: "fluorescent_1",
    0x8002: "fluorescent_2",
    0x8003: "fluorescent_3",
    0x8006: "shade",
    0x8007: "color_temperature",
    0x8021: "ambience_priority",
}


def dial(value: float) -> int:
    """Convert a dial value to tenths: 0.5 -> 5, -1.5 -> -15.

    Rounds half away from zero, like the Rust core, so 0.25 -> 3 and never
    depends on the platform's banker's rounding.
    """
    scaled = float(value) * 10
    rounded = math.floor(abs(scaled) + 0.5)
    return int(rounded if scaled >= 0 else -rounded)


def from_dial(raw: int) -> float:
    return round(raw / 10.0, 2)


def u16(value: int) -> bytes:
    return int(value).to_bytes(2, "little", signed=False)


def i16(value: int) -> bytes:
    return int(value).to_bytes(2, "little", signed=True)


def unpack_u16(data: bytes) -> int:
    if len(data) != 2:
        raise InvalidRecipe(f"expected a 16-bit property value, got {len(data)} bytes")
    return int.from_bytes(data, "little", signed=False)


def recipe_from_props(name: str, props: list[int]) -> Recipe:
    """Decode the 19-word property block (0xD190..0xD1A2) into a Recipe."""
    if len(props) != 19:
        raise InvalidRecipe(f"expected 19 properties, got {len(props)}")
    if props[0] == 0xFFFF:
        recipe = Recipe(name=name, empty=True)
        return recipe

    def enum(table: dict[int, str], value: int, label: str) -> str:
        if value not in table:
            raise InvalidRecipe(
                f"{label} has an unknown value 0x{value:04X}",
                hint="this body or firmware may use a newer value",
            )
        return table[value]

    def signed(value: int) -> int:
        return value - 0x10000 if value >= 0x8000 else value

    if props[17] not in NR_FROM_WIRE:
        raise InvalidRecipe(f"high ISO NR has an unknown value 0x{props[17]:04X}")

    def mono_word(value: int) -> float:
        # 0xFFFF means "never written": bodies leave the monochrome words
        # untouched on colour simulations. Do not surface -0.1 for that.
        return 0.0 if value == 0xFFFF else from_dial(signed(value))

    recipe = Recipe(
        name=name,
        dynamic_range=enum(DR_FROM_WIRE, props[0], "dynamic range"),
        dynamic_range_priority=props[1],
        film_simulation=enum(FILM_FROM_WIRE, props[2], "film simulation"),
        monochrome_wc=mono_word(props[3]),
        monochrome_mg=mono_word(props[4]),
        grain_effect=enum(GRAIN_FROM_WIRE, props[5], "grain effect"),
        color_chrome=enum(STRENGTH_FROM_WIRE, props[6], "color chrome"),
        color_chrome_fx_blue=enum(STRENGTH_FROM_WIRE, props[7], "color chrome fx blue"),
        smooth_skin=enum(STRENGTH_FROM_WIRE, props[8], "smooth skin"),
        highlight=from_dial(signed(props[13])),
        shadow=from_dial(signed(props[14])),
        color=from_dial(signed(props[15])),
        sharpness=from_dial(signed(props[16])),
        noise_reduction=NR_FROM_WIRE[props[17]],
        clarity=from_dial(signed(props[18])),
        white_balance=WhiteBalance(
            mode=enum(WB_FROM_WIRE, props[9], "white balance"),
            shift_r=signed(props[10]),
            shift_b=signed(props[11]),
            # The temperature field is only meaningful in that mode; other
            # modes leave whatever the body had there (often 0).
            color_temperature=(
                props[12] if WB_FROM_WIRE.get(props[9]) == "color_temperature" else None
            ),
        ),
    )
    return recipe


def ptp_name(data: bytes) -> str:
    """Decode a PTP string: [count][UTF-16LE chars][NUL]."""
    if not data:
        raise InvalidRecipe("empty PTP string")
    count = data[0]
    if count == 0:
        if len(data) == 1:
            return ""
        raise InvalidRecipe("malformed empty PTP string")
    if len(data) != 1 + count * 2 or data[-2:] != b"\x00\x00":
        raise InvalidRecipe("malformed PTP string")
    try:
        return data[1:-2].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise InvalidRecipe("PTP string is not valid UTF-16LE") from exc


def ptp_name_bytes(name: str) -> bytes:
    units = name.encode("utf-16-le")
    count = len(units) // 2
    if count > 254:
        raise InvalidRecipe("recipe name is longer than 254 characters")
    return bytes([count + 1]) + units + b"\x00\x00"
