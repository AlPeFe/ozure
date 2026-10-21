"""Build assets/demo.gif from real CLI runs against the simulated camera.

Nothing in the animation is faked: every command is executed through
`python -m ozure` with a throwaway OZURE_HOME, and the terminal frames show
the bytes that came back. Only the typing and scrolling are staged.

    python tools/build_demo_gif.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "demo.gif"

WIDTH, HEIGHT = 960, 560
PAD_X, PAD_Y = 26, 20
HEADER_H = 40
FONT_SIZE = 16
LINE_H = 23
MAX_LINES = 18

# The same pastel palette as assets/palette.md: cream, blush, pink, soft ink.
CREAM = (255, 249, 247)
BLUSH = (252, 228, 234)
BORDER = (240, 214, 220)
INK = (44, 47, 56)
TEXT = (74, 79, 90)
DIM = (154, 143, 149)
PETAL = (242, 163, 182)
ROSE = (200, 106, 136)
GREEN = (79, 156, 120)
AMBER = (181, 124, 46)
CORAL = (198, 90, 97)

FONT = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", FONT_SIZE)
FONT_BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", FONT_SIZE)
FONT_SMALL = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)

LOGO = ROOT / "assets" / "wordmark.png"

STEPS = [
    "connect",
    "catalogs",
    "catalog list --catalog fxw -q kodak",
    "apply acros-night --slot C6",
    "apply acros-night --slot C6 --yes",
    "list",
]


def run(command: str, home: Path) -> list[tuple[str, tuple[int, int, int]]]:
    env = {
        **os.environ,
        "OZURE_HOME": str(home),
        "OZURE_MOCK": "1",
        "NO_COLOR": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "-m", "ozure", *command.split()],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    lines: list[tuple[str, tuple[int, int, int]]] = []
    for line in result.stdout.rstrip("\n").splitlines():
        lines.append((line, style_for(line)))
    for line in result.stderr.rstrip("\n").splitlines():
        if line.strip():
            lines.append((line, CORAL))
    return lines


def style_for(line: str) -> tuple[int, int, int]:
    stripped = line.strip()
    if stripped.startswith(("ok ", "✓")):
        return GREEN
    if stripped.startswith(("dry run", "plan")):
        return AMBER
    if stripped.startswith("error"):
        return CORAL
    if re.match(r"^-+(\s+-+)+$", stripped):
        return BORDER
    if " → " in line:
        return TEXT
    if stripped.startswith(("slot ", "slug ")):
        return DIM
    if stripped.startswith(("backup:", "next:")):
        return DIM
    return TEXT


MAX_TEXT_WIDTH = WIDTH - 2 * PAD_X


def fit(text: str) -> str:
    """Ellipsize a line so nothing is clipped by the window edge."""
    if FONT.getlength(text) <= MAX_TEXT_WIDTH:
        return text
    trimmed = text
    while trimmed and FONT.getlength(trimmed + "…") > MAX_TEXT_WIDTH:
        trimmed = trimmed[:-1]
    return trimmed + "…"


def draw_frame(
    lines: list[tuple[str, tuple[int, int, int]]],
    typed: str,
    prompt_visible: bool,
    title: str,
) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, WIDTH - 1, HEIGHT - 1], radius=16, fill=CREAM)
    draw.rounded_rectangle([0, 0, WIDTH - 1, HEADER_H], radius=16, fill=BLUSH)
    draw.rectangle([0, HEADER_H - 16, WIDTH - 1, HEADER_H], fill=BLUSH)
    for index, colour in enumerate([PETAL, (246, 208, 166), (185, 216, 200)]):
        x = 22 + index * 20
        draw.ellipse([x, 15, x + 10, 25], fill=colour)
    if LOGO.exists():
        logo = Image.open(LOGO)
        height = 20
        width = round(logo.width * height / logo.height)
        logo = logo.resize((width, height), Image.LANCZOS)
        image.paste(logo, (88, (HEADER_H - height) // 2), logo)
    draw.text((WIDTH - 22, HEADER_H / 2 - 8), title, font=FONT_SMALL, fill=DIM, anchor="ra")
    draw.line([0, HEADER_H, WIDTH, HEADER_H], fill=BORDER)
    # A status bar keeps the frame honest about what is on screen.
    draw.rectangle([0, HEIGHT - 26, WIDTH - 1, HEIGHT - 1], fill=BLUSH)
    draw.line([0, HEIGHT - 26, WIDTH, HEIGHT - 26], fill=BORDER)
    draw.text((PAD_X, HEIGHT - 20), "simulated body · OZURE_MOCK=1", font=FONT_SMALL, fill=DIM)
    draw.text((WIDTH - PAD_X, HEIGHT - 20), "ozure", font=FONT_SMALL, fill=ROSE, anchor="ra")

    # Bottom-anchored, the way a terminal looks after `clear`.
    total = len(lines) + (1 if prompt_visible else 0)
    y = max(HEADER_H + PAD_Y, HEIGHT - 40 - total * LINE_H)
    for text, colour in lines:
        if text:
            draw.text((PAD_X, y), fit(text), font=FONT, fill=colour)
        y += LINE_H
    if prompt_visible:
        prompt_x = PAD_X
        draw.text((prompt_x, y), "$", font=FONT_BOLD, fill=ROSE)
        draw.text((prompt_x + 18, y), "ozure " + typed, font=FONT, fill=INK)
        if (len(typed) // 2) % 2 == 0:
            cursor_x = prompt_x + 18 + FONT.getlength("ozure " + typed) + 1
            draw.rectangle([cursor_x, y + 2, cursor_x + 9, y + FONT_SIZE + 4], fill=PETAL)
    return image


def render(
    script: list[tuple[str, list[tuple[str, tuple[int, int, int]]]]],
) -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []
    visible: list[tuple[str, tuple[int, int, int]]] = []
    title = "USB PTP console"

    def snap(duration: int) -> None:
        image = draw_frame(visible, "", False, title)
        frames.append(image.quantize(colors=64, method=Image.MEDIANCUT))
        durations.append(duration)

    snap(700)
    for index, (command, output) in enumerate(script):
        if index:
            # Clear between steps: each one deserves a readable screen.
            visible = []
            snap(220)
        typed = ""
        for index in range(0, len(command) + 1, 2):
            typed = command[:index]
            image = draw_frame(visible, typed, True, title)
            frames.append(image.quantize(colors=64, method=Image.MEDIANCUT))
            durations.append(45)
        typed = command
        frames.append(
            draw_frame(visible, typed, True, title).quantize(colors=64, method=Image.MEDIANCUT)
        )
        durations.append(320)

        visible.append(("$ ozure " + command, ROSE))
        for line in output:
            visible.append(line)
            if len(visible) > MAX_LINES:
                visible.pop(0)
            frames.append(
                draw_frame(visible, "", False, title).quantize(colors=64, method=Image.MEDIANCUT)
            )
            durations.append(70)
        # the CLI prompt goes back to the user
        visible.append(("", CREAM))
        snap(900)
    durations[-1] = 2600
    return frames, durations


def main() -> None:
    home = Path(tempfile.mkdtemp(prefix="ozure-demo-"))
    try:
        script = []
        for command in STEPS:
            script.append((command, run(command, home)))
    finally:
        shutil.rmtree(home, ignore_errors=True)

    frames, durations = render(script)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} kB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
