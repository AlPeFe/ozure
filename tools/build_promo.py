"""Build assets/promo.mp4: a ~35 s promo for Twitter, 1280x720, no audio.

Every terminal line comes from really running the CLI against the simulated
body, so the video cannot show a command that does not work.

    python tools/build_promo.py            # writes assets/promo.mp4
    python tools/build_promo.py --gif      # also writes a preview GIF

Requires ffmpeg: `pip install imageio-ffmpeg` provides a binary.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
BUILD = ROOT / ".build"
MONO = "C:/Windows/Fonts/consola.ttf"
MONO_BOLD = "C:/Windows/Fonts/consolab.ttf"

W, H = 1280, 720
FPS = 30

CREAM = (255, 249, 247)
BLUSH = (252, 228, 234)
PETAL = (242, 163, 182)
PETAL_DEEP = (229, 142, 164)
ROSE = (200, 106, 136)
INK = (44, 47, 56)
TEXT = (74, 79, 90)
DIM = (150, 136, 143)
GREEN = (79, 156, 120)
AMBER = (176, 122, 48)
WHITE = (255, 255, 255)

FONT_BOLD = str(BUILD / "quicksand-600.ttf")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def qfont(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD, size)


def monofont(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO, size)


def ease(t: float) -> float:
    """Smooth 0..1 ease-out."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def fade_text(
    image: Image.Image,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    colour: tuple[int, int, int],
    alpha: float,
    anchor: str = "la",
) -> None:
    """Draw text with an opacity, on its own layer so it composites cleanly."""
    if alpha <= 0.01:
        return
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=(*colour, 255), anchor=anchor)
    if alpha < 1:
        layer.putalpha(layer.getchannel("A").point(lambda value: round(value * alpha)))
    image.alpha_composite(layer)


