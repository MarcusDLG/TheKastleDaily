"""Render the edition's generated masthead cover.

The cover is a deterministic function of the edition date — no
third-party imagery, so it is license-clean by construction. Output is
a grayscale PNG sized for e-ink: light background, dark ink, and
classic masthead rules.
"""

from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1200
HEIGHT = 1600
MARGIN = 90
PAPER = 246
INK = 24


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _width(draw, text: str, font, tracking: int = 0) -> float:
    return draw.textlength(text, font=font) + tracking * max(len(text) - 1, 0)


def _fit(draw, text: str, size: int, max_width: int, tracking: int = 0):
    while size > 24:
        font = _font(size)
        if _width(draw, text, font, tracking) <= max_width:
            return font
        size -= 4
    return _font(24)


def _center(draw, text: str, y: int, font, tracking: int = 0) -> None:
    x = (WIDTH - _width(draw, text, font, tracking)) / 2
    for char in text:
        draw.text((x, y), char, font=font, fill=INK)
        x += draw.textlength(char, font=font) + tracking


def render_cover(edition_date: date, output, *, label: str | None = None) -> Path:
    """Draw the masthead cover for one edition date to `output` (PNG)."""
    output = Path(output)
    image = Image.new("L", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    left, right = MARGIN, WIDTH - MARGIN
    usable = right - left

    def rule(y, weight):
        draw.line([(left, y), (right, y)], fill=INK, width=weight)

    y = 170
    rule(y, 5)
    rule(y + 12, 1)

    masthead = "THE KASTLE DAILY"
    font = _fit(draw, masthead, 130, usable, tracking=8)
    y += 90
    _center(draw, masthead, y, font, tracking=8)
    y += font.size + 60

    rule(y, 1)
    rule(y + 10, 4)

    date_text = (
        f"{edition_date.strftime('%A, %B')} "
        f"{edition_date.day}, {edition_date.year}"
    )
    date_font = _fit(draw, date_text, 56, usable)
    y += 70
    _center(draw, date_text, y, date_font)
    y += date_font.size + 40

    if label := (label or "").strip():
        label_font = _fit(draw, label, 38, usable)
        _center(draw, label, y, label_font)

    footer = "PERSONAL DAILY EDITION"
    footer_font = _fit(draw, footer, 30, usable, tracking=6)
    rule(HEIGHT - 240, 2)
    _center(draw, footer, HEIGHT - 190, footer_font, tracking=6)
    rule(HEIGHT - 150, 1)
    rule(HEIGHT - 138, 4)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return output
