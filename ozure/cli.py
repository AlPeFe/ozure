"""Command line interface.

Design rules that the skill depends on:

* Every command works with ``--mock`` against a simulated body, so the skill can
  be exercised (and demoed) without hardware.
* Every command has a ``--json`` mode with a stable envelope.
* Writes never happen without ``--yes``; without it the CLI prints the plan and
  exits with code 10.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__, ui
from .catalog import CatalogRecipe, find, load_catalog, resolve_catalog_dir
from .errors import DryRun, OzureError, UsageError
from .fuji import FujiPtp
from .mockcam import MockCameraTransport, create_transport, save_state, state_from_recipes
from .recipe import MONO_FILM_SIMULATIONS, Recipe, parse_slot, slot_name
from .transport import UsbTransport

JSON_SCHEMA_VERSION = 1


# --------------------------------------------------------------------------
# Home / state paths
# --------------------------------------------------------------------------


def ozure_home() -> Path:
    override = os.environ.get("OZURE_HOME")
    return Path(override) if override else Path.home() / ".ozure"


def mock_state_path(args: argparse.Namespace) -> Path:
    return Path(args.mock_state) if args.mock_state else ozure_home() / "mock-camera.json"


def backup_dir() -> Path:
    return ozure_home() / "backups"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# --------------------------------------------------------------------------
# Output envelope
# --------------------------------------------------------------------------


class Output:
    def __init__(self, as_json: bool, command: str):
        self.as_json = as_json
        self.command = command
        self.data: dict[str, Any] = {}

    def set(self, **values: Any) -> None:
        self.data.update(values)

    def finish(self) -> None:
        if self.as_json:
            ui.emit_json(
                {
                    "ok": True,
                    "schema": JSON_SCHEMA_VERSION,
                    "command": self.command,
                    "version": __version__,
                    "data": self.data,
                }
            )


# --------------------------------------------------------------------------
# Camera plumbing
# --------------------------------------------------------------------------


def seed_mock_state(path: Path) -> None:
    """Create a plausible camera: seven slots filled from the catalog."""
    recipes: list[Recipe] = []
    catalog_dir = resolve_catalog_dir(None)
    try:
        bundled = load_catalog(catalog_dir)
    except OzureError:
        bundled = []
    for entry in bundled[:7]:
        recipe = Recipe.from_dict(entry.recipe.to_dict())
        recipe.name = entry.name
        recipes.append(recipe)
    defaults = [
        ("PROVIA BASE", {}),
        ("VELVIA POP", {"film_simulation": "velvia", "color": 1.5, "sharpness": 1.0}),
        ("CLASSIC CHROME", {"film_simulation": "classic_chrome", "grain_effect": "weak_small"}),
        ("ACROS +R", {"film_simulation": "acros_r", "highlight": 1.0, "shadow": 1.0}),
        ("ETERNA CINEMA", {"film_simulation": "eterna", "highlight": -1.0, "shadow": 1.5}),
        ("PRO NEG HI", {"film_simulation": "pro_neg_hi", "color": -1.0}),
        ("", {"empty": True}),
    ]
    for name, overrides in defaults:
        if len(recipes) >= 7:
            break
        recipe = Recipe.from_dict({"name": name, **overrides})
        recipe.name = name or ""
        recipes.append(recipe)
    recipes = (recipes + [Recipe(name="") for _ in range(7)])[:7]
    save_state(
        path,
        state_from_recipes("X100VI", recipes, firmware="2.10", serial="0XK42011"),
    )


@contextlib.contextmanager
def camera(args: argparse.Namespace) -> Iterator[tuple[FujiPtp, Any]]:
    transport: Any
    if args.mock:
        path = mock_state_path(args)
        if not path.exists():
            seed_mock_state(path)
        transport = create_transport(path, delay=args.mock_delay)
    else:
        transport = UsbTransport.open(
            timeout_ms=args.timeout * 1000,
            wait_seconds=args.wait,
            on_wait=lambda remaining: ui.step(
                f"waiting for a Fujifilm camera... ({remaining:.0f}s left)"
            ),
        )
    fuji = FujiPtp(transport)
    try:
        fuji.open()
        yield fuji, transport
    finally:
        fuji.close()
        if isinstance(transport, MockCameraTransport):
            transport.save()
        else:
            transport.close()


class CameraArgs:
    """Flags shared by every command that talks to the camera."""

    @staticmethod
    def add(parser: argparse.ArgumentParser) -> None:
        group = parser.add_argument_group("camera")
        group.add_argument(
            "--mock",
            action="store_true",
            help="use a simulated camera instead of USB (no hardware needed)",
        )
        group.add_argument(
            "--mock-state",
            metavar="PATH",
            help="JSON file backing the simulated camera (default: ~/.ozure/mock-camera.json)",
        )
        group.add_argument(
            "--mock-delay",
            type=float,
            default=0.0,
            help="seconds of simulated latency per transfer (nice for demos)",
        )
        group.add_argument(
            "--wait",
            type=float,
            default=0.0,
            help="keep polling for a camera for this many seconds before giving up",
        )
        group.add_argument(
            "--timeout",
            type=float,
            default=5.0,
            help="USB transfer timeout in seconds (default: 5)",
        )


# --------------------------------------------------------------------------
# Commands: doctor / connect
# --------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace, out: Output) -> None:
    usb_ok = True
    usb_error = None
    try:
        import usb  # noqa: F401
    except ImportError as exc:
        usb_ok = False
        usb_error = str(exc)

    catalog_dir = resolve_catalog_dir(args.catalog)
    try:
        catalog = load_catalog(catalog_dir)
        catalog_error = None
    except OzureError as exc:
        catalog = []
        catalog_error = exc.message

    devices: list[dict[str, Any]] = []
    if usb_ok:
        try:
            devices = UsbTransport.find_devices()
        except Exception as exc:
            devices = [{"problem": str(exc)}]

    payload = {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pyusb": usb_ok,
        "pyusb_error": usb_error,
        "usb_devices": devices,
        "catalog_dir": str(catalog_dir),
        "catalog_recipes": len(catalog),
        "catalog_error": catalog_error,
        "home": str(ozure_home()),
    }
    out.set(**payload)

    if not args.json:
        print(ui.paint(f"ozure {__version__}", ui.BOLD))
        print(f"  python      {payload['python']} ({payload['platform']})")
        print(f"  pyusb       {'ok' if usb_ok else ui.paint('missing', ui.RED)}")
        print(f"  catalog     {len(catalog)} recipes in {catalog_dir}")
        if catalog_error:
            print(ui.paint(f"  catalog err {catalog_error}", ui.RED))
        if devices:
            print("  usb         ")
            for device in devices:
                if device.get("problem"):
                    print(f"    - {device.get('product') or 'device'}: {device['problem']}")
                else:
                    name = device.get("product") or "Fujifilm device"
                    state = (
                        f"PTP iface {device['ptp_interface']}"
                        if device.get("ptp_interface") is not None
                        else "no PTP interface"
                    )
                    identifiers = f"{device['vendor_id']}:{device['product_id']}"
                    print(f"    - {name} [{identifiers}] {state}")
        else:
            print("  usb         no Fujifilm device visible")
        if not devices:
            print(
                ui.paint(
                    "  next        plug the camera in, choose USB RAW CONV./BACKUP RESTORE",
                    ui.GREY,
                )
            )
    out.finish()


def cmd_connect(args: argparse.Namespace, out: Output) -> None:
    with camera(args) as (fuji, transport):
        camera_info = dict(fuji.camera)
        recipes = fuji.read_profile()
    slots = [
        {
            "slot": slot_name(index + 1),
            "name": recipe.name,
            "empty": recipe.empty,
        }
        for index, recipe in enumerate(recipes)
    ]
    out.set(connected=True, camera=camera_info, slots=slots)
    if not args.json:
        model = camera_info.get("model") or transport.describe()
        ui.ok(f"connected to {ui.paint(model, ui.BOLD)}")
        details = [
            f"{key}={value}"
            for key, value in camera_info.items()
            if key in {"firmware", "serial", "manufacturer"} and value
        ]
        if details:
            print(ui.paint("  " + "  ".join(details), ui.GREY))
        print()
        print(
            ui.table(
                ["slot", "name", "state"],
                [
                    (entry["slot"], entry["name"] or "—", "empty" if entry["empty"] else "ready")
                    for entry in slots
                ],
            )
        )
        print()
        print(ui.paint("next: ozure list --json", ui.GREY))
    out.finish()


# --------------------------------------------------------------------------
# Commands: list / show
# --------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace, out: Output) -> None:
    with camera(args) as (fuji, _transport):
        camera_info = dict(fuji.camera)
        recipes = fuji.read_profile()
    rows = [
        {
            "slot": slot_name(index + 1),
            "name": recipe.name,
            "empty": recipe.empty,
            "film_simulation": None if recipe.empty else recipe.film_simulation,
            "summary": recipe.summary(),
            "recipe": recipe.to_dict(),
        }
        for index, recipe in enumerate(recipes)
    ]
    out.set(camera=camera_info, slots=rows)
    if not args.json:
        print(
            ui.table(
                ["slot", "name", "film", "settings"],
                [
                    (
                        row["slot"],
                        row["name"] or "—",
                        row["film_simulation"] or "—",
                        row["summary"] if not row["empty"] else ui.paint("empty", ui.GREY),
                    )
                    for row in rows
                ],
            )
        )
    out.finish()


RECIPE_FIELDS = [
    "film_simulation",
    "dynamic_range",
    "dynamic_range_priority",
    "grain_effect",
    "color_chrome",
    "color_chrome_fx_blue",
    "smooth_skin",
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "noise_reduction",
    "clarity",
    "monochrome_wc",
    "monochrome_mg",
    "white_balance",
]


def cmd_show(args: argparse.Namespace, out: Output) -> None:
    wanted = [parse_slot(value) for value in args.slots] if args.slots else [1, 2, 3, 4, 5, 6, 7]
    with camera(args) as (fuji, _transport):
        recipes = {slot: fuji.read_slot(slot) for slot in wanted}
    payload = []
    for slot, recipe in recipes.items():
        payload.append(
            {
                "slot": slot_name(slot),
                "empty": recipe.empty,
                "recipe": recipe.to_dict(include_meta=True),
            }
        )
    out.set(slots=payload)
    if not args.json:
        for index, (slot, recipe) in enumerate(recipes.items()):
            if index:
                print()
            title = f"{slot_name(slot)}  {recipe.name or '(no name)'}"
            print(ui.paint(title, ui.BOLD))
            if recipe.empty:
                print(ui.paint("  empty slot", ui.GREY))
                continue
            for field in RECIPE_FIELDS:
                value = getattr(recipe, field)
                if field == "white_balance":
                    wb = recipe.white_balance
                    text = f"{wb.mode} R{wb.shift_r:+d} B{wb.shift_b:+d}"
                    if wb.color_temperature:
                        text += f" {wb.color_temperature}K"
                    value = text
                elif isinstance(value, float):
                    value = f"{value:+g}"
                print(f"  {field.ljust(22)} {value}")
            for warning in recipe.warnings:
                ui.warn(f"{slot_name(slot)}: {warning}")
    out.finish()


# --------------------------------------------------------------------------
# Commands: writes
# --------------------------------------------------------------------------


def save_backup(slot: int, recipe: Recipe, *, directory: Path | None = None) -> Path:
    directory = directory or backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{timestamp()}-{slot_name(slot)}.json"
    path.write_text(
        json.dumps(
            {"slot": slot_name(slot), "recipe": recipe.to_dict()}, indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def diff_recipes(before: Recipe, after: Recipe) -> list[tuple[str, Any, Any]]:
    left = before.to_dict()
    right = after.to_dict()
    changes: list[tuple[str, Any, Any]] = []
    for key in left:
        if key == "name":
            continue
        lv, rv = left[key], right[key]
        if lv != rv:
            changes.append((key, _flatten(lv), _flatten(rv)))
    if after.name and before.name != after.name:
        changes.insert(0, ("name", before.name or "—", after.name))
    return changes


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key}={item}" for key, item in value.items() if item is not None)
    return str(value)


def _plan_and_maybe_stop(
    args: argparse.Namespace,
    out: Output,
    *,
    title: str,
    plan: dict[str, Any],
    changes: list[tuple[str, Any, Any]],
) -> None:
    """Show the plan and stop with exit code 10 unless --yes was passed."""
    out.set(
        **plan,
        changes=[{"field": f, "before": b, "after": a} for f, b, a in changes],
        written=False,
    )
    if args.yes:
        return
    if not args.json:
        print(ui.paint(title, ui.BOLD))
        print(ui.render_diff(changes))
        print()
        print(ui.paint("dry run — re-run with --yes to write to the camera", ui.YELLOW))
    raise DryRun("dry run: nothing was written")


def _verify(expected: Recipe, actual: Recipe, *, compare_name: bool = True) -> list[str]:
    """Fields the camera did not keep. Controls that the body silently ignores
    are excluded: on monochrome simulations it keeps the colour-only values and
    the white balance shift that were already stored."""
    wanted = expected.to_dict()
    got = actual.to_dict()
    if not compare_name:
        wanted.pop("name", None)
        got.pop("name", None)
    if expected.film_simulation in MONO_FILM_SIMULATIONS:
        for field in ("color_chrome", "color_chrome_fx_blue"):
            wanted.pop(field, None)
        if isinstance(wanted.get("white_balance"), dict) and isinstance(
            got.get("white_balance"), dict
        ):
            wanted["white_balance"] = {"mode": wanted["white_balance"].get("mode")}
            got["white_balance"] = {"mode": got["white_balance"].get("mode")}
    return [field for field, value in wanted.items() if got.get(field) != value]


def _write_and_verify(
    fuji: FujiPtp,
    slot: int,
    recipe: Recipe,
    args: argparse.Namespace,
    out: Output,
    *,
    write_name: bool,
) -> None:
    if not args.no_backup:
        out.set(backup=str(save_backup(slot, fuji.read_slot(slot))))
    fuji.write_recipe(slot, recipe, write_name=write_name)
    verified = fuji.read_slot(slot)
    mismatches = _verify(recipe, verified, compare_name=write_name)
    out.set(verified=verified.to_dict(), written=True, mismatches=mismatches)
    if not args.json:
        ui.ok(f"wrote {slot_name(slot)}")
        if mismatches:
            ui.warn(f"camera returned different values for: {', '.join(mismatches)}")
        elif out.data.get("backup"):
            print(ui.paint(f"  backup: {out.data['backup']}", ui.GREY))


def cmd_set(args: argparse.Namespace, out: Output) -> None:
    slot = parse_slot(args.slot)
    overrides: dict[str, Any] = {}
    for raw in args.field or []:
        if "=" not in raw:
            raise UsageError(f"--field expects key=value, got {raw!r}")
        key, value = raw.split("=", 1)
        overrides[key.strip()] = _coerce(value.strip())
    overrides.update({k: v for k, v in vars(args).items() if k in RECIPE_FIELDS and v is not None})
    if args.name is not None:
        overrides["name"] = args.name
    if not overrides:
        raise UsageError("nothing to change", hint="pass --field key=value or a named flag")
    if "name" in overrides and args.name is None:
        args.name = str(overrides["name"])

    with camera(args) as (fuji, _transport):
        before = fuji.read_slot(slot)
        merged = before.to_dict()
        merged.pop("empty", None) if before.empty else None
        merged.update(overrides)
        after = Recipe.from_dict(merged)
        for warning in after.warnings:
            ui.warn(warning)
        changes = diff_recipes(before, after)
        _plan_and_maybe_stop(
            args,
            out,
            title=f"plan for {slot_name(slot)} ({'empty slot' if before.empty else before.name})",
            plan={"slot": slot_name(slot), "recipe": after.to_dict(), "camera": fuji.camera},
            changes=changes,
        )
        if not args.json:
            print(ui.render_diff(changes))
            print()
        _write_and_verify(fuji, slot, after, args, out, write_name="name" in overrides)
    out.finish()


def cmd_apply(args: argparse.Namespace, out: Output) -> None:
    slot = parse_slot(args.slot)
    source, entry = _load_reference(args.recipe, args.catalog)
    recipe = Recipe.from_dict(entry.recipe.to_dict())
    recipe.name = entry.name
    if args.name:
        recipe.name = args.name
    if args.keep_name:
        recipe.name = ""
    for warning in recipe.warnings:
        ui.warn(warning)

    with camera(args) as (fuji, _transport):
        before = fuji.read_slot(slot)
        changes = diff_recipes(before, recipe)
        _plan_and_maybe_stop(
            args,
            out,
            title=f"plan: {entry.name} → {slot_name(slot)} ({'empty' if before.empty else before.name})",
            plan={
                "slot": slot_name(slot),
                "source": str(source),
                "slug": entry.slug,
                "recipe": recipe.to_dict(),
                "camera": fuji.camera,
            },
            changes=changes,
        )
        if not args.json:
            print(ui.render_diff(changes))
            print()
        _write_and_verify(fuji, slot, recipe, args, out, write_name=not args.keep_name)
    out.finish()


def _coerce(value: str) -> Any:
    """Turn a --field value into the type the catalog schema expects."""
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if text[:1] in {"{", "["}:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise UsageError(f"invalid JSON in --field: {exc.msg}") from exc
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def _load_reference(reference: str, catalog_dir: str | None) -> tuple[Path | str, CatalogRecipe]:
    path = Path(reference).expanduser()
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "recipes" in data:
            raise UsageError(
                f"{path.name} contains several recipes",
                hint="point at a single-recipe file or use the catalog slug",
            )
        entry = _entry_from_file(data, path.name)
        return path, entry
    catalog = load_catalog(resolve_catalog_dir(catalog_dir))
    return f"catalog:{resolve_catalog_dir(catalog_dir)}", find(catalog, reference)


def _entry_from_file(data: dict[str, Any], fallback_name: str) -> CatalogRecipe:
    if "recipe" in data:
        payload = data
    else:
        payload = {
            "recipe": {
                key: value
                for key, value in data.items()
                if key
                not in {"slug", "author", "source", "notes", "tags", "description", "version"}
            }
        }
    name = str(data.get("name") or Path(fallback_name).stem)
    return CatalogRecipe(
        slug=str(data.get("slug") or name.lower().replace(" ", "-")),
        name=name,
        recipe=Recipe.from_dict(payload),
        author=data.get("author"),
        source=data.get("source"),
        notes=data.get("notes"),
        tags=list(data.get("tags") or []),
    )


# --------------------------------------------------------------------------
# Commands: backup / restore / catalog
# --------------------------------------------------------------------------


def cmd_backup(args: argparse.Namespace, out: Output) -> None:
    with camera(args) as (fuji, _transport):
        camera_info = dict(fuji.camera)
        recipes = fuji.read_profile()
    if args.out:
        target = Path(args.out).expanduser()
        if target.is_dir() or str(args.out).endswith(os.sep):
            target.mkdir(parents=True, exist_ok=True)
            target = target / f"{timestamp()}-ozure.json"
    else:
        backup_dir().mkdir(parents=True, exist_ok=True)
        target = backup_dir() / f"{timestamp()}-profile.json"
    payload = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "camera": camera_info,
        "slots": {slot_name(index + 1): recipe.to_dict() for index, recipe in enumerate(recipes)},
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out.set(path=str(target), camera=camera_info, slots=payload["slots"])
    if not args.json:
        ui.ok(f"backup written to {target}")
    out.finish()


def cmd_restore(args: argparse.Namespace, out: Output) -> None:
    source = Path(args.file).expanduser()
    if not source.is_file():
        raise UsageError(f"no such backup: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    slots = payload.get("slots") or {}
    if not slots:
        raise UsageError(f"{source.name} has no slots")
    plan: dict[str, Any] = {"source": str(source), "slots": []}
    with camera(args) as (fuji, _transport):
        for slot_text, data in slots.items():
            slot = parse_slot(slot_text)
            recipe = Recipe.from_dict(data)
            before = fuji.read_slot(slot)
            plan["slots"].append(
                {
                    "slot": slot_name(slot),
                    "name": recipe.name,
                    "changes": len(diff_recipes(before, recipe)),
                }
            )
        if not args.yes:
            out.set(**plan, written=False)
            if not args.json:
                for entry in plan["slots"]:
                    print(f"{entry['slot']}  {entry['name'] or '—'}  {entry['changes']} change(s)")
                print()
                print(ui.paint("dry run — re-run with --yes to write to the camera", ui.YELLOW))
            raise DryRun("dry run: nothing was written")
        for slot_text, data in slots.items():
            slot = parse_slot(slot_text)
            recipe = Recipe.from_dict(data)
            if not args.no_backup:
                save_backup(slot, fuji.read_slot(slot))
            fuji.write_recipe(slot, recipe)
        verified = fuji.read_profile()
        out.set(
            **plan,
            written=True,
            verified={slot_name(i + 1): r.to_dict() for i, r in enumerate(verified)},
        )
        if not args.json:
            ui.ok(f"restored {len(slots)} slot(s) from {source.name}")
    out.finish()


def cmd_catalog(args: argparse.Namespace, out: Output) -> None:
    if args.catalog_command == "format":
        text = FORMAT_DOC.strip()
        out.set(format=text)
        if not args.json:
            print(text)
        out.finish()
        return
    directory = resolve_catalog_dir(args.catalog)
    catalog = load_catalog(directory)
    if args.catalog_command == "list":
        matches = [entry for entry in catalog if entry.matches(args.query or "")]
        out.set(
            directory=str(directory),
            count=len(matches),
            recipes=[entry.to_dict() for entry in matches],
        )
        if not args.json:
            if not matches:
                print(ui.paint(f"no recipes in {directory}", ui.GREY))
            else:
                print(
                    ui.table(
                        ["slug", "name", "film", "tags"],
                        [
                            (entry.slug, entry.name, entry.film, ",".join(entry.tags))
                            for entry in matches
                        ],
                    )
                )
                print()
                print(ui.paint(f"{len(matches)} recipe(s) in {directory}", ui.GREY))
        out.finish()
        return
    if args.catalog_command == "show":
        entry = find(catalog, args.ref)
        out.set(recipe=entry.to_dict())
        if not args.json:
            print(ui.paint(entry.name, ui.BOLD) + ui.paint(f"  ({entry.slug})", ui.GREY))
            if entry.notes:
                print(f"  {entry.notes}")
            if entry.author or entry.source:
                print(ui.paint(f"  {entry.author or ''} {entry.source or ''}".rstrip(), ui.GREY))
            print()
            print(json.dumps(entry.recipe.to_dict(), indent=2, ensure_ascii=False))
        out.finish()
        return
    raise UsageError("unknown catalog command")


FORMAT_DOC = """
Catalog file format
===================

