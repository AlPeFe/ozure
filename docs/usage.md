# Usage

```text
ozure [--json] [--catalog DIR] [--no-color] <command> [options]
```

`--json` is accepted before or after the command and always prints exactly one
JSON object on stdout.

## Commands

### `doctor`

Checks Python, `pyusb`, the USB backend, visible Fujifilm interfaces and the
catalog. Never opens a session; safe to run anywhere.

```bash
ozure doctor
ozure doctor --json
```

### `connect`

Finds the camera, opens a PTP session, reads the device info (model, firmware,
serial) and lists the seven slots.

| flag | meaning |
| --- | --- |
| `--wait SECONDS` | keep polling instead of failing on the first attempt |
| `--timeout SECONDS` | USB transfer timeout (default 5) |

### `list`

Reads all seven slots and prints `slot / name / film / settings`.

### `show [SLOT...]`

Every field of the given slots (default: all seven). Adds `warnings` in JSON
when a value is outside the usual range for a body or a property is unavailable.

### `set SLOT --field key=value ...`

Changes only the fields you name; everything else is preserved (the current slot
is read first and merged).

```bash
ozure set C4 --field shadow=1.5 --field clarity=-1
ozure set C4 --dynamic-range dr400 --grain-effect strong_small
ozure set C4 --dynamic-range-priority dr200 --wb-mode shade --wb-shift-b -3
ozure set C4 --name "Portrait Warm" --field color=-1
```

`--field` reaches every scalar in the schema. The named flags are:
`--film-simulation`, `--dynamic-range`, `--dynamic-range-priority`,
`--grain-effect`, `--color-chrome`, `--color-chrome-fx-blue`, `--smooth-skin`,
`--highlight`, `--shadow`, `--color`, `--sharpness`, `--clarity`,
`--noise-reduction`, `--monochrome-wc`, `--monochrome-mg`, `--wb-mode`,
`--wb-shift-r`, `--wb-shift-b`, `--wb-temperature`.

For a full white balance object you can also pass JSON:
`--field 'white_balance={"mode":"shade","shift_b":-2}'`.

| flag | meaning |
| --- | --- |
| `--yes` | actually write (default is a dry run, exit 10) |
| `--no-backup` | skip the pre-write backup of the slot |

### `apply REF --slot SLOT`

Installs a recipe from the catalog (by slug or partial name) or from a `.json`
file. The slot name is written too, unless `--keep-name`.

```bash
ozure apply portra-soft --slot C5
ozure apply portra-soft --slot C5 --name "Portra 400" --yes
ozure apply ./my-recipe.json --slot C1 --keep-name --yes
```

### `backup [--out PATH]` and `restore FILE`

`backup` writes `{"version", "created_at", "camera", "slots": {"C1": {...}, ...}}`.
`restore` accepts the same file and rewrites every slot it contains. Slots the
backup recorded as **empty** are skipped, because an empty slot cannot be
re-created as empty — writing the defaults would invent settings. Pass
`--include-empty` to write them anyway.

```bash
ozure backup --out ~/Desktop/camera.json
ozure restore camera.json            # dry run: prints change counts
ozure restore camera.json --yes
```

### `catalog list|show|format`

```bash
ozure catalog list
ozure catalog list -q acros --json
ozure catalog show eterna-cinema
ozure catalog format
```

## Exit codes

| code | meaning |
| --- | --- |
| 0 | success |
| 1 | unexpected error |
| 2 | usage error or catalog problem |
| 3 | camera not found (unplugged, or not in the PTP USB mode) |
| 4 | USB transport failure (driver, permissions, cable) |
| 5 | PTP protocol error, or the camera rejected the write |
| 6 | invalid recipe (validated before touching the camera) |
| 10 | dry run — nothing was written |

## Environment

| variable | meaning |
| --- | --- |
| `OZURE_HOME` | state directory (default `~/.ozure`) |
| `OZURE_CATALOG` | default catalog directory |
| `OZURE_MOCK` | `1` forces the simulated camera |
| `NO_COLOR` | disable colour |
