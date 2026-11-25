"""Render the edition's generated masthead cover.

The masthead, rules and type are a deterministic function of the
edition date. When the lead story carries an acquired og:image photo
it is composited in grayscale under the masthead — the same publisher
image the edition already embeds. With no photo the cover is
text-only, and an unreadable photo never blocks the build.
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


def _place_photo(image, draw, path, top: int, bottom: int, caption) -> None:
    """Center-crop `path` into the framed hero box, captioned below.

    Any unreadable image leaves the cover text-only — a photo never
    blocks the build.
    """
    try:
        photo = Image.open(path).convert("L")
    except (OSError, ValueError, Image.DecompressionBombError):
        return
    box_w = WIDTH - 2 * MARGIN
    box_h = bottom - top
    scale = max(box_w / photo.width, box_h / photo.height)
    resized = photo.resize(
        (
            max(1, round(photo.width * scale)),
            max(1, round(photo.height * scale)),
        )
    )
    x0 = max(0, (resized.width - box_w) // 2)
    y0 = max(0, (resized.height - box_h) // 2)
    image.paste(resized.crop((x0, y0, x0 + box_w, y0 + box_h)), (MARGIN, top))
    draw.rectangle(
        (MARGIN - 1, top - 1, MARGIN + box_w, top + box_h), outline=INK, width=2
    )
    if caption := (caption or "").strip():
        font = _fit(draw, caption, 30, box_w)
        _center(draw, caption, top + box_h + 26, font)


def render_cover(
    edition_date: date,
    output,
    *,
    label: str | None = None,
    photo=None,
    caption: str | None = None,
) -> Path:
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

    if photo is not None:
        _place_photo(image, draw, photo, y + 50, HEIGHT - 330, caption)

    footer = "PERSONAL DAILY EDITION"
    footer_font = _fit(draw, footer, 30, usable, tracking=6)
    rule(HEIGHT - 240, 2)
    _center(draw, footer, HEIGHT - 190, footer_font, tracking=6)
    rule(HEIGHT - 150, 1)
    rule(HEIGHT - 138, 4)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return output
