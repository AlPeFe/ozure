"""Error types and exit codes.

The exit codes are part of the CLI contract: an agent (or a shell script)
can branch on them without parsing text.
"""

from __future__ import annotations


class OzureError(Exception):
    """Base error. Every failure carries an exit code and a hint."""

    exit_code = 1
    kind = "error"

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class UsageError(OzureError):
    exit_code = 2
    kind = "usage"


class CameraNotFound(OzureError):
    """No Fujifilm PTP interface visible on USB, or none in the right mode."""

    exit_code = 3
    kind = "camera_not_found"


class TransportFailure(OzureError):
    """Device found but the USB transfer failed (driver, permissions, unplug)."""

    exit_code = 4
    kind = "transport"


class ProtocolError(OzureError):
    """Camera answered with an unexpected PTP container or response code."""

    exit_code = 5
    kind = "protocol"


class InvalidRecipe(OzureError):
    exit_code = 6
    kind = "invalid_recipe"


class DryRun(OzureError):
    """Nothing was written because --yes was missing."""

    exit_code = 10
    kind = "dry_run"
