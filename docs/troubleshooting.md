# Troubleshooting

## `camera not found` (exit 3)

The CLI only sees a camera that is in PTP mode.

1. On the camera: **SET UP → CONNECTION SETTING → USB → USB RAW CONV./BACKUP
   RESTORE**. In any other USB mode the body exposes a mass-storage interface
   instead.
2. `ozure doctor` prints every Fujifilm device it can see and what is wrong
   with it ("device is not in USB RAW CONV./BACKUP RESTORE mode").
3. Some bodies need to be awake and out of playback mode.
4. Try another cable/port: some USB-C cables are charge-only.

## `transport` (exit 4)

The device is there but the interface could not be claimed.

* **Windows**: the PTP interface needs the WinUSB driver. In Zadig, enable
  *List All Devices*, pick **USB PTP Camera** (vendor id must start with `04CB`)
  and install WinUSB.
* **Linux**: add a udev rule instead of running as root:

  ```bash
  echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="04cb", MODE="0666"' \
    | sudo tee /etc/udev/rules.d/60-fuji-ptp.rules
  sudo udevadm control --reload-rules && sudo udevadm trigger
  ```

* **macOS**: no driver needed, but the *Image Capture* / *Photos* daemon may grab
  the interface; quit those apps.
* "no USB backend available" means libusb is missing:
  `pip install libusb-package`.

## `protocol` (exit 5)

The camera answered with an error response.

* `0x200F` (DeviceBusy): another app holds the session. Close Fujifilm X
  Acquire / tethering software.
* `0x200B` (DevicePropNotSupported): the property does not exist on this body.
  ozure already tolerates the optional ones.
* `0x201D` (InvalidParameter): a value outside what this firmware accepts —
  usually a dial beyond the body's range or a colour control on a monochrome
  simulation. Narrow the change, or use `--json` and inspect `mismatches`.
* Anything after a successful write but before verification: re-run
  `ozure show C3 --json`; the slot is probably fine and the read was late.

## `mismatches` is not empty

The write succeeded and the read-back disagreed. That means the body normalised
or refused those fields. It

* grain: bodies normalise `off` to their own wire value, and both decode to `off`;
* clarity / color: some bodies clip to their dial range;
* white balance shift: not written on monochrome simulations;
* a slot name longer than the body allows gets truncated.

Nothing is lost silently: the previous content is in
`~/.ozure/backups/<timestamp>-<slot>.json`.

## Recipes look wrong after an import

`ozure show C3` prints exactly what the camera stores. If a value looks
unusual, it is probably what was written; `ozure restore` from the backup
takes it back.

## Working without a camera

`--mock` (or `OZURE_MOCK=1`) uses `~/.ozure/mock-camera.json`, a plain JSON
file you can edit by hand. Delete it to reseed from the catalog.
