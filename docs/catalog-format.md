# Catalog format

A catalog is a directory of `.json` files. Each file holds either one recipe or
a list. Nothing is compiled in: replacing the folder replaces the catalog.

```json
{
  "version": 1,
  "recipes": [
    { "slug": "acros-night", "name": "Acros Night", "recipe": { "...": "..." } },
    { "slug": "portra-soft", "name": "Portra Soft", "recipe": { "...": "..." } }
  ]
}
```

One recipe per file, with metadata next to the settings:

```json
{
  "slug": "portra-soft",
  "name": "Portra Soft",
  "author": "who made it",
  "source": "https://example.com/post",
  "notes": "why it works, in one or two sentences",
  "tags": ["color", "portrait"],
  "recipe": {
    "film_simulation": "pro_neg_hi",
    "dynamic_range": "dr200",
    "grain_effect": "weak_small",
    "smooth_skin": "strong",
    "white_balance": { "mode": "auto", "shift_r": 3, "shift_b": -4 },
    "highlight": -0.5,
    "shadow": 0.5,
    "color": -1.0,
    "sharpness": -2.0,
    "noise_reduction": 0,
    "clarity": -1.0
  }
}
```

`slug` is what `ozure apply` resolves. `name` becomes the slot name on the
camera if you do not pass `--name`. A flat file (recipe fields at the top level,
metadata beside them) also works.

## Fields

| field | values | default |
| --- | --- | --- |
| `name` | up to 254 UTF-16 characters | file stem |
| `film_simulation` | see below | `classic_chrome` |
| `dynamic_range` | `dr100`, `dr200`, `dr400` | `dr100` |
| `dynamic_range_priority` | `0` auto, `1` DR100, `2` DR200, `32768` DR400 | `0` |
| `grain_effect` | `off`, `weak_small`, `strong_small`, `weak_large`, `strong_large` | `off` |
| `color_chrome` | `off`, `weak`, `strong` | `off` |
| `color_chrome_fx_blue` | `off`, `weak`, `strong` | `off` |
| `smooth_skin` | `off`, `weak`, `strong` | `off` |
| `white_balance` | object, see below | `auto`, no shift |
| `highlight` | -2..+4, step 0.5 | `0` |
| `shadow` | -2..+4, step 0.5 | `0` |
| `color` | -4..+4 | `0` |
| `sharpness` | -4..+4 | `0` |
| `clarity` | -5..+5 | `0` |
| `noise_reduction` | -4..+4 | `0` |
| `monochrome_wc`, `monochrome_mg` | -9..+9, monochrome simulations only | `0` |
| `exposure` | accepted for `fuji-ptp-core` compatibility, not written | `0` |

Film simulations: `provia`, `velvia`, `astia`, `pro_neg_hi`, `pro_neg_std`,
`monochrome`, `monochrome_ye`, `monochrome_r`, `monochrome_g`, `sepia`,
`classic_chrome`, `acros`, `acros_ye`, `acros_r`, `acros_g`, `eterna`,
`classic_negative`, `eterna_bleach_bypass`, `nostalgic_negative`, `reala_ace`.

Human spellings are accepted and normalised: `Classic Negative`, `Acros +R`,
`Pro Neg High`, `AWB`, `WS`/`SS`/`WL`/`SL` for grain.

## White balance

```json
{ "mode": "color_temperature", "color_temperature": 5200, "shift_r": 0, "shift_b": -2 }
```

Modes: `auto`, `daylight`, `shade`, `fluorescent_1`, `fluorescent_2`,
`fluorescent_3`, `incandescent`, `underwater`, `color_temperature`,
`ambience_priority`. `shift_r`/`shift_b` are -9..+9 and are ignored (not sent) on
monochrome simulations. `color_temperature` is only written in
`color_temperature` mode.

## Validation

Everything is validated locally before a session is opened: unknown enum values,
out-of-range dials, a missing temperature, a recipe name over 254 characters.
Values that are legal but unusual produce a warning on stderr instead of an
error, so an exotic recipe can still be installed.
