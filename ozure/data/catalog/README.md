# Catalogs

Each subdirectory is a catalog. `ozure catalogs` lists them; `ozure catalog list
--catalog <name>` lists the recipes inside one.

| catalog | recipes | where it comes from |
| --- | --- | --- |
| `fxw` | 79 | Fuji X Weekly, imported from the Android app |
| `popular2026` | 26 | "Top 26 most viewed of 2026" (Fuji X Weekly) |
| `osan` | 5 | Osan-Bilgi |
| `armitage` | 5 | Alex Armitage (X100VI) |
| `samples` | 5 | hand-written samples, safe to delete |
| `instagram` | 4 | viral reels |
| `reggies` | 3 | Reggie |
| `eddy` | 2 | EDDY's point & shoot |
| `bw` | 1 | Kevin Mullins |
| `reddit` | 1 | r/fujix |

## Where these came from

The collections are imported from
[`AlPeFe/fuji-ptp-android`](https://github.com/AlPeFe/fuji-ptp-android), which
curates them in `DiscoverData.kt`. Each recipe keeps its `source` link and the
original description in `notes`, plus `parse_notes` when a value (for example
"DR-P Strong") has no equivalent in the C1–C7 block.

Regenerate them from the Kotlin source at any time:

```bash
python3 tools/import_discover.py                 # fetches the file into .build/
python3 tools/import_discover.py --source path/to/DiscoverData.kt
```

## Adding your own

```bash
ozure catalog init my-looks          # empty catalog with a README
ozure catalog add C3 --catalog my-looks --name "My Eterna" --tags cinema
ozure catalog export --catalog my-looks   # copy every non-empty slot
```

Or drop a JSON file here, one recipe per file:

```json
{
  "slug": "acros-night",
  "name": "Acros Night",
  "tags": ["monochrome"],
  "recipe": { "film_simulation": "acros", "highlight": 1, "shadow": 2 }
}
```

Full schema: `ozure catalog format` · [`docs/catalog-format.md`](../../../docs/catalog-format.md).