A catalog is a directory of .json files. Each file holds one recipe or a list:

  {"version": 1, "recipes": [ {...}, {...} ]}

One recipe:

  {
    "slug": "portra-400",          # stable id, used by `ozure apply portra-400`
    "name": "Portra 400",          # becomes the C1..C7 name on the camera
    "author": "who made it",       # optional
    "source": "https://...",       # optional
    "notes": "why it works",       # optional
    "tags": ["color", "portrait"], # optional
    "recipe": { ... }              # or put the recipe fields at the top level
  }

Recipe fields (defaults in brackets):

  film_simulation       provia | velvia | astia | pro_neg_hi | pro_neg_std |
                        monochrome | monochrome_ye | monochrome_r | monochrome_g |
                        sepia | classic_chrome | acros | acros_ye | acros_r |
                        acros_g | eterna | classic_negative |
                        eterna_bleach_bypass | nostalgic_negative | reala_ace
                        ["classic_chrome"]
  dynamic_range         dr100 | dr200 | dr400 ["dr100"]
  dynamic_range_priority  0 auto | 1 DR100 | 2 DR200 | 32768 DR400 [0]
  grain_effect          off | weak_small | strong_small | weak_large | strong_large ["off"]
  color_chrome          off | weak | strong ["off"]
  color_chrome_fx_blue  off | weak | strong ["off"]
  smooth_skin           off | weak | strong ["off"]
  white_balance         {"mode": "auto", "shift_r": 0, "shift_b": 0,
                         "color_temperature": 5600}
                        modes: auto, daylight, shade, fluorescent_1..3,
                        incandescent, underwater, color_temperature,
                        ambience_priority
  highlight, shadow     -2..+4, step 0.5   [0]
  color                 -4..+4             [0]
  sharpness             -4..+4             [0]
  clarity               -5..+5             [0]
  noise_reduction       -4..+4             [0]
  monochrome_wc/mg      -9..+9 (monochrome sims only) [0]

