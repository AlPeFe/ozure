# PyInstaller spec: one self-contained `ozure` binary per OS.
#
#   python -m pip install pyinstaller pyusb
#   pyinstaller tools/ozure.spec
#
# The catalogs MUST travel with the binary: the whole point is that a stranger
# can list 126 recipes without a repo checkout.

from pathlib import Path

ROOT = Path(SPECPATH).parent
SEP = ";" if __import__("sys").platform.startswith("win") else ":"

a = Analysis(
    [str(ROOT / "tools" / "ozure_entry.py")],
    pathex=[str(ROOT)],
    hiddenimports=["usb.core", "usb.util", "usb.backend.libusb1"],
    datas=[(str(ROOT / "ozure" / "data" / "catalog"), "ozure/data/catalog")],
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
