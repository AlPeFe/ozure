# PyInstaller spec: one self-contained `ozure` binary per OS.
#
#   python -m pip install pyinstaller pyusb
#   pyinstaller tools/ozure.spec
#
# The catalogs MUST travel with the binary: the whole point is that a stranger
# can list 126 recipes without a repo checkout.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
SEP = ";" if __import__("sys").platform.startswith("win") else ":"

# libusb-package ships the native DLL; without it the binary can import pyusb but
# has no backend, which looks like "the camera is not there".
libusb_datas, libusb_binaries, libusb_hidden = collect_all("libusb_package")

a = Analysis(
    [str(ROOT / "tools" / "ozure_entry.py")],
    pathex=[str(ROOT)],
    hiddenimports=[
        "usb.core",
        "usb.util",
        "usb.backend.libusb1",
        "libusb_package",
        *libusb_hidden,
    ],
    datas=[
        (str(ROOT / "ozure" / "data" / "catalog"), "ozure/data/catalog"),
        *libusb_datas,
    ],
    binaries=[*libusb_binaries],
    excludes=["tkinter", "unittest", "pydoc", "email", "http", "xml"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="ozure",
    console=True,
    upx=False,
    strip=False,
)