Values are validated locally, so a typo fails before anything touches the camera.
"""


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ozure",
        description="Read, edit and install Fujifilm custom recipes over USB PTP.",
    )
    parser.add_argument("--version", action="version", version=f"ozure {__version__}")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--catalog", metavar="DIR", help="catalog directory to use")
    parser.add_argument("--no-color", action="store_true", help="disable colour")
    # The same three flags are accepted after the subcommand too, so both
    # `ozure --json list` and `ozure list --json` work.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS
    )
    common.add_argument(
        "--catalog", metavar="DIR", default=argparse.SUPPRESS, help=argparse.SUPPRESS
    )
    common.add_argument(
        "--no-color", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS
    )

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser(
        "doctor", parents=[common], help="check the environment and USB visibility"
    )
    doctor.set_defaults(func=cmd_doctor)

    connect = sub.add_parser(
        "connect", parents=[common], help="find the camera, open a session, list slots"
    )
    CameraArgs.add(connect)
    connect.set_defaults(func=cmd_connect)

    listing = sub.add_parser("list", parents=[common], help="read the seven slots")
    CameraArgs.add(listing)
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", parents=[common], help="show every field of one or more slots")
    show.add_argument("slots", nargs="*", help="C1..C7 (default: all)")
    CameraArgs.add(show)
    show.set_defaults(func=cmd_show)

    setter = sub.add_parser(
        "set", parents=[common], help="change fields of a slot (defaults to a dry run)"
    )
    setter.add_argument("slot", help="C1..C7")
    setter.add_argument("--field", action="append", metavar="KEY=VALUE", help="repeatable")
    setter.add_argument("--name", help="new slot name")
    setter.add_argument("--film-simulation", dest="film_simulation")
    setter.add_argument("--dynamic-range", dest="dynamic_range")
    setter.add_argument("--grain-effect", dest="grain_effect")
    setter.add_argument("--color-chrome", dest="color_chrome")
    setter.add_argument("--color-chrome-fx-blue", dest="color_chrome_fx_blue")
    setter.add_argument("--smooth-skin", dest="smooth_skin")
    setter.add_argument("--highlight", type=float)
    setter.add_argument("--shadow", type=float)
    setter.add_argument("--color", type=float)
    setter.add_argument("--sharpness", type=float)
    setter.add_argument("--clarity", type=float)
    setter.add_argument("--noise-reduction", dest="noise_reduction", type=int)
    setter.add_argument("--yes", action="store_true", help="actually write to the camera")
    setter.add_argument("--no-backup", action="store_true", help="skip the pre-write backup")
    CameraArgs.add(setter)
    setter.set_defaults(func=cmd_set)

    apply = sub.add_parser("apply", parents=[common], help="install a catalog recipe into a slot")
    apply.add_argument("recipe", help="catalog slug, or a .json file")
    apply.add_argument("--slot", required=True, help="C1..C7")
    apply.add_argument("--name", help="override the name written to the slot")
    apply.add_argument("--keep-name", action="store_true", help="do not touch the slot name")
    apply.add_argument("--yes", action="store_true", help="actually write to the camera")
    apply.add_argument("--no-backup", action="store_true", help="skip the pre-write backup")
    CameraArgs.add(apply)
    apply.set_defaults(func=cmd_apply)

    backup = sub.add_parser("backup", parents=[common], help="save the seven slots to a JSON file")
    backup.add_argument(
        "--out", metavar="PATH", help="file or directory (default: ~/.ozure/backups)"
    )
    CameraArgs.add(backup)
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", parents=[common], help="write a backup back to the camera")
    restore.add_argument("file", help="backup JSON produced by `ozure backup`")
    restore.add_argument("--yes", action="store_true", help="actually write to the camera")
    restore.add_argument("--no-backup", action="store_true", help="skip the pre-write backup")
    CameraArgs.add(restore)
    restore.set_defaults(func=cmd_restore)

    catalog = sub.add_parser("catalog", parents=[common], help="browse the recipe catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_list = catalog_sub.add_parser("list", parents=[common], help="list recipes")
    catalog_list.add_argument("--query", "-q", help="filter by slug, name, tag or film")
    catalog_show = catalog_sub.add_parser("show", parents=[common], help="show one recipe")
    catalog_show.add_argument("ref", help="slug or name")
    catalog_sub.add_parser("format", parents=[common], help="print the catalog file format")
    catalog.set_defaults(func=cmd_catalog)

    return parser


def main(argv: list[str] | None = None) -> int:
    ui.setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "no_color", False):
        ui.COLOR = False
    if not hasattr(args, "yes"):
        args.yes = False
    # OZURE_MOCK=1 lets a demo or a test suite pin the simulator without
    # repeating --mock on every call.
    if os.environ.get("OZURE_MOCK") in {"1", "true", "yes"}:
        args.mock = True
    out = Output(args.json, args.command)
    try:
        args.func(args, out)
        return 0
    except DryRun as exc:
        if args.json:
            ui.emit_json(
                {
                    "ok": True,
                    "schema": JSON_SCHEMA_VERSION,
                    "command": args.command,
                    "version": __version__,
                    "dry_run": True,
                    "data": out.data,
                }
            )
        return exc.exit_code
    except OzureError as exc:
        if args.json:
            ui.emit_json(
                {
                    "ok": False,
                    "schema": JSON_SCHEMA_VERSION,
                    "command": args.command,
                    "error": {"kind": exc.kind, "message": exc.message, "hint": exc.hint},
                }
            )
        else:
            ui.error(exc.message, exc.hint)
        return exc.exit_code
    except KeyboardInterrupt:
        ui.error("interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
