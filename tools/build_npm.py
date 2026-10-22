"""Build and package the npm distribution of ozure.

Layout (the esbuild pattern: one tiny JS launcher + one package per platform):

    npm/ozure                    @microck/ozure            (bin shim)
    npm/ozure-win32-x64          .../ozure-win32-x64       (ozure.exe)
    npm/ozure-darwin-arm64       ...                       (filled by CI)
    ...

    python tools/build_npm.py                 # build the local platform binary
    python tools/build_npm.py --pack          # + npm pack every ready package
    python tools/build_npm.py --scope alpefe  # different npm scope

Publishing (needs `npm login`):

    npm publish npm/ozure-win32-x64 --access public
    npm publish npm/ozure --access public
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NPM = ROOT / "npm"
PYPROJECT = ROOT / "pyproject.toml"

PLATFORMS = {
    ("win32", "x64"): "ozure-win32-x64",
    ("win32", "arm64"): "ozure-win32-arm64",
    ("darwin", "arm64"): "ozure-darwin-arm64",
    ("darwin", "x64"): "ozure-darwin-x64",
    ("linux", "x64"): "ozure-linux-x64",
    ("linux", "arm64"): "ozure-linux-arm64",
}


def version() -> str:
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("version ="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("no version in pyproject.toml")


def local_platform() -> tuple[str, str]:
    system = {"windows": "win32", "darwin": "darwin", "linux": "linux"}.get(
        platform.system().lower(), sys.platform
    )
    machine = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(platform.machine().lower(), platform.machine().lower())
    return system, machine


def stamp(scope: str, ver: str) -> None:
    """Rewrite the launcher manifest and create/stamp the platform ones."""
    launcher = NPM / "ozure" / "package.json"
    data = json.loads(launcher.read_text(encoding="utf-8"))
    data["name"] = f"@{scope}/ozure"
    data["version"] = ver
    data["optionalDependencies"] = {
        f"@{scope}/{name}": ver for name in PLATFORMS.values()
    }
    launcher.write_text(json.dumps(data, indent=2) + chr(10), encoding="utf-8")

    for name in PLATFORMS.values():
        suffix = name.removeprefix("ozure-")
        system, arch = suffix.split("-", 1)
        directory = NPM / name
        directory.mkdir(parents=True, exist_ok=True)
        manifest = directory / "package.json"
        platform_data = (
            json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
        )
        platform_data.update(
            {
                "name": f"@{scope}/{name}",
                "version": ver,
                "description": f"ozure binary for {system} {arch}",
                "os": [system],
                "cpu": [arch],
                "files": ["bin"],
                "license": "MIT",
                "homepage": "https://github.com/AlPeFe/ozure",
                "repository": {
                    "type": "git",
                    "url": "git+https://github.com/AlPeFe/ozure.git",
                },
            }
        )
        manifest.write_text(json.dumps(platform_data, indent=2) + chr(10), encoding="utf-8")

    shim = NPM / "ozure" / "bin" / "ozure.js"
    source = shim.read_text(encoding="utf-8").replace("@microck/", f"@{scope}/")
    shim.write_text(source, encoding="utf-8")


def build_binary() -> Path:
    print("building the standalone binary with PyInstaller...")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "tools/ozure.spec"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    produced = ROOT / "dist" / "ozure.exe"
    if not produced.exists():
        produced = ROOT / "dist" / "ozure"
    if not produced.exists():
        raise SystemExit("PyInstaller did not produce dist/ozure[.exe]")
    return produced


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", default="microck", help="npm scope, without the @")
    parser.add_argument("--pack", action="store_true", help="npm pack ready packages")
    parser.add_argument("--skip-build", action="store_true", help="reuse dist/ozure*")
    args = parser.parse_args()

    ver = version()
    stamp(args.scope, ver)
    print(f"stamped @{args.scope}/ozure {ver}")

    system, machine = local_platform()
    name = PLATFORMS.get((system, machine))
    if not name:
        print(f"no npm platform package for {system}-{machine}; stamping only")
    else:
        binary = (ROOT / "dist" / "ozure.exe") if system == "win32" else (ROOT / "dist" / "ozure")
        if not args.skip_build and not binary.exists():
            binary = build_binary()
        target = NPM / name / "bin" / ("ozure.exe" if system == "win32" else "ozure")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, target)
        if system != "win32":
            target.chmod(0o755)
        print(f"copied {binary.name} -> {target.relative_to(ROOT)} ({target.stat().st_size // 1024} kB)")

    ready = [
        directory
        for directory in (NPM / "ozure", *[NPM / value for value in PLATFORMS.values()])
        if directory.is_dir() and (directory / "bin").exists()
    ]
    print("ready to publish:", ", ".join(str(directory.name) for directory in ready))

    if args.pack:
        npm = shutil.which("npm") or "npm"
        for directory in ready:
            subprocess.run([npm, "pack", "--silent"], cwd=directory, check=True)
            print(f"packed {directory.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
