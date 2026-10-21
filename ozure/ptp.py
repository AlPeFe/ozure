"""PTP containers and the transaction machine.

Only the handful of operations Fujifilm needs are implemented:
OpenSession, CloseSession, GetDeviceInfo, GetDevicePropValue and
SetDevicePropValue. Wire layout is the standard PTP/IP-less USB layout used by
fuji-ptp-core.
"""

from __future__ import annotations

import struct
from typing import Any

from .errors import ProtocolError, TransportFailure
from .transport import Transport

CONTAINER_COMMAND = 1
CONTAINER_DATA = 2
CONTAINER_RESPONSE = 3

OP_GET_DEVICE_INFO = 0x1001
OP_OPEN_SESSION = 0x1002
OP_CLOSE_SESSION = 0x1003
OP_GET_DEVICE_PROP_VALUE = 0x1015
OP_SET_DEVICE_PROP_VALUE = 0x1016

RESPONSE_OK = 0x2001
RESPONSE_NAMES = {
    0x2001: "OK",
    0x2002: "GeneralError",
    0x2003: "SessionNotOpen",
    0x2004: "InvalidTransactionID",
    0x2005: "OperationNotSupported",
    0x2006: "ParameterNotSupported",
    0x2007: "IncompleteTransfer",
    0x2009: "InvalidStorageID",
    0x200A: "InvalidObjectHandle",
    0x200B: "DevicePropNotSupported",
    0x200C: "InvalidObjectFormatCode",
    0x200F: "DeviceBusy",
    0x2019: "DevicePropNotSupported",
    0x201D: "InvalidParameter",
    0xA002: "FujiError",
}


def _container(kind: int, code: int, tx: int, payload: bytes = b"") -> bytes:
    return struct.pack("<IHHI", 12 + len(payload), kind, code, tx) + payload


def parse_container(packet: bytes, expected_kind: int, expected_code: int, tx: int) -> bytes:
    if len(packet) < 12:
        raise ProtocolError(
            f"short PTP container ({len(packet)} bytes)",
            hint="the camera may still be in a non-PTP USB mode",
        )
    length, kind, code, received_tx = struct.unpack("<IHHI", packet[:12])
    if length < 12 or length > len(packet):
        raise ProtocolError(f"malformed PTP container length {length}")
    if kind != expected_kind:
        raise ProtocolError(f"expected container type {expected_kind}, got {kind}")
    if code != expected_code:
        raise ProtocolError(f"expected operation 0x{expected_code:04X}, got 0x{code:04X}")
    if received_tx != tx:
        raise ProtocolError(f"transaction mismatch: expected {tx}, got {received_tx}")
    return packet[12:length]


def parse_response(packet: bytes, tx: int) -> int:
    if len(packet) < 12:
        raise ProtocolError(f"short PTP response ({len(packet)} bytes)")
    _length, kind, code, received_tx = struct.unpack("<IHHI", packet[:12])
    if kind != CONTAINER_RESPONSE:
        raise ProtocolError(f"expected a response container, got type {kind}")
    if received_tx != tx:
        raise ProtocolError(f"transaction mismatch: expected {tx}, got {received_tx}")
    if code != RESPONSE_OK:
        name = RESPONSE_NAMES.get(code, "Unknown")
        raise ProtocolError(
            f"camera rejected the operation with 0x{code:04X} ({name})",
            hint="some properties are model/firmware specific; try fewer changes",
        )
    return code


def parse_ptp_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read a PTP string from `data` at `offset`; returns (text, next offset)."""
    if offset >= len(data):
        raise ProtocolError("PTP string runs past the end of the payload")
    count = data[offset]
    begin = offset + 1
    end = begin + count * 2
    if end > len(data):
        raise ProtocolError("PTP string is truncated")
    raw = data[begin:end]
    try:
        text = raw.decode("utf-16-le").rstrip("\x00") if count else ""
    except UnicodeDecodeError as exc:
        raise ProtocolError("PTP string is not valid UTF-16LE") from exc
    return text, end


def parse_device_info(payload: bytes) -> dict[str, Any]:
    """Extract the interesting fields from a DeviceInfo dataset.

    Everything here is best effort: some bodies skip fields, so a parse error
    must never stop us from talking to the camera.
    """
    info: dict[str, Any] = {}
    try:
        offset = 0
        # StandardVersion, VendorExtensionID, VendorExtensionVersion
        offset += 2 + 4 + 2
        _, offset = parse_ptp_string(payload, offset)  # vendor extension description
        offset += 2  # FunctionalMode
        for _ in range(5):  # Operations, Events, Properties, CaptureFormats, ImageFormats
            (length,) = struct.unpack("<I", payload[offset : offset + 4])
            offset += 4 + length
        manufacturer, offset = parse_ptp_string(payload, offset)
        model, offset = parse_ptp_string(payload, offset)
        version, offset = parse_ptp_string(payload, offset)
        serial, offset = parse_ptp_string(payload, offset)
        info = {
            "manufacturer": manufacturer,
            "model": model,
            "firmware": version,
            "serial": serial,
        }
    except (struct.error, IndexError, ProtocolError):
        pass
    return info


class PtpSession:
    def __init__(self, transport: Transport):
        self.transport = transport
        self.transaction_id = 0

    # -- plumbing ----------------------------------------------------------

    def _next_tx(self) -> int:
        self.transaction_id += 1
        return self.transaction_id

    def _send(self, data: bytes) -> None:
        try:
            self.transport.send(data)
        except TransportFailure:
            raise
        except OSError as exc:  # pyusb raises OSError subclasses
            raise TransportFailure(str(exc), hint="is the camera still plugged in?") from exc

    def _receive(self) -> bytes:
        try:
            return self.transport.receive()
        except TransportFailure:
            raise
        except OSError as exc:
            raise TransportFailure(str(exc), hint="USB read failed") from exc

    # -- operations --------------------------------------------------------

    def open_session(self, session_id: int = 1) -> None:
        tx = self._next_tx()
        self._send(
            _container(CONTAINER_COMMAND, OP_OPEN_SESSION, tx, struct.pack("<I", session_id))
        )
        parse_response(self._receive(), tx)

    def close_session(self) -> None:
        tx = self._next_tx()
        self._send(_container(CONTAINER_COMMAND, OP_CLOSE_SESSION, tx))
        parse_response(self._receive(), tx)

    def get_device_info(self) -> dict[str, Any]:
        tx = self._next_tx()
        self._send(_container(CONTAINER_COMMAND, OP_GET_DEVICE_INFO, tx))
        payload = parse_container(self._receive(), CONTAINER_DATA, OP_GET_DEVICE_INFO, tx)
        parse_response(self._receive(), tx)
        return parse_device_info(payload)

    def get_device_prop_value(self, prop: int) -> bytes:
        tx = self._next_tx()
        self._send(
            _container(CONTAINER_COMMAND, OP_GET_DEVICE_PROP_VALUE, tx, struct.pack("<I", prop))
        )
        payload = parse_container(self._receive(), CONTAINER_DATA, OP_GET_DEVICE_PROP_VALUE, tx)
        parse_response(self._receive(), tx)
        return payload

    def set_device_prop_value(self, prop: int, value: bytes) -> None:
        tx = self._next_tx()
        self._send(
            _container(CONTAINER_COMMAND, OP_SET_DEVICE_PROP_VALUE, tx, struct.pack("<I", prop))
        )
        self._send(_container(CONTAINER_DATA, OP_SET_DEVICE_PROP_VALUE, tx, value))
        parse_response(self._receive(), tx)
