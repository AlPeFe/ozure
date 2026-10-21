---
name: ozure
description: Read, edit and install Fujifilm Custom Recipes (C1-C7) on the camera over USB PTP. Use when the user wants to connect a Fujifilm body (X100V/VI, X-T*, X-Pro, X-S, GFX), see which recipes the camera has, change a film simulation / grain / white balance shift / tone curve, apply a recipe from the catalog to a slot, or back up and restore all seven slots.
license: MIT
metadata:
  requires:
    bins: ["python3"]
    pip: ["pyusb"]
  version: 0.2.0
---

# ozure — Fujifilm recipes, from the catalog to the camera

ozure talks to the camera over USB PTP (the same protocol as
`fuji-ptp-core`) and exposes it as a small, scriptable CLI with a strict JSON
mode. Recipes are ordinary JSON, so the catalog is just a folder of files.

## Non-negotiable rules

1. **Never write without `--yes`.** `set`, `apply` and `restore` are dry runs by
   default and exit with code **10**. Show the user the diff, get their go-ahead,
   then re-run with `--yes`.
2. **Always back up before a multi-slot write.** `ozure backup` first, or let
   the per-write backup happen (default) and report its path.
3. **Trust the verification, not the write.** Every write re-reads the slot and
   reports `mismatches`. If that list is not empty, tell the user what the camera
   refused.
4. **Don't invent values.** Valid enums and ranges are in
   `ozure catalog format`; an invalid value fails locally before touching the
   camera. Every field of the slot is exposed: name + the 19 property words
   (film simulation, dynamic range and its priority, grain, smooth skin, color
   chrome and fx blue, white balance mode/shift/temperature, highlight, shadow,
   color, sharpness, clarity, high ISO NR, monochrome WC/MG).
5. **Read the warnings.** Controls a body does not implement (clarity on older
   firmware, the Kelvin word, monochrome controls on colour simulations) come
   back as `warnings`, not as failures.

## Setup (once per machine)

```bash
python3 -m pip install pyusb          # add: pip install libusb-package
ozure --version                     # or: python3 -m ozure --version
ozure doctor --json                 # is the camera visible?
```

On the camera: **USB RAW CONV./BACKUP RESTORE**. On Windows the PTP interface
needs WinUSB (Zadig, vendor id must start with `04CB`). On Linux, a udev rule or
`sudo` may be needed to claim the interface.

No camera at hand? Add `--mock` (or `OZURE_MOCK=1`) and every command runs
against a simulated body in `~/.ozure/mock-camera.json`.

## Workflow

```bash
# 1. Is it there?
ozure connect --wait 15 --json

# 2. What is loaded right now?
ozure list --json            # slot names + a one-line summary
ozure show C3 --json         # every field of one slot

# 3. What could be installed?
ozure catalog list --json                # or: -q acros
ozure catalog show eterna-cinema --json

# 4. Change one thing (dry run, then write)
ozure set C3 --field shadow=1.5 --json
ozure set C3 --field shadow=1.5 --yes --json

# 5. Install a catalog recipe into a slot
ozure apply eterna-cinema --slot C6 --json        # dry run, exit 10
ozure apply eterna-cinema --slot C6 --yes --json  # writes + verifies

# 6. Safety net
ozure backup --json
ozure restore ~/.ozure/backups/20261021T101500Z-profile.json --yes --json
```

## Contract for agents

* **stdout** carries the result; `--json` prints a single object:
  `{"ok": true, "schema": 1, "command": "...", "version": "...", "data": {...}}`
  and on failure `{"ok": false, ..., "error": {"kind", "message", "hint"}}`.
  A dry run prints `{"ok": true, ..., "dry_run": true, "data": {"written": false, "changes": [...]}}`.
* **stderr** carries warnings (`outside the usual range`, camera refusals) that
  did not stop the command.
* **Exit codes**: `0` ok · `1` unexpected error · `2` usage/catalog problem ·
  `3` camera not found (not plugged in, or not in the PTP USB mode) ·
  `4` USB transport (driver or permissions) · `5` PTP protocol/camera rejected
  the write · `6` invalid recipe · `10` dry run, nothing written.
* Slots are addressed as `C1`..`C7`.
* Recipe field names are snake_case and match `fuji-ptp-core`'s serde model, so
  a JSON dump from either tool loads in the other.

## Reading `data` after a write

```json
{"slot": "C6", "written": true, "changes": [{"field": "...", "before": "...", "after": "..."}],
 "verified": {"film_simulation": "eterna", "...": "..."}, "mismatches": ["clarity"],
 "backup": "/home/me/.ozure/backups/...-C6.json"}
```

`mismatches` only lists fields the body refused or normalised. Colour-only
controls and the WB shift are deliberately not sent on monochrome simulations,
and they are excluded from that list.

## Where the catalog lives

Resolution order: `--catalog DIR` → `$OZURE_CATALOG` → the repo's
`catalog/` → `~/.ozure/catalog`. Format: one JSON file per recipe, or
`{"recipes": [...]}`. Run `ozure catalog format` for the full field list.

## Reference

* `docs/usage.md` — every command and flag.
* `docs/catalog-format.md` — catalog schema and worked examples.
* `docs/protocol.md` — PTP operations, property ids, wire conversions.
* `docs/troubleshooting.md` — "camera not found", driver, firmware quirks.
