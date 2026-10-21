"""Terminal rendering: colour, tables, diffs and the JSON view.

Two audiences, two shapes: humans get colour and alignment, agents get
`--json` with a stable schema. Colour is disabled automatically when stdout is
not a TTY or when NO_COLOR is set.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any

COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _encodable(text: str) -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


#: Windows consoles still default to cp1252 often enough that the marks have
#: to degrade gracefully instead of crashing the CLI.
OK_MARK = "✓" if _encodable("✓") else "ok"
FAIL_MARK = "✗" if _encodable("✗") else "x"


def setup_stdio() -> None:
    """Prefer UTF-8 output; never fail because of a pipe or an old console."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GREY = "\033[90m"


def paint(text: str, *styles: str) -> str:
    if not COLOR or not styles:
        return text
    return "".join(styles) + text + RESET


def warn(text: str) -> None:
    print(paint(f"warning: {text}", YELLOW), file=sys.stderr)


def error(text: str, hint: str | None = None) -> None:
    print(paint(f"error: {text}", RED), file=sys.stderr)
    if hint:
        print(paint(f"hint: {hint}", GREY), file=sys.stderr)


def step(text: str) -> None:
    print(paint(f"→ {text}", DIM))


def ok(text: str) -> None:
    print(paint(f"{OK_MARK} {text}", GREEN))


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    rows = [list(map(str, row)) for row in rows]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = []
    header_line = "  ".join(
        paint(header.ljust(widths[index]), BOLD) for index, header in enumerate(headers)
    )
    lines.append(header_line)
    lines.append(paint("  ".join("-" * width for width in widths), GREY))
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines)


def render_diff(changes: Sequence[tuple[str, Any, Any]]) -> str:
    """`changes` is a list of (field, before, after). Unchanged fields are omitted."""
    if not changes:
        return paint("no changes", DIM)
    width = max(len(field) for field, _, _ in changes)
    lines = []
    for field, before, after in changes:
        lines.append(
            f"  {field.ljust(width)}  {paint(str(before), RED)} → {paint(str(after), GREEN)}"
        )
    return "\n".join(lines)
