"""Publish the npm packages in the only order that works.

    python tools/publish_npm.py --dry-run      # show what would go out
    python tools/publish_npm.py                # platform packages, then the launcher

npm asks for a one-time password when the account has 2FA enabled for
publishing. Either type it when prompted, or put an **Automation** token in
~/.npmrc (Account -> Access Tokens -> Automation: it bypasses 2FA, which is also
what CI needs):

    //registry.npmjs.org/:_authToken=npm_XXXXXXXX

Platform packages must be published first: the launcher lists them in
optionalDependencies, and npm resolves those at install time.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NPM = ROOT / "npm"


def manifest(directory: Path) -> dict:
    return json.loads((directory / "package.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the commands only")
    args = parser.parse_args()

    npm = shutil.which("npm") or "npm"
    try:
        whoami = subprocess.run(
            [npm, "whoami"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except FileNotFoundError:
        print("npm is not installed", file=sys.stderr)
        return 1
    if not whoami:
        print("not logged in: run `npm login` first", file=sys.stderr)
        return 1

    launcher = NPM / "ozure"
    launcher_name = manifest(launcher)["name"]
    print(f"npm user: {whoami} · publishing {launcher_name} {manifest(launcher)['version']}")

    platforms = sorted(
        directory
        for directory in NPM.iterdir()
        if directory.is_dir() and directory.name.startswith("ozure-")
    )
    ready = [directory for directory in platforms if (directory / "bin").exists()]
    missing = [directory.name for directory in platforms if directory not in ready]
    for name in missing:
        print(f"  skip {name}: no binary yet (CI builds it)")

    if not ready:
        print(
            "no platform package has a binary; run tools/build_npm.py first",
            file=sys.stderr,
        )
        return 1

    queue = [*ready, launcher]
    for directory in queue:
        data = manifest(directory)
        command = [npm, "publish", "--access", "public"]
        printable = " ".join(command)
        print(f"\n== {data['name']}@{data['version']}  ({directory.relative_to(ROOT)})")
        if args.dry_run:
            print(f"   {printable}")
            continue
        result = subprocess.run(command, cwd=directory, check=False)
        if result.returncode != 0:
            print(f"failed while publishing {data['name']}", file=sys.stderr)
            return result.returncode

    if not args.dry_run:
        print("\ndone. Check with:")
        print(f"  npm view {launcher_name} version")
        print(f"  npm install -g {launcher_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
