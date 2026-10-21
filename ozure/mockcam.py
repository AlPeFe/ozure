"""A simulated Fujifilm body that speaks the same PTP containers.
It exists for two reasons: the test suite must not need a camera, and the demo
animation has to show a real CLI talking to something. State is plain JSON so
anyone can inspect or seed it.
"""

from __future__ import annotations

import json
import struct
import time
from pathlib import Path
from typing import Any

from .errors import ProtocolError
from .fuji import PROPS
from .ptp import (
    CONTAINER_COMMAND,
    CONTAINER_DATA,
    CONTAINER_RESPONSE,
    OP_CLOSE_SESSION,
    OP_GET_DEVICE_INFO,
    OP_GET_DEVICE_PROP_VALUE,
    OP_OPEN_SESSION,
    OP_SET_DEVICE_PROP_VALUE,
    RESPONSE_OK,
)
from .recipe import (
    DYNAMIC_RANGES,
    EFFECT_STRENGTHS,
    FILM_SIMULATIONS,
    GRAIN_EFFECTS,
    NR_VALUES,
    WHITE_BALANCE_MODES,
    Recipe,
    dial,
    ptp_name_bytes,
)

PROP_SLOT_CURSOR = 0xD18C
PROP_SLOT_NAME = 0xD18D
RESPONSE_ERROR = 0x2002
RESPONSE_DEVICE_PROP_NOT_SUPPORTED = 0x200B
RESPONSE_INVALID_PARAMETER = 0x201D


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
def props_from_recipe(recipe: Recipe) -> list[int]:
    """Encode a Recipe into the 19-word property block."""
    if recipe.empty:
        return [0xFFFF] * 19
    values = [
        DYNAMIC_RANGES[recipe.dynamic_range],
        recipe.dynamic_range_priority,
        FILM_SIMULATIONS[recipe.film_simulation],
        dial(recipe.monochrome_wc) & 0xFFFF,
        dial(recipe.monochrome_mg) & 0xFFFF,
        GRAIN_EFFECTS[recipe.grain_effect],
        EFFECT_STRENGTHS[recipe.color_chrome],
        EFFECT_STRENGTHS[recipe.color_chrome_fx_blue],
        EFFECT_STRENGTHS[recipe.smooth_skin],
        WHITE_BALANCE_MODES[recipe.white_balance.mode],
        recipe.white_balance.shift_r & 0xFFFF,
        recipe.white_balance.shift_b & 0xFFFF,
        recipe.white_balance.color_temperature or 0,
        dial(recipe.highlight) & 0xFFFF,
        dial(recipe.shadow) & 0xFFFF,
        dial(recipe.color) & 0xFFFF,
        dial(recipe.sharpness) & 0xFFFF,
        NR_VALUES[recipe.noise_reduction],
        dial(recipe.clarity) & 0xFFFF,
    ]
    return values


