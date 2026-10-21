"""Where ozure keeps its state.

One place for every path, so the catalog, the CLI and the tests agree.
"""

from __future__ import annotations

import os
from pathlib import Path


def ozure_home() -> Path:
    """State directory: `$OZURE_HOME` or `~/.ozure`."""
    override = os.environ.get("OZURE_HOME")
    return Path(override) if override else Path.home() / ".ozure"


def default_catalog_dir() -> Path:
    return ozure_home() / "catalog"


def catalogs_root() -> Path:
    """Where named catalogs live: `~/.ozure/catalogs/<name>`."""
    return ozure_home() / "catalogs"


def backup_dir() -> Path:
    return ozure_home() / "backups"


def mock_state_path(explicit: str | None = None) -> Path:
    return Path(explicit) if explicit else ozure_home() / "mock-camera.json"
