"""Fujifilm recipe operations on top of the PTP session.

This is the Python mirror of `fuji-ptp-core`'s `FujiPtp` struct: same property
block, same write order (name first — it is what gets dropped when a write is
truncated), same model-specific guards.
"""

from __future__ import annotations

import contextlib
from typing import Any

from .errors import ProtocolError, TransportFailure
from .ptp import PtpSession
from .recipe import (
    DYNAMIC_RANGES,
    EFFECT_STRENGTHS,
    FILM_SIMULATIONS,
    GRAIN_EFFECTS,
    MONO_FILM_SIMULATIONS,
    NR_VALUES,
    SLOTS,
    WHITE_BALANCE_MODES,
    Recipe,
    dial,
    i16,
    ptp_name,
    ptp_name_bytes,
    recipe_from_props,
    u16,
    unpack_u16,
)
from .transport import Transport

SET_DEVICE_PROP_VALUE = 0x1016
GET_DEVICE_PROP_VALUE = 0x1015
PROP_SLOT_CURSOR = 0xD18C
PROP_SLOT_NAME = 0xD18D
PRESET_BLOCK_START = 0xD18E
PRESET_BLOCK_END = 0xD1A5

DR = 0xD190
DR_PRIORITY = 0xD191
FILM = 0xD192
MONO_WC = 0xD193
MONO_MG = 0xD194
GRAIN = 0xD195
COLOR_CHROME = 0xD196
FX_BLUE = 0xD197
SMOOTH = 0xD198
WB = 0xD199
WB_R = 0xD19A
WB_B = 0xD19B
TEMP = 0xD19C
HIGHLIGHT = 0xD19D
SHADOW = 0xD19E
COLOR = 0xD19F
SHARPNESS = 0xD1A0
NR = 0xD1A1
CLARITY = 0xD1A2

PROPS = (
    DR,
    DR_PRIORITY,
    FILM,
    MONO_WC,
    MONO_MG,
    GRAIN,
    COLOR_CHROME,
    FX_BLUE,
    SMOOTH,
    WB,
    WB_R,
    WB_B,
    TEMP,
    HIGHLIGHT,
    SHADOW,
    COLOR,
    SHARPNESS,
    NR,
    CLARITY,
)

#: Properties that are legitimately absent on some bodies (older firmware has
#: no clarity, non colour-temperature bodies may not expose the temperature
#: word). A failure here must not abort the whole slot.
OPTIONAL_PROPS = frozenset({TEMP, MONO_WC, MONO_MG, CLARITY})

OPTIONAL_LABELS = {
    TEMP: "white balance temperature",
    MONO_WC: "monochrome WC",
    MONO_MG: "monochrome MG",
    CLARITY: "clarity",
}


