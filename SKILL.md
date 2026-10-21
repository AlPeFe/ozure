---
name: ozure
description: Read, edit and install Fujifilm Custom Recipes (C1-C7) on the camera over USB PTP. Use when the user wants to connect a Fujifilm body (X100V/VI, X-T*, X-Pro, X-S, GFX), see which recipes the camera has, change a film simulation / grain / white balance shift / tone curve, apply a recipe from a catalog to a slot, or back up and restore all seven slots. También cuando pide "conecta con mi cámara Fuji", "qué recetas tengo cargadas", "ponme esta receta en C3" o "hazme una copia de seguridad de las recetas".
license: MIT
metadata:
  requires:
    bins: ["python3"]
    pip: ["pyusb"]
  version: 0.2.0
---

# ozure — Fujifilm recipes, from the catalog to the camera

ozure talks to the camera over USB PTP and exposes it as a scriptable CLI with a
strict JSON mode. Recipes are ordinary JSON, so the catalog is just a folder of
files. You never need the GUI, a vendor SDK, or gphoto2.

## Hard rules

1. **Never write without consent.** `set`, `apply` and `restore` are dry runs and
   exit **10**. Run the dry run, show the user the diff (or act on their explicit
   instruction if the diff matches exactly what they asked), then re-run with
   `--yes`. If the diff surprises you, stop and ask.
2. **Never fake hardware.** `--mock` / `OZURE_MOCK=1` drives a simulated body. Use
   it only when the user asks for a demo or agrees there is no camera, and say so
   in your answer ("simulated body"). Never report a mock write as a real one.
3. **Trust the verification.** Every write re-reads the slot. If `mismatches` is
   not empty, tell the user which fields the body refused or normalised.
4. **Back up before a multi-slot write.** `ozure backup` first for `restore`, or
   rely on the per-write backup (default) and report its path.
5. **Don't invent values.** Enums and ranges are in `ozure catalog format`; bad
   values fail locally before touching the camera. Every field is reachable: the
   slot name plus the 19 property words (film simulation, dynamic range and its
   priority, grain, smooth skin, colour chrome, fx blue, white balance
   mode/shift/Kelvin, highlight, shadow, color, sharpness, clarity, high ISO NR,
   monochrome WC/MG).
6. **Read the warnings.** Controls a body does not implement (clarity on old
   firmware, the Kelvin word, monochrome controls on colour simulations) come
   back as `warnings`, not as failures. Mention them; don't retry blindly.

## Install check (first thing, always)

```bash
ozure --version                         # if it fails: python3 -m pip install -e .
python3 -m pip install pyusb            # needed for real USB (add libusb-package)
ozure doctor --json                     # pyusb, USB visible, catalog count
```

`python3 -m ozure` is always equivalent to the `ozure` command; use it if the
entry point is not on `PATH`.

On the camera: **USB RAW CONV./BACKUP RESTORE**. Windows needs WinUSB on the PTP
interface (Zadig, vendor id starts with `04CB`); Linux may need a udev rule.
`doctor` reports what it can see and what is wrong with each device.

## Workflow

```bash
ozure connect --wait 15 --json          # camera info + seven slots
ozure list --json                       # what is loaded now
ozure show C3 --json                    # every field of one slot
ozure catalog list --json               # what could be installed (-q text)
ozure catalog show eterna-cinema --json
ozure set C3 --field shadow=1.5 --json          # dry run, exit 10
ozure set C3 --field shadow=1.5 --yes --json    # write + verify
ozure apply eterna-cinema --slot C6 --json      # dry run, exit 10
ozure apply eterna-cinema --slot C6 --yes --json
ozure backup --json                     # seven slots to one file
ozure restore ~/.ozure/backups/20261021T101500Z-profile.json --yes --json
```

`--json` may go before or after the command. It prints exactly one object on
stdout; stderr carries warnings that did not stop the command.

`apply` writes the recipe's `name` into the slot; use `--name "..."` to change it
or `--keep-name` to leave the camera's name alone.