def background() -> Image.Image:
    """Cream page with two soft blush blobs, drawn opaque then blurred once."""
    image = Image.new("RGBA", (W, H), (*CREAM, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse([W - 380, -220, W + 200, 360], fill=(*mix(CREAM, BLUSH, 0.85), 255))
    draw.ellipse([-240, H - 300, 320, H + 220], fill=(*mix(CREAM, BLUSH, 0.55), 255))
    image = image.filter(ImageFilter.GaussianBlur(6))
    return image


def rounded_card(
    image: Image.Image, box: tuple[int, int, int, int], radius: int = 22, fill=WHITE, outline=None
) -> None:
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        [x0 + 4, y0 + 10, x1 + 4, y1 + 10], radius=radius, fill=(120, 80, 90, 26)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    image.alpha_composite(shadow)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline)


# --------------------------------------------------------------------------
# real CLI output
# --------------------------------------------------------------------------


def run_cli(args: list[str], home: Path) -> list[tuple[str, tuple[int, int, int]]]:
    env = {
        **os.environ,
        "OZURE_HOME": str(home),
        "OZURE_MOCK": "1",
        "NO_COLOR": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "-m", "ozure", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    lines: list[tuple[str, tuple[int, int, int]]] = []
    for line in (result.stdout + result.stderr).rstrip().splitlines():
        # Consolas has no check mark; colour carries the meaning instead.
        text = line.replace("✓ ", "").replace("✗ ", "").rstrip()
        lines.append((text, style(line)))
    return lines


def style(line: str) -> tuple[int, int, int]:
    stripped = line.strip()
    if stripped.startswith(("ok ", "wrote ", "✓")):
        return GREEN
    if stripped.startswith(("dry run", "plan")):
        return AMBER
    if stripped.startswith("error"):
        return (198, 90, 97)
    if " → " in line:
        return TEXT
    if stripped.startswith(
        ("slot", "slug", "catalog", "name", "film", "settings", "kind", "recipes", "about")
    ):
        return DIM
    if stripped and set(stripped) <= {"-", " "}:
        return (226, 208, 214)
    if stripped.startswith(("backup:", "next:", "hint:", "mine:", "bundled:", "  ")):
        return DIM
    return TEXT


# --------------------------------------------------------------------------
# drawing blocks
# --------------------------------------------------------------------------


def draw_terminal(
    image: Image.Image,
    lines: list[tuple[str, tuple[int, int, int]]],
    command: str,
    typed: str,
    *,
    box: tuple[int, int, int, int],
    alpha: float = 1.0,
    t: float = 0.0,
) -> None:
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(box, radius=18, fill=(*WHITE, 255), outline=(240, 214, 220, 255))
    draw.rounded_rectangle([x0, y0, x1, y0 + 42], radius=18, fill=(*BLUSH, 255))
    draw.rectangle([x0, y0 + 26, x1, y0 + 42], fill=(*BLUSH, 255))
    for index, colour in enumerate([PETAL, (246, 208, 166), (185, 216, 200)]):
        cx = x0 + 24 + index * 18
        draw.ellipse([cx, y0 + 16, cx + 10, y0 + 26], fill=(*colour, 255))
    draw.text(
        (x1 - 20, y0 + 13), "ozure · USB PTP console", font=qfont(15), fill=(*DIM, 255), anchor="ra"
    )

    font = monofont(16)
    monobold = ImageFont.truetype(MONO_BOLD, 16)
    y = y0 + 62
    draw.text((x0 + 26, y), "$", font=monobold, fill=(*ROSE, 255))
    draw.text((x0 + 44, y), typed, font=font, fill=(*INK, 255))
    if typed and int(t * 2.2) % 2 == 0:
        caret = x0 + 44 + font.getlength(typed)
        draw.rectangle([caret + 2, y + 2, caret + 8, y + 17], fill=(*PETAL, 255))
    else:
        draw.text((x0 + 44, y), " ", font=font, fill=(*INK, 255))
    y += 30
    for text, colour in lines:
        if text:
            draw.text((x0 + 26, y), text, font=font, fill=(*colour, 255))
        y += 22
        if y > y1 - 16:
            break
    if alpha < 1:
        layer.putalpha(layer.getchannel("A").point(lambda value: round(value * alpha)))
    image.alpha_composite(layer)


def draw_chip(
    image: Image.Image, box: tuple[int, int, int, int], slot: str, label: str, alpha: float
) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(box, radius=14, fill=(*WHITE, 255), outline=(*PETAL, 255), width=2)
    x0, y0, _, y1 = box
    draw.text((x0 + 16, (y0 + y1) / 2), slot, font=qfont(20), fill=(*ROSE, 255), anchor="lm")
    draw.text((x0 + 62, (y0 + y1) / 2), label, font=qfont(19), fill=(*INK, 255), anchor="lm")
    if alpha < 1:
        layer.putalpha(layer.getchannel("A").point(lambda value: round(value * alpha)))
    image.alpha_composite(layer)


def bubble(
    image: Image.Image,
    box: tuple[int, int, int, int],
    text_lines: list[str],
    *,
    who: str,
    alpha: float,
    fill: tuple[int, int, int],
) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(box, radius=20, fill=(*fill, 255))
    x0, y0, _, _ = box
    draw.text((x0 + 22, y0 + 16), who, font=qfont(14), fill=(*DIM, 255))
    y = y0 + 42
    for line in text_lines:
        draw.text((x0 + 22, y), line, font=qfont(22), fill=(*INK, 255))
        y += 32
    if alpha < 1:
        layer.putalpha(layer.getchannel("A").point(lambda value: round(value * alpha)))
    image.alpha_composite(layer)


def paste_logo(image: Image.Image, width: int, xy: tuple[int, int], alpha: float = 1.0) -> None:
    logo = Image.open(ASSETS / "logo.png").convert("RGBA")
    height = round(logo.height * width / logo.width)
    logo = logo.resize((width, height), Image.LANCZOS)
    if alpha < 1:
        logo.putalpha(logo.getchannel("A").point(lambda value: round(value * alpha)))
    image.alpha_composite(logo, xy)


def paste_mascot(image: Image.Image, size: int, xy: tuple[int, int], alpha: float = 1.0) -> None:
    mascot = Image.open(ASSETS / "icon.png").convert("RGBA")
    mascot = mascot.resize((size, size), Image.LANCZOS)
    if alpha < 1:
        mascot.putalpha(mascot.getchannel("A").point(lambda value: round(value * alpha)))
    image.alpha_composite(mascot, xy)


# --------------------------------------------------------------------------
# the film
# --------------------------------------------------------------------------


class Promo:
    def __init__(self, home: Path):
        self.connect = run_cli(["connect"], home)
        self.listing = run_cli(["list"], home)
        self.catalogs = run_cli(["catalogs"], home)
        self.dry = run_cli(["apply", "kodak-gold-200", "--slot", "C6"], home)
        written = run_cli(["apply", "kodak-gold-200", "--slot", "C6", "--yes"], home)
        # The diff already had its own step; keep the success line and the backup.
        self.write = [line for line in written if " → " not in line[0]]

        # terminal script: command, output, start
        self.steps = []
        start = 8.2
        for command, output in (
            ("ozure connect", self.connect),
            ("ozure list", self.listing[:11]),
            ("ozure apply kodak-gold-200 --slot C6", self.dry),
            ("ozure apply kodak-gold-200 --slot C6 --yes", self.write),
        ):
            typing = len(command) / 55 + 0.35
            reveal = len(output) / 7.0
            hold = 0.7 if "kodak" not in command else 1.1
            duration = typing + reveal + hold
            self.steps.append(
                {
                    "command": command,
                    "output": output,
                    "start": start,
                    "typing": typing,
                    "duration": duration,
                }
            )
            start += duration
        self.catalog_scene = start + 0.4
        self.skill_scene = self.catalog_scene + 4.6
        self.cta_scene = self.skill_scene + 5.0
        self.end = self.cta_scene + 5.4

    # -- scenes ---------------------------------------------------------

    def frame(self, t: float) -> Image.Image:
        image = background()

        if t < 4.2:
            self.scene_intro(image, t)
        elif t < 8.2:
            self.scene_seven(image, t)
        elif t < self.catalog_scene:
            self.scene_terminal(image, t)
        elif t < self.skill_scene:
            self.scene_catalogs(image, t)
        elif t < self.cta_scene:
            self.scene_skill(image, t)
        else:
            self.scene_cta(image, t)
        return image.convert("RGB")

    def scene_intro(self, image: Image.Image, t: float) -> None:
        reveal = ease(t / 0.9)
        width = int(520 + 24 * reveal)
        paste_logo(image, width, (W // 2 - width // 2, 196 - int(16 * (1 - reveal))), alpha=reveal)
        fade_text(
            image,
            (W / 2, 452),
            "Recetas Fujifilm: del catálogo a la cámara",
            qfont(34),
            INK,
            ease((t - 1.0) / 0.8),
            anchor="ma",
        )
        fade_text(
            image,
            (W / 2, 508),
            "CLI + skill · USB PTP · sin GUI, sin tarjetas",
            qfont(22),
            DIM,
            ease((t - 1.7) / 0.8),
            anchor="ma",
        )

    def scene_seven(self, image: Image.Image, t: float) -> None:
        fade_text(
            image,
            (110, 120),
            "Tu cámara ya tiene 7 recetas",
            qfont(40),
            INK,
            ease((t - 4.3) / 0.45),
        )
        fade_text(
            image,
            (110, 178),
            "C1–C7. Hasta ahora solo se tocaban con el dedo y la rueda.",
            qfont(23),
            TEXT,
            ease((t - 4.6) / 0.45),
        )

        slots = [
            ("C1", "Acros Night"),
            ("C2", "Classic Chrome City"),
            ("C3", "Eterna Cinema"),
            ("C4", "Portra Soft"),
            ("C5", "Velvia Punch"),
            ("C6", "Kodak Gold 200"),
            ("C7", "—"),
        ]
        for index, (slot, label) in enumerate(slots):
            appear = 4.85 + index * 0.16
            alpha = ease((t - appear) / 0.4)
            if alpha <= 0:
                continue
            y = 248 + index * 56 - int(10 * (1 - alpha))
            draw_chip(image, (110, y, 610, y + 44), slot, label, alpha)

        right = ease((t - 6.2) / 0.5)
        if right > 0:
            rounded_card(image, (700, 250, 1170, 500))
            fade_text(image, (736, 286), "ozure", qfont(26), ROSE, right)
            fade_text(image, (736, 330), "las lee", qfont(28), INK, right)
            fade_text(image, (736, 374), "las edita", qfont(28), INK, right * 0.97)
            fade_text(image, (736, 418), "las reinstala", qfont(28), INK, right * 0.94)
            fade_text(image, (736, 462), "por USB, sin GUI", qfont(18), DIM, right * 0.9)

    def scene_terminal(self, image: Image.Image, t: float) -> None:
        step = next((step for step in reversed(self.steps) if t >= step["start"]), self.steps[0])
        local = t - step["start"]
        typed = step["command"][: int(max(0.0, local) * 55)]
        if local < step["typing"]:
            output: list[tuple[str, tuple[int, int, int]]] = []
        else:
            visible = int((local - step["typing"]) * 7.0) + 1
            output = step["output"][:visible]

        captions = {
            0: ("1 · Conecta", "la cámara aparece en cuanto está en modo PTP"),
            1: ("2 · Lee", "los siete slots, con sus ajustes completos"),
            2: ("3 · Prueba en seco", "diff antes de tocar nada; exit 10, nada escrito"),
            3: ("4 · Escribe y verifica", "relee el slot y compara campo a campo"),
        }
        index = self.steps.index(step)
        title, subtitle = captions[index]
        fade_text(image, (90, 54), title, qfont(32), INK, 1.0)
        fade_text(image, (92, 100), subtitle, qfont(20), DIM, 1.0)

        card_bottom = 150 + 62 + 30 + len(step["output"]) * 22 + 42
        draw_terminal(
            image,
            output,
            step["command"],
            typed,
            box=(90, 150, W - 90, min(H - 70, card_bottom)),
            t=t,
        )
        paste_mascot(image, 96, (W - 150, 40), alpha=0.95)

    def scene_catalogs(self, image: Image.Image, t: float) -> None:
        reveal = ease((t - self.catalog_scene) / 0.6)
        fade_text(image, (90, 56), "126 recetas en 10 catálogos", qfont(38), INK, reveal)
        fade_text(
            image,
            (92, 108),
            "Fuji X Weekly, Osan-Bilgi, Alex Armitage… y el tuyo, con lo que tengas en la cámara.",
            qfont(20),
            TEXT,
            ease((t - self.catalog_scene - 0.2) / 0.6),
        )
        draw_terminal(
            image,
            self.catalogs[:12],
            "ozure catalogs",
            "ozure catalogs" if reveal > 0.6 else "ozure catal",
            box=(90, 160, W - 90, 160 + 62 + 30 + 12 * 22 + 36),
            alpha=reveal,
            t=t,
        )
        fade_text(
            image,
            (92, 596),
            "$ ozure catalog export    guarda las 7 de tu cámara en tu catálogo",
            qfont(21),
            ROSE,
            ease((t - self.catalog_scene - 1.4) / 0.6),
        )

    def scene_skill(self, image: Image.Image, t: float) -> None:
        reveal = ease((t - self.skill_scene) / 0.6)
        fade_text(image, (90, 56), "También es un skill", qfont(38), INK, reveal)
        fade_text(
            image,
            (92, 108),
            "Se lo pides en lenguaje natural y el agente ejecuta el CLI, con los mismos límites.",
            qfont(20),
            TEXT,
            ease((t - self.skill_scene - 0.2) / 0.6),
        )
        bubble(
            image,
            (90, 186, 690, 300),
            ["conecta a mi Fuji y ponme la receta", "Kodak Gold 200 en C6"],
            who="tú",
            alpha=ease((t - self.skill_scene - 0.6) / 0.5),
            fill=BLUSH,
        )
        bubble(
            image,
            (300, 330, W - 90, 470),
            [
                "Hecho: C6 = Kodak Gold 200. Antes te enseño",
                "el diff, escribo con --yes y releo el slot.",
                "Backup en ~/.ozure/backups/…",
            ],
            who="agente · ozure",
            alpha=ease((t - self.skill_scene - 1.4) / 0.5),
            fill=WHITE,
        )
        fade_text(
            image,
            (W - 100, 500),
            "OK · written · verified · mismatches: []",
            monofont(19),
            GREEN,
            ease((t - self.skill_scene - 2.2) / 0.5),
            anchor="ra",
        )
        paste_mascot(image, 92, (W - 150, 44), alpha=0.9)

    def scene_cta(self, image: Image.Image, t: float) -> None:
        reveal = ease((t - self.cta_scene) / 0.7)
        width = int(500 + 30 * reveal)
        paste_logo(image, width, (W // 2 - width // 2, 168 - int(14 * (1 - reveal))), alpha=reveal)
        fade_text(
            image,
            (W / 2, 396),
            "github.com/AlPeFe/ozure",
            qfont(34),
            INK,
            ease((t - self.cta_scene - 0.6) / 0.6),
            anchor="ma",
        )
        fade_text(
            image,
            (W / 2, 452),
            "CLI + skill · MIT · tus recetas se quedan en tu máquina",
            qfont(21),
            TEXT,
            ease((t - self.cta_scene - 1.1) / 0.6),
            anchor="ma",
        )
        paste_mascot(image, 104, (W - 170, H - 150), alpha=ease((t - self.cta_scene - 1.4) / 0.6))


# --------------------------------------------------------------------------
# encoding
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gif", action="store_true", help="also write assets/promo-preview.gif")
    parser.add_argument("--poster", default="", help="write this frame (seconds) as a PNG")
    args = parser.parse_args()

    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    home = Path(tempfile.mkdtemp(prefix="ozure-promo-"))
    promo = Promo(home)
    total_frames = int(promo.end * FPS)
    out = ASSETS / "promo.mp4"
    print(f"{promo.end:.1f}s · {total_frames} frames · {W}x{H}@{FPS}")

    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    for index in range(total_frames):
        frame = promo.frame(index / FPS)
        assert process.stdin is not None
        process.stdin.write(frame.tobytes())
    assert process.stdin is not None
    process.stdin.close()
    process.wait()
    print(f"wrote {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")

    if args.poster:
        seconds = float(args.poster)
        promo.frame(seconds).save(ASSETS / "promo-poster.png")
        print("wrote assets/promo-poster.png")

    if args.gif:
        frames = [
            promo.frame(index / 15).quantize(colors=96)
            for index in range(0, int(promo.end * 15), 2)
        ]
        frames[0].save(
            ASSETS / "promo-preview.gif",
            save_all=True,
            append_images=frames[1:],
            duration=133,
            loop=0,
            optimize=True,
        )
        print("wrote assets/promo-preview.gif")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
