# AGENTS.md

This repository ships an agent skill. Read **[SKILL.md](SKILL.md)** first: it
contains the rules an agent must follow (dry run by default, `--yes` to write,
backup before multi-slot writes, read the verification) plus the JSON contract.

Quick orientation:

* `ozure/cli.py` — commands, exit codes, JSON envelope.
* `ozure/fuji.py` — recipe read/write over the PTP session.
* `ozure/ptp.py` — PTP containers and operations.
* `ozure/recipe.py` — domain model, validation and wire codecs.
* `ozure/mockcam.py` — simulated body used by the tests and the demo.
* `catalog/` — bundled sample recipes (replace with your own collection).

Run `python3 -m unittest discover -s tests` before changing protocol code.
