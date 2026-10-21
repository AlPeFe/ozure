"""Transports: real USB (pyusb) and an in-process fake for tests and demos.

`Transport` is intentionally tiny — send a PTP container, receive one — so the
protocol layer never knows whether it is talking to a camera or a simulator.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import Any, Protocol

from .errors import CameraNotFound, TransportFailure

FUJI_VENDOR_ID = 0x04CB
PTP_INTERFACE_CLASS = 0x06
PTP_INTERFACE_SUBCLASS = 0x01
PTP_INTERFACE_PROTOCOL = 0x01
DEFAULT_TIMEOUT_MS = 5000
MAX_CONTAINER = 64 * 1024 * 1024


class Transport(Protocol):
    def send(self, data: bytes) -> None: ...

    def receive(self) -> bytes: ...

    def describe(self) -> str: ...


# --------------------------------------------------------------------------
# USB
# --------------------------------------------------------------------------


def _load_usb():
    try:
        import usb.core
        import usb.util
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise TransportFailure(
            "pyusb is not installed",
            hint="pip install pyusb  (ozure needs it to talk to the camera)",
        ) from exc
    return usb


def _backend():
    """Find a libusb backend, including the one shipped by libusb-package."""
    import usb.backend.libusb1 as libusb1

    backend = libusb1.get_backend()
    if backend is not None:
        return backend
    try:  # pragma: no cover - optional convenience dependency
        import libusb_package

        backend = libusb_package.get_libusb1_backend()
    except Exception:
        backend = None
    return backend


def _find(**kwargs):
    usb = _load_usb()
    backend = _backend()
    try:
        return usb.core.find(backend=backend, **kwargs)
    except usb.core.NoBackendError as exc:  # pragma: no cover - environment
        raise TransportFailure(
            "no USB backend available",
            hint="install libusb: pip install libusb-package (or the libusb-1.0 package "
            "of your OS)",
        ) from exc


class UsbTransport:
    """Fujifilm PTP camera over USB bulk transfers."""

    def __init__(self, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self.timeout_ms = timeout_ms
        self.device = None
        self.interface_number = 0
        self.ep_in = None
        self.ep_out = None
        self._detached_kernel_driver = False
        self.description = ""

    # -- discovery ---------------------------------------------------------

    @staticmethod
    def find_devices() -> list[dict[str, Any]]:
        """List Fujifilm PTP interfaces without opening them."""
        usb = _load_usb()
        found: list[dict[str, Any]] = []
        devices = _find(idVendor=FUJI_VENDOR_ID, find_all=True)
        for device in devices:
            try:
                model = usb.util.get_string(device, device.iProduct) or ""
            except Exception:
                model = ""
            try:
                serial = usb.util.get_string(device, device.iSerialNumber) or ""
            except Exception:
                serial = ""
            entry: dict[str, Any] = {
                "bus": int(device.bus),
                "address": int(device.address),
                "vendor_id": f"{device.idVendor:04X}",
                "product_id": f"{device.idProduct:04X}",
                "product": model,
                "serial": serial,
                "ptp_interface": None,
                "problem": None,
            }
            try:
                config = device.get_active_configuration()
                interfaces = list(config)
            except Exception as exc:
                entry["problem"] = f"no active configuration ({exc})"
                found.append(entry)
                continue
            matching = [intf for intf in interfaces if intf.bInterfaceClass == PTP_INTERFACE_CLASS]
            if not matching:
                entry["problem"] = "device is not in USB RAW CONV./BACKUP RESTORE mode"
            else:
                intf = matching[0]
                entry["ptp_interface"] = int(intf.bInterfaceNumber)
                entry["endpoints"] = [
                    {"address": hex(int(ep.bEndpointAddress)), "type": int(ep.bmAttributes) & 3}
                    for ep in intf
                    if (int(ep.bmAttributes) & 3) == 2  # bulk
                ]
            found.append(entry)
        return found

    @classmethod
    def open(
        cls,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        wait_seconds: float = 0.0,
        on_wait: Callable[[float], None] | None = None,
    ) -> UsbTransport:
        """Open the first Fujifilm PTP interface, polling for up to `wait_seconds`."""
        deadline = time.monotonic() + max(0.0, wait_seconds)
        last_error: str | None = None
        while True:
            try:
                return cls._open_once(timeout_ms)
            except CameraNotFound as exc:
                last_error = exc.message
            if time.monotonic() >= deadline:
                raise CameraNotFound(
                    last_error or "no Fujifilm camera found",
                    hint="set USB RAW CONV./BACKUP RESTORE on the camera, then retry",
                )
            if on_wait:
                on_wait(max(0.0, deadline - time.monotonic()))
            time.sleep(0.5)

    @classmethod
    def _open_once(cls, timeout_ms: int) -> UsbTransport:
        _load_usb()
        if not _find(find_all=True):
            raise CameraNotFound("no USB devices visible")
        for entry in cls.find_devices():
            if entry.get("ptp_interface") is None:
                continue
            device = _find(
                idVendor=FUJI_VENDOR_ID,
                custom_match=lambda d, bus=entry["bus"], address=entry["address"]: (
                    int(d.bus) == bus and int(d.address) == address
                ),
            )
            if device is None:
                continue
            transport = cls(timeout_ms=timeout_ms)
            transport._claim(device, int(entry["ptp_interface"]), entry)
            return transport
        raise CameraNotFound(
            "found a Fujifilm device but no PTP interface",
            hint="camera menu -> USB RAW CONV./BACKUP RESTORE; on Windows install "
            "WinUSB for 'USB PTP Camera' with Zadig",
        )

    def _claim(self, device, interface_number: int, entry: dict[str, Any]) -> None:
        usb = _load_usb()
        self.device = device
        self.interface_number = interface_number
        with contextlib.suppress(Exception):
            device.set_configuration()
        # Linux only: the PTP driver may hold the interface.
        try:
            if device.is_kernel_driver_active(interface_number):
                device.detach_kernel_driver(interface_number)
                self._detached_kernel_driver = True
        except (NotImplementedError, AttributeError):
            pass
        except Exception as exc:
            raise TransportFailure(f"cannot detach the kernel driver: {exc}") from exc
        try:
            usb.util.claim_interface(device, interface_number)
        except Exception as exc:
            raise TransportFailure(
                f"cannot claim the PTP interface: {exc}",
                hint="on Windows install WinUSB with Zadig; on Linux fix udev permissions",
            ) from exc
        config = device.get_active_configuration()
        intf = config[(interface_number, 0)]
        for endpoint in intf:
            if int(endpoint.bmAttributes) & 3 != 2:
                continue
            if endpoint.bEndpointAddress & 0x80:
                self.ep_in = endpoint
            else:
                self.ep_out = endpoint
        if self.ep_in is None or self.ep_out is None:
            raise TransportFailure("PTP interface has no bulk IN/OUT endpoint pair")
        for endpoint in (self.ep_in, self.ep_out):
            with contextlib.suppress(Exception):
                endpoint.timeout = self.timeout_ms
        product = entry.get("product") or ""
        self.description = (
            f"{product or 'Fujifilm camera'} (bus {entry['bus']} addr {entry['address']})"
        )

    # -- transfers ---------------------------------------------------------

    def send(self, data: bytes) -> None:
        try:
            self.ep_out.write(data, self.timeout_ms)
        except OSError as exc:
            raise TransportFailure(f"USB write failed: {exc}") from exc

    def receive(self) -> bytes:
        header = self._read(12)
        length = int.from_bytes(header[0:4], "little")
        if not 12 <= length <= MAX_CONTAINER:
            raise TransportFailure(f"camera announced an implausible packet size ({length})")
        packet = bytearray(header)
        while len(packet) < length:
            packet.extend(self._read(length - len(packet)))
        return bytes(packet)

    def _read(self, size: int) -> bytes:
        try:
            chunk = self.ep_in.read(size, self.timeout_ms)
        except OSError as exc:
            raise TransportFailure(f"USB read failed: {exc}") from exc
        data = bytes(chunk)
        if not data:
            raise TransportFailure("camera closed the USB pipe")
        return data

    def describe(self) -> str:
        return self.description or "Fujifilm camera"

    def close(self) -> None:
        usb = _load_usb()
        if self.device is None:
            return
        with contextlib.suppress(Exception):
            usb.util.release_interface(self.device, self.interface_number)
        if self._detached_kernel_driver:
            with contextlib.suppress(Exception):
                self.device.attach_kernel_driver(self.interface_number)
        with contextlib.suppress(Exception):
            usb.util.dispose_resources(self.device)
        self.device = None


# --------------------------------------------------------------------------
# In-memory transport for the unit tests
# --------------------------------------------------------------------------


class MockTransport:
    """Records sent containers and replays queued packets."""

    def __init__(self, packets: list[bytes] | None = None):
        self.sent: list[bytes] = []
        self.packets: list[bytes] = list(packets or [])
        self.name = "mock"

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def receive(self) -> bytes:
        if not self.packets:
            raise TransportFailure("mock transport has no more packets")
        return self.packets.pop(0)

    def describe(self) -> str:
        return self.name
