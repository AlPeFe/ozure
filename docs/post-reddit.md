# Reddit posts

Primary post: short, for the agent/LLM subs (r/ClaudeAI, r/codex, r/AI_Agents,
r/LocalLLaMA, r/commandline). The longer photography version is kept below for
r/fujifilm, r/x100v and r/fujifilmx.

---

## Short · agent / LLM subs

**Title:** `A CLI + skill so Claude Code / Codex can read and edit your Fujifilm recipes over USB`

**Body:**

I built **ozure**: a CLI that reads and writes the C1–C7 recipe slots over USB PTP
— plus a `SKILL.md`, so an agent can drive it from plain language.

It is a decent fit for a harness because it is predictable:

- one JSON envelope per command (`{ok, command, data}`) and real exit codes
  (3 = no camera, 5 = camera rejected, 10 = dry run)
- writes are **dry runs unless `--yes`**: diff first, backup before, read-back
  verification after
- offline, no API keys; 126 recipes bundled as plain JSON

```bash
npm install -g @alpefe/ozure
ozure connect --json
ozure apply kodak-gold-200 --slot C6        # dry run: diff, exit 10
ozure apply kodak-gold-200 --slot C6 --yes  # write + re-read + verify
```

Then ask: *"connect to my Fuji and put Kodak Gold 200 in C6"*. The skill tells the
agent to show you the diff before writing.

Repo (MIT, skill at the root, just point your agent at it):
https://github.com/AlPeFe/ozure

One caveat: on Windows the camera interface must be on WinUSB (Zadig) or libusb
gets `Access denied` — steps in the README.

## Long version · photography subs

## r/fujifilm · r/x100v · r/fujifilmx

**Title options** (pick one):

1. `I wrote an open-source CLI to read, edit and install the C1–C7 recipes over USB (126 recipes bundled)`
2. `Editing Fujifilm recipes from a terminal: read your 7 slots, install one from a catalog, verify the write`
3. `Tired of re-dialing recipes: a small tool that writes C1–C7 straight from the computer`

**Body:**

I love the custom recipe slots, but I hate dialing them in. Seven slots, each
with a dozen parameters, and the camera only shows one value at a time. So I
built **ozure**: a small CLI (and an agent skill) that talks to the camera over
USB PTP and does the boring part.

```bash
ozure connect                 # find the camera, list C1..C7
ozure list                    # what is loaded right now, one line per slot
ozure apply kodak-gold-200 --slot C6        # dry run: shows the diff, writes nothing
ozure apply kodak-gold-200 --slot C6 --yes  # writes, re-reads the slot and compares
```

**It is deliberately boring about safety**, because it writes to your camera:

- `apply` / `set` are **dry runs by default**. Without `--yes` they print the diff
  and exit with code 10.
- Before touching a slot it saves that slot to `~/.ozure/backups/`.
- After writing it **reads the slot back** and lists anything the body refused or
  normalised. If that list is not empty, you see it.
- Values are validated locally against the ranges the hardware accepts.

**Catalogs.** A catalog is a folder of JSON recipes. There are **126 bundled**
(imported from Fuji X Weekly, Osan-Bilgi, Alex Armitage, Reggie's, Kevin
Mullins…), each file keeping its source link and the original description. You
can also go the other way and export your camera's seven slots into your own
catalog, so the look you tuned on the body is not lost when you overwrite it:

```bash
ozure catalogs                          # what is available
ozure catalog list --catalog fxw        # 79 recipes
ozure catalog show kodak-gold-200       # full settings + source
ozure catalog export                    # your 7 slots -> your catalog
```

**It is also an agent skill.** There is a `SKILL.md` in the repo, so you can ask
an assistant "connect to my Fuji and put Kodak Gold 200 in C6" and it runs the
same commands — with the same guardrails (it has to show you the diff first).

**Install**

```bash
npm install -g @alpefe/ozure     # prebuilt binary, no Python needed
pipx install "ozure[usb]"        # or through Python
```

Repo (MIT, no telemetry, nothing leaves the machine): https://github.com/AlPeFe/ozure

**Honest limitations**

- Windows needs a one-time driver step: the camera's PTP interface has to be
  bound to **WinUSB** (Zadig) because Windows' own WPD driver holds it and libusb
  cannot claim it. It is documented in the README with the exact steps and how to
  revert. macOS needs nothing; Linux may need a udev rule.
- Only the **Windows x64** binary is published so far; macOS/Linux fall back to
  the Python package until the CI matrix builds theirs.
- It writes the C1–C7 block only (name + 19 property words). Not backup/restore of
  the whole card, no firmware, no photo transfer.
- Some controls are model/firmware specific (clarity on older bodies, the Kelvin
  word, monochrome controls on color sims). Those come back as warnings instead of
  failing the write.

Tested on a real body (`04CB:0305`): reading all seven slots, and writing a
recipe to an empty slot with a clean read-back. Feedback very welcome, especially
from X-T / X-Pro / GFX owners, since I have only one body here.

---

## r/commandline · r/opensource

**Title:** `ozure: a CLI that reads and writes Fujifilm camera recipes over USB PTP (dry-run by default)`

**Body:**

A small CLI for a niche problem: Fujifilm bodies keep seven "custom recipes"
(film simulation, grain, tone curve, WB shift…) and the only way to edit them is
a menu wheel. **ozure** reads and writes those slots over raw USB PTP.

```bash
npm install -g @alpefe/ozure
ozure list
ozure apply kodak-gold-200 --slot C6          # diff, exit 10, nothing written
ozure apply kodak-gold-200 --slot C6 --yes    # write + read-back verification
```

Things that might be interesting beyond the camera bits:

- **Writes need `--yes`**, exit 10 otherwise. Backups before writing, read-back
  after, and a `mismatches` list of anything the device silently changed.
- **126 recipes bundled** as plain JSON, one file each, with provenance.
- **A simulator** (`--mock`) so the whole flow is testable without hardware; the
  demo GIF and the test suite both run against it.
- **`SKILL.md`**: the repo is also an agent skill, so a harness can drive it from
  plain language with the same guardrails.
- A single-file binary (PyInstaller) plus a thin npm launcher, the esbuild pattern,
  so npm users do not need Python.

Repo: https://github.com/AlPeFe/ozure (MIT)

The friction worth knowing about: on Windows the camera interface must be on
WinUSB, otherwise libusb gets `Access denied`. The README spells out the Zadig
steps and how to undo them. macOS/Linux binaries are next, once CI builds them.