def state_from_recipes(
    model: str, recipes: list[Recipe], *, missing_props: list[int] | None = None, **meta: Any
) -> dict[str, Any]:
    if len(recipes) != 7:
        raise ValueError("a Fujifilm body always has seven custom slots")
    return {
        "model": model,
        "manufacturer": "FUJIFILM",
        "firmware": meta.get("firmware", "2.10"),
        "serial": meta.get("serial", "0X0000000"),
        "cursor": 1,
        "missing_props": list(missing_props or []),
        "slots": [
            {"name": recipe.name, "props": props_from_recipe(recipe), "empty": recipe.empty}
            for recipe in recipes
        ],
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _ptp_string(text: str) -> bytes:
    encoded = text.encode("utf-16-le")
    return bytes([len(encoded) // 2 + 1]) + encoded + b"\x00\x00"


def _device_info_payload(state: dict[str, Any]) -> bytes:
    payload = struct.pack("<HIH", 100, 0x0CB5, 100)
    payload += _ptp_string("FUJIFILM PTP extension")
    payload += struct.pack("<H", 0)  # FunctionalMode: standard
    for count in (8, 0, 0, 0, 0):  # operations, events, props, capture, image
        payload += struct.pack("<I", count * 2) + b"\x00" * (count * 2)
    payload += _ptp_string(state.get("manufacturer", "FUJIFILM"))
    payload += _ptp_string(state.get("model", "X100VI"))
    payload += _ptp_string(state.get("firmware", "1.00"))
    payload += _ptp_string(state.get("serial", "0X0000000"))
    return payload


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------
class MockCameraTransport:
    """In-process camera. Implements the `Transport` protocol."""

    def __init__(
        self,
        state: dict[str, Any],
        *,
        delay: float = 0.0,
        state_path: Path | None = None,
    ):
        self.state = state
        self.delay = delay
        self.state_path = state_path
        self.outbox: list[bytes] = []
        self.sent_props: list[tuple[int, bytes]] = []
        self._pending_set: tuple[int, int, int] | None = None
        self.sessions = 0
        self.closed_sessions = 0

    # -- Transport ---------------------------------------------------------
    def describe(self) -> str:
        suffix = " (simulated)" if self.state_path else ""
        return f"{self.state.get('model', 'Fujifilm')}{suffix}"

    def save(self) -> None:
        if self.state_path is not None:
            save_state(self.state_path, self.state)

    def send(self, data: bytes) -> None:
        if len(data) < 12:
            raise ProtocolError("short container from the host")
        length, kind, code, tx = struct.unpack("<IHHI", data[:12])
        payload = data[12:length]
        if kind == CONTAINER_COMMAND:
            self._handle_command(code, tx, payload)
        elif kind == CONTAINER_DATA:
            self._handle_data(code, tx, payload)
        else:
            raise ProtocolError(f"host sent an unexpected container type {kind}")

    def receive(self) -> bytes:
        if self.delay:
            time.sleep(self.delay)
        if not self.outbox:
            raise ProtocolError("the simulated camera has nothing to say")
        return self.outbox.pop(0)

    # -- protocol ----------------------------------------------------------
    def _handle_command(self, op: int, tx: int, payload: bytes) -> None:
        if op == OP_OPEN_SESSION:
            self.sessions += 1
            self._response(tx, RESPONSE_OK)
        elif op == OP_CLOSE_SESSION:
            self.closed_sessions += 1
            self._response(tx, RESPONSE_OK)
        elif op == OP_GET_DEVICE_INFO:
            self._data(op, tx, _device_info_payload(self.state))
            self._response(tx, RESPONSE_OK)
        elif op == OP_GET_DEVICE_PROP_VALUE:
            (prop,) = struct.unpack("<I", payload[:4])
            self._get_prop(prop, tx)
        elif op == OP_SET_DEVICE_PROP_VALUE:
            (prop,) = struct.unpack("<I", payload[:4])
            self._pending_set = (prop, tx, 0)
        else:
            self._response(tx, RESPONSE_ERROR)

    def _handle_data(self, op: int, tx: int, payload: bytes) -> None:
        if op != OP_SET_DEVICE_PROP_VALUE or self._pending_set is None:
            self._response(tx, RESPONSE_ERROR)
            return
        prop, pending_tx, _ = self._pending_set
        self._pending_set = None
        code = self._set_prop(prop, payload)
        self._response(pending_tx, code)

    def _get_prop(self, prop: int, tx: int) -> None:
        if prop in self.state.get("missing_props", []):
            self._response(tx, RESPONSE_DEVICE_PROP_NOT_SUPPORTED)
            return
        if prop == PROP_SLOT_CURSOR:
            self._data(OP_GET_DEVICE_PROP_VALUE, tx, struct.pack("<H", self.state["cursor"]))
        elif prop == PROP_SLOT_NAME:
            slot = self._current_slot()
            self._data(OP_GET_DEVICE_PROP_VALUE, tx, ptp_name_bytes(slot["name"]))
        elif prop in PROPS:
            index = PROPS.index(prop)
            slot = self._current_slot()
            value = slot["props"][index]
            self._data(OP_GET_DEVICE_PROP_VALUE, tx, struct.pack("<H", value & 0xFFFF))
        else:
            self._response(tx, RESPONSE_DEVICE_PROP_NOT_SUPPORTED)
            return
        self._response(tx, RESPONSE_OK)

    def _set_prop(self, prop: int, payload: bytes) -> int:
        self.sent_props.append((prop, payload))
        if prop in self.state.get("missing_props", []):
            return RESPONSE_DEVICE_PROP_NOT_SUPPORTED
        if prop == PROP_SLOT_NAME:
            if not payload:
                return RESPONSE_INVALID_PARAMETER
            text = (
                ""
                if payload[0] == 0
                else payload[1:].decode("utf-16-le", errors="replace").rstrip("\x00")
            )
            self._current_slot()["name"] = text
            return RESPONSE_OK
        if len(payload) != 2:
            return RESPONSE_INVALID_PARAMETER
        value = struct.unpack("<H", payload[:2])[0]
        if prop == PROP_SLOT_CURSOR:
            if not 1 <= value <= 7:
                return RESPONSE_INVALID_PARAMETER
            self.state["cursor"] = value
            return RESPONSE_OK
        if prop in PROPS:
            index = PROPS.index(prop)
            slot = self._current_slot()
            # Writing into a slot that was empty just replaces the 0xFFFF
            # placeholders one by one, like a real body filling the block.
            slot["props"][index] = value
            slot["empty"] = False
            # Real X100VI firmware normalises Grain Off to wire value 7.
            is_grain_off = prop == PROPS[5] and value == 1
            if is_grain_off and self.state.get("model", "").startswith("X100"):
                slot["props"][index] = 7
            return RESPONSE_OK
        return RESPONSE_DEVICE_PROP_NOT_SUPPORTED

    # -- helpers -----------------------------------------------------------
    def _current_slot(self) -> dict[str, Any]:
        return self.state["slots"][self.state["cursor"] - 1]

    def _response(self, tx: int, code: int) -> None:
        self.outbox.append(struct.pack("<IHHI", 12, CONTAINER_RESPONSE, code, tx))

    def _data(self, op: int, tx: int, payload: bytes) -> None:
        self.outbox.append(
            struct.pack("<IHHI", 12 + len(payload), CONTAINER_DATA, op, tx) + payload
        )


def create_transport(state_path: Path, *, delay: float = 0.0) -> MockCameraTransport:
    return MockCameraTransport(load_state(state_path), delay=delay, state_path=state_path)
