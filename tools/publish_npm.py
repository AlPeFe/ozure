"""Publish the npm packages in the only order that works.

    python tools/publish_npm.py --dry-run      # show what would go out
    python tools/publish_npm.py                # platform packages, then the launcher

Two flows are supported, because npm now hands out stage-only tokens:

* plain `npm publish` (classic token or an interactive 2FA session);
* staged publishing: `npm stage publish` writes the version to the registry in a
  pending state and a maintainer promotes it with `npm stage approve <id>`
  (that step needs proof-of-presence, i.e. 2FA in your own terminal).

The script detects the second case automatically and prints the approve commands
in the right order.

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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
NPM = ROOT / "npm"


def manifest(directory: Path) -> dict:
    return json.loads((directory / "package.json").read_text(encoding="utf-8"))


STAGE_HINT = ("stage-only", "npm stage publish", "staged publish", "staged")


def run_publish(directory: Path, npm: str, otp: str, *, stage: bool) -> tuple[int, str]:
    command = [npm, "publish", "--access", "public"]
    if stage:
        command = [npm, "stage", "publish", ".", "--access", "public"]
    if otp:
        command.append(f"--otp={otp}")
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, check=False)
    output = (result.stdout or "") + (result.stderr or "")
    print(output.strip()[-1200:] or "(no output)")
    return result.returncode, output


def staged_list(npm: str) -> list[dict]:
    result = subprocess.run(
        [npm, "stage", "list", "--json"], capture_output=True, text=True, check=False
    )
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("staged", []) or data.get("items", [])
    return [item for item in data if isinstance(item, dict)]


def approve(npm: str, *, dry_run: bool) -> int:
    """Promote staged versions, smallest blast radius first: binaries, then the
    launcher that points at them."""
    staged = staged_list(npm)
    if not staged:
        print("nothing staged: run tools/publish_npm.py --stage first")
        return 1
    # binaries first (they carry os/cpu), the launcher last: it points at them
    order = sorted(
        staged,
        key=lambda item: (item.get("packageName") or "").endswith("/ozure"),
    )
    for item in order:
        stage_id = item.get("stageId") or item.get("stage_id") or item.get("id")
        name = item.get("packageName") or item.get("name")
        version = item.get("version")
        if not stage_id:
            continue
        print(f"approve {name}@{version}  ({stage_id})")
        if dry_run:
            continue
        result = subprocess.run([npm, "stage", "approve", stage_id], check=False)
        if result.returncode != 0:
            print(f"approval failed for {name}", file=sys.stderr)
            return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the commands only")
    parser.add_argument(
        "--otp",
        default="",
        help="one-time password from the authenticator; npm reuses it for both publishes",
    )
    parser.add_argument(
        "--stage",
        action="store_true",
        help="use staged publishing from the start (npm stage publish)",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="approve everything that is staged (needs 2FA: run it in your terminal)",
    )
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

    if args.approve:
        return approve(npm, dry_run=args.dry_run)

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
    staged: list[str] = []
    for directory in queue:
        data = manifest(directory)
        print(NL + f"== {data['name']}@{data['version']}  ({directory.relative_to(ROOT)})")
        if args.dry_run:
            stage_flag = "stage " if args.stage else ""
            print(f"   {npm} {stage_flag}publish --access public")
            continue
        code, output = run_publish(directory, npm, args.otp, stage=args.stage)
        if code == 0:
            continue
        if not args.stage and any(hint in output.lower() for hint in STAGE_HINT):
            print(NL + "registry wants a staged publish; retrying with `npm stage publish`...")
            code, output = run_publish(directory, npm, args.otp, stage=True)
        # The staging endpoint answers 403 "request timeout" now and then; it is
        # a transient registry hiccup, not a permission problem.
        attempts = 0
        while code != 0 and "request timeout" in output.lower() and attempts < 3:
            attempts += 1
            print(NL + f"registry timeout while staging; retry {attempts}/3 in a few seconds...")
            time.sleep(5)
            code, output = run_publish(directory, npm, args.otp, stage=True)
        if code != 0:
            print(f"failed while publishing {data['name']}", file=sys.stderr)
            return code
        staged.append(f"{data['name']}@{data['version']}")

    if staged:
        print(NL + "staged (not public yet): " + ", ".join(staged))
        print("a maintainer promotes each one, with 2FA:")
        found = False
        for item in staged_list(npm):
            name = item.get("packageName") or item.get("name")
            version = item.get("version")
            stage_id = item.get("stageId") or item.get("stage_id") or item.get("id")
            if name and stage_id:
                found = True
                print(f"  npm stage approve {stage_id}    # {name}@{version}")
        if not found:
            print("  npm stage list                 # copy the ids from here")

    if not args.dry_run and not staged:
        print(NL + "done. Check with:")
        print(f"  npm view {launcher_name} version")
        print(f"  npm install -g {launcher_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
