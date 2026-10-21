# Protocol

ozure speaks USB PTP directly (no vendor SDK, no gphoto2). The implementation
mirrors [`fuji-ptp-core`](https://github.com/AlPeFe/fuji-ptp-core): the same
operations, the same property block, the same write order, the same model
quirks. Keep both in sync when the protocol changes.

## USB

| item | value |
| --- | --- |
| vendor id | `0x04CB` (Fujifilm) |
| interface class | `0x06` (still image capture / PTP) |
| endpoints | one bulk IN, one bulk OUT on that interface |
| camera mode | `USB RAW CONV./BACKUP RESTORE` |

A container is `length:u32le, type:u16le, code:u16le, transaction_id:u32le`
followed by the payload; `length` includes the 12-byte header. A transaction is
`Command` → optional `Data` → `Response`.

## Operations

| op | code | used for |
| --- | --- | --- |
| `GetDeviceInfo` | `0x1001` | model, firmware, serial (best effort) |
| `OpenSession` | `0x1002` | session id 1 |
| `CloseSession` | `0x1003` | — |
| `GetDevicePropValue` | `0x1015` | read name / settings |
| `SetDevicePropValue` | `0x1016` | write name / settings |

## Properties

| id | meaning | encoding |
| --- | --- | --- |
| `0xD18C` | slot cursor | `u16le`, 1..7 |
| `0xD18D` | slot name | PTP string, UTF-16LE, `[count][chars][NUL]` |
| `0xD190` | dynamic range | `100 / 200 / 400` |
| `0xD191` | DR priority | `0` auto, `1`, `2`, `32768` |
| `0xD192` | film simulation | `1..20`, see below |
| `0xD193` | monochrome WC | `i16le`, tenths |
| `0xD194` | monochrome MG | `i16le`, tenths |
| `0xD195` | grain effect | `1..5` (`1` off) |
| `0xD196` | color chrome | `1` off, `2` weak, `3` strong |
| `0xD197` | color chrome fx blue | same |
| `0xD198` | smooth skin | same |
| `0xD199` | white balance | see below |
| `0xD19A` | WB shift R | `i16le`, -9..+9 |
| `0xD19B` | WB shift B | `i16le`, -9..+9 |
| `0xD19C` | color temperature | `u16le`, Kelvin |
| `0xD19D` | highlight | `i16le`, tenths |
| `0xD19E` | shadow | `i16le`, tenths |
| `0xD19F` | color | `i16le`, tenths |
| `0xD1A0` | sharpness | `i16le`, tenths |
| `0xD1A1` | high ISO NR | non-linear, see below |
| `0xD1A2` | clarity | `i16le`, tenths |

Film simulation values: `1` Provia, `2` Velvia, `3` Astia, `4` Pro Neg Hi,
`5` Pro Neg Std, `6` Monochrome, `7/8/9` Monochrome Ye/R/G, `10` Sepia,
`11` Classic Chrome, `12` Acros, `13/14/15` Acros Ye/R/G, `16` Eterna,
`17` Classic Negative, `18` Eterna Bleach Bypass, `19` Nostalgic Neg,
`20` Reala Ace.

White balance values: `2`/`0x8020` auto, `4` daylight, `6` incandescent,
`8` underwater, `0x8001..0x8003` fluorescent, `0x8006` shade,
`0x8007` color temperature, `0x8021` ambience priority.

High ISO NR is not linear: `-4 → 0x8000`, `-3 → 0x7000`, `-2 → 0x4000`,
`-1 → 0x3000`, `0 → 0x2000`, `1 → 0x1000`, `2 → 0`, `3 → 0x6000`,
`4 → 0x5000`.

## Writing a slot

1. `SetDevicePropValue(0xD18C, slot)`.
2. Name **first** — it is what a body drops when a write is truncated.
3. Film simulation, DR priority, (DR only when the priority is `0`).
4. Monochrome WC/MG only for monochrome simulations; Color Chrome and FX Blue
   only for colour ones; WB shift only for colour ones.
5. Color temperature only in `color_temperature` mode.
6. Highlight, shadow, color, sharpness, clarity, then high ISO NR.

Empty slots read back as `0xFFFF` in the first property word. ozure keeps them
representable (`"empty": true`) and never sends `0xFFFF`.

## Known quirks

* An X100VI stores *Grain Off* as wire value `7`; older firmware used `6`.
  Reading accepts `1`, `6` and `7` as `off`.
* Colour-only controls (Color Chrome, FX Blue, WB shift) are rejected or ignored
  on monochrome simulations, so they are skipped instead of sent.
* "Mono WC"/"Mono MG" are rejected when a colour simulation is active, for the
  same reason — they are only written for monochrome.
* Some bodies do not expose every property; a failure on a known-optional
  property is recorded as a warning instead of aborting the slot.
