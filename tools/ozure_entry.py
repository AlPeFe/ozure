"""Entry point for the standalone binaries (PyInstaller cannot run a package
module with relative imports as a script)."""

import sys

from ozure.cli import main

if __name__ == "__main__":
    sys.exit(main())
