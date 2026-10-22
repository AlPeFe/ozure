# ozure

Read, edit and install **Fujifilm custom recipes (C1–C7)** over USB PTP, from
the terminal. Ships 126 curated recipes (Fuji X Weekly, Osan-Bilgi, Alex
Armitage, …) and keeps the same safety rails as the Python package: dry run by
default, backup before writing, read-back verification.

```bash
npm install -g ozure

ozure connect              # find the camera, list the seven slots
ozure list                 # what is loaded right now
ozure catalogs             # what could be installed
ozure apply kodak-gold-200 --slot C6        # dry run: shows the diff, exit 10
ozure apply kodak-gold-200 --slot C6 --yes  # writes, re-reads and verifies
ozure catalog export       # save the camera's recipes into your own catalog
```

On the camera, pick **USB RAW CONV./BACKUP RESTORE**. Windows needs WinUSB on
the PTP interface (Zadig, vendor id `04CB`); Linux may need a udev rule.

No camera? `ozure connect --mock` runs against a simulated body.

The npm package is a thin launcher: it runs the prebuilt binary for your
platform (`ozure-<platform>-<arch>`). If that binary is missing and you
already have the Python package, it falls back to `python -m ozure`.

Docs, schema, protocol notes and the agent skill:
[github.com/AlPeFe/ozure](https://github.com/AlPeFe/ozure).

MIT.