## Data you can rely on

| command | `data` |
| --- | --- |
| `connect` | `connected`, `camera{model,firmware,serial,...}`, `slots[]{slot,name,empty}` |
| `list` | `camera`, `slots[]{slot,name,empty,film_simulation,summary,recipe}` |
| `show` | `slots[]{slot,empty,recipe{...all fields...}}` |
| `catalog list` | `directory`, `count`, `recipes[]{slug,name,film_simulation,tags,recipe}` |
| `catalog show` | `recipe{slug,name,...,recipe}` |
| `set` / `apply` | `slot`, `recipe`, `changes[]{field,before,after}`, `written`, `verified`, `mismatches`, `warnings`, `backup` |
| `backup` | `path`, `camera`, `slots{C1..C7}` |
| `doctor` | `pyusb`, `usb_devices[]`, `catalog_dir`, `catalog_recipes` |

Envelope: `{"ok": true, "schema": 1, "command", "version", "data"}`; failures use
`{"ok": false, ..., "error": {"kind", "message", "hint"}}`; dry runs add
`"dry_run": true`. Slots are `C1`..`C7`; recipe fields are snake_case and match
`fuji-ptp-core`'s serde model.

## Exit codes → what to do

| code | meaning | next action |
| --- | --- | --- |
| 0 | success | report `changes`, `mismatches`, `backup` |
| 1 | unexpected error | show `error.message`; do not retry blindly |
| 2 | usage or catalog problem | fix the arguments; `catalog list` first |
| 3 | camera not found | tell the user to switch the camera to USB RAW CONV./BACKUP RESTORE and replug; `--wait 15` to poll |
| 4 | USB transport | driver/permissions: WinUSB (Zadig) on Windows, udev rule on Linux |
| 5 | camera rejected the write | read `error.message`, narrow the change, or check `mismatches` |
| 6 | invalid recipe | the value is out of range: `ozure catalog format` |
| 10 | dry run, nothing written | show the diff, then re-run with `--yes` |

Film simulations, ready to pass as `--field film_simulation=...` or
`--film-simulation`: `provia`, `velvia`, `astia`, `pro_neg_hi`, `pro_neg_std`,
`monochrome`, `monochrome_ye`, `monochrome_r`, `monochrome_g`, `sepia`,
`classic_chrome`, `acros`, `acros_ye`, `acros_r`, `acros_g`, `eterna`,
`classic_negative`, `eterna_bleach_bypass`, `nostalgic_negative`, `reala_ace`.
Everything else (grain, colour chrome, white balance modes, ranges) is in
`ozure catalog format`.

## Choosing a slot

* If the user names a slot ("en C3"), use it.
* If they don't, look at `list --json`: prefer a slot marked `empty`, otherwise
  ask which of the seven they want to overwrite. Never pick a used slot on a
  hunch — every slot is somebody's recipe.
* `--keep-name` writes the settings but leaves the camera's slot name alone.

## Catalog

Resolution order: `--catalog DIR` → `$OZURE_CATALOG` → the repo's `catalog/` →
`~/.ozure/catalog`. Format: one JSON file per recipe, or `{"recipes": [...]}`;
`ozure catalog format` prints the whole schema.

If `catalog list` comes back empty, don't invent recipes: tell the user to drop
JSON files in `~/.ozure/catalog` (or pass `--catalog DIR`), offer to write a
recipe from what they describe, and show them the format block.

## When not to use it

* Bodies without custom recipe slots, or a camera used as a card reader (no PTP):
  `doctor` says so, stop there.
* Don't hand-edit `~/.ozure/mock-camera.json` to simulate success.
* Don't chain `restore` over slots the user did not ask to touch; it rewrites
  every slot in the file.

## Reference

* `docs/usage.md` — every command and flag.
* `docs/catalog-format.md` — catalog schema and worked examples.
* `docs/protocol.md` — PTP operations, property ids, wire conversions.
* `docs/troubleshooting.md` — "camera not found", drivers, firmware quirks.