class FujiPtp:
    def __init__(self, transport: Transport, *, session_id: int = 1):
        self.transport = transport
        self.session_id = session_id
        self.session = PtpSession(transport)
        self.camera: dict[str, Any] = {}
        self._opened = False

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> FujiPtp:
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> dict[str, Any]:
        self.session.open_session(self.session_id)
        self._opened = True
        try:
            info = self.session.get_device_info()
        except ProtocolError:
            info = {}
        self.camera = {
            **{key: value for key, value in info.items() if value},
            "transport": self.transport.describe(),
        }
        return self.camera

    def close(self) -> None:
        if not self._opened:
            return
        self._opened = False
        # Closing a session must never mask the real result.
        with contextlib.suppress(ProtocolError, TransportFailure):
            self.session.close_session()

    # -- primitives --------------------------------------------------------

    def select_slot(self, slot: int) -> None:
        if not 1 <= slot <= 7:
            raise ProtocolError(f"slot {slot} is out of range (1..7)")
        self.session.set_device_prop_value(PROP_SLOT_CURSOR, u16(slot))

    def get(self, prop: int) -> bytes:
        return self.session.get_device_prop_value(prop)

    def set(self, prop: int, value: bytes) -> None:
        self.session.set_device_prop_value(prop, value)

    def read_slot_name(self, slot: int) -> str:
        self.select_slot(slot)
        return ptp_name(self.get(PROP_SLOT_NAME))

    # -- read --------------------------------------------------------------

    def read_slot(self, slot: int) -> Recipe:
        self.select_slot(slot)
        name = ptp_name(self.get(PROP_SLOT_NAME))
        words: list[int] = []
        missing: list[str] = []
        for prop in PROPS:
            try:
                words.append(unpack_u16(self.get(prop)))
            except (ProtocolError, TransportFailure) as exc:
                if prop in OPTIONAL_PROPS:
                    words.append(0)
                    missing.append(OPTIONAL_LABELS.get(prop, f"0x{prop:04X}"))
                    continue
                raise ProtocolError(
                    f"could not read property 0x{prop:04X} of C{slot}: {exc.message}"
                ) from exc
        recipe = recipe_from_props(name, words)
        if missing:
            recipe.warnings.append("unavailable on this body: " + ", ".join(missing))
        return recipe

    def read_profile(self) -> list[Recipe]:
        return [self.read_slot(slot) for slot in range(1, 8)]

    # -- write -------------------------------------------------------------

    def _set_name(self, name: str) -> None:
        self.set(PROP_SLOT_NAME, ptp_name_bytes(name))

    def _set_optional(self, prop: int, value: bytes, warnings: list[str]) -> None:
        """Write a property the body may not know about.

        Older firmware lacks clarity and some bodies ignore the temperature
        word unless the white balance is set to colour temperature. The write
        is attempted, and a refusal becomes a warning instead of losing the
        rest of the recipe half-written.
        """
        try:
            self.set(prop, value)
        except ProtocolError as exc:
            warnings.append(
                f"{OPTIONAL_LABELS.get(prop, f'property 0x{prop:04X}')} was not accepted "
                f"by this body ({exc.message})"
            )

    def _write_settings(self, recipe: Recipe, warnings: list[str]) -> None:
        self.set(FILM, u16(FILM_SIMULATIONS[recipe.film_simulation]))
        self.set(DR_PRIORITY, u16(recipe.dynamic_range_priority))
        if recipe.dynamic_range_priority == 0:
            self.set(DR, u16(DYNAMIC_RANGES[recipe.dynamic_range]))
        mono = recipe.film_simulation in MONO_FILM_SIMULATIONS
        if mono:
            self._set_optional(MONO_WC, i16(dial(recipe.monochrome_wc)), warnings)
            self._set_optional(MONO_MG, i16(dial(recipe.monochrome_mg)), warnings)
        self.set(GRAIN, u16(GRAIN_EFFECTS[recipe.grain_effect]))
        # Colour-only controls: the camera rejects them on monochrome sims.
        if not mono:
            self.set(COLOR_CHROME, u16(EFFECT_STRENGTHS[recipe.color_chrome]))
            self.set(FX_BLUE, u16(EFFECT_STRENGTHS[recipe.color_chrome_fx_blue]))
        self.set(SMOOTH, u16(EFFECT_STRENGTHS[recipe.smooth_skin]))
        self.set(WB, u16(WHITE_BALANCE_MODES[recipe.white_balance.mode]))
        if not mono:
            self.set(WB_R, i16(recipe.white_balance.shift_r))
            self.set(WB_B, i16(recipe.white_balance.shift_b))
        if recipe.white_balance.mode == "color_temperature":
            self._set_optional(TEMP, u16(recipe.white_balance.color_temperature or 5600), warnings)
        for prop, value in (
            (HIGHLIGHT, recipe.highlight),
            (SHADOW, recipe.shadow),
            (COLOR, recipe.color),
            (SHARPNESS, recipe.sharpness),
        ):
            self.set(prop, i16(dial(value)))
        self._set_optional(CLARITY, i16(dial(recipe.clarity)), warnings)
        self.set(NR, u16(NR_VALUES[recipe.noise_reduction]))

    def write_recipe(self, slot: int, recipe: Recipe, *, write_name: bool = True) -> list[str]:
        """Write one complete recipe into one slot.

        The name goes first on purpose: it is the property the camera tends to
        drop when a write is interrupted. Returns the warnings collected from
        controls this body does not accept.
        """
        if recipe.empty:
            raise ProtocolError(
                "refusing to write an empty recipe",
                hint="an empty slot has no settings to restore; pick a real recipe",
            )
        warnings: list[str] = []
        self.select_slot(slot)
        if write_name:
            self._set_name(recipe.name)
        self._write_settings(recipe, warnings)
        return warnings

    def write_name(self, slot: int, name: str) -> None:
        self.select_slot(slot)
        self._set_name(name)

    # -- views -------------------------------------------------------------

    def slots(self) -> list[str]:
        return list(SLOTS)
