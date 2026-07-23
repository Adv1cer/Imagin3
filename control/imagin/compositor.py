import io
from dataclasses import dataclass
from typing import NamedTuple

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

FONT_HEADLINE = "Noto Sans Thai Bold 48"
FONT_BODY = "Noto Sans Thai 24"
MARGIN = 64
LOGO_SIZE = 120
QR_SIZE = 140
CTA_MAX_HEIGHT = 64


class TextOverflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextBlockBounds:
    """The exact pixel-space box the compositor drew one piece of text
    into, plus the literal text it drew there.

    QA (imagin.qa.ocr_check.check_text_blocks_exact_match) uses this to
    crop and OCR each block in isolation instead of running OCR over the
    whole poster and checking whether the right substrings show up
    somewhere in one big blob. Cropping to just this block's own box (and
    upscaling it) gives the OCR engine a much better chance of reading it
    correctly, and comparing per-block keeps the check an exact match
    instead of papering over misreads with a fuzzy similarity score.
    """

    name: str
    text: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ComposedPoster:
    png_bytes: bytes
    text_blocks: list[TextBlockBounds]


class _DrawnTextBlock(NamedTuple):
    x: int
    y: int
    width: int
    height: int


def _draw_text(ctx: cairo.Context, text: str, font_desc: str, x: int, y: int, max_width: int, max_height: int) -> _DrawnTextBlock:
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription(font_desc))
    layout.set_width(max_width * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_text(text, -1)
    _ink_rect, logical_rect = layout.get_pixel_extents()

    if logical_rect.height > max_height:
        raise TextOverflowError(
            f"text '{text[:30]}...' is {logical_rect.height}px tall, exceeds region height {max_height}px"
        )

    ctx.save()
    ctx.translate(x, y)
    PangoCairo.show_layout(ctx, layout)
    ctx.restore()

    return _DrawnTextBlock(
        x=x + logical_rect.x,
        y=y + logical_rect.y,
        width=logical_rect.width,
        height=logical_rect.height,
    )


def _paint_scaled_image(ctx: cairo.Context, png_bytes: bytes, x: int, y: int, target_size: int) -> None:
    source_surface = cairo.ImageSurface.create_from_png(io.BytesIO(png_bytes))
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(target_size / source_surface.get_width(), target_size / source_surface.get_height())
    ctx.set_source_surface(source_surface, 0, 0)
    ctx.paint()
    ctx.restore()


def compose_poster(
    hero_png: bytes,
    headline: str,
    body_lines: list[str],
    cta: str,
    logo_png: bytes,
    qr_png: bytes,
    width: int,
    height: int,
) -> ComposedPoster:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)

    hero_surface = cairo.ImageSurface.create_from_png(io.BytesIO(hero_png))
    ctx.save()
    ctx.scale(width / hero_surface.get_width(), height / hero_surface.get_height())
    ctx.set_source_surface(hero_surface, 0, 0)
    ctx.paint()
    ctx.restore()

    text_blocks: list[TextBlockBounds] = []

    y = height - 420
    headline_block = _draw_text(ctx, headline, FONT_HEADLINE, MARGIN, y, width - 2 * MARGIN, 160)
    text_blocks.append(TextBlockBounds(name="headline", text=headline, **headline_block._asdict()))
    y += headline_block.height + 16

    body_text = "\n".join(body_lines)
    body_block = _draw_text(ctx, body_text, FONT_BODY, MARGIN, y, width - 2 * MARGIN, 140)
    text_blocks.append(TextBlockBounds(name="body", text=body_text, **body_block._asdict()))
    y += body_block.height + 16

    cta_block = _draw_text(ctx, cta, FONT_BODY, MARGIN, y, width - 2 * MARGIN, CTA_MAX_HEIGHT)
    text_blocks.append(TextBlockBounds(name="cta", text=cta, **cta_block._asdict()))

    _paint_scaled_image(ctx, logo_png, MARGIN, MARGIN, LOGO_SIZE)
    _paint_scaled_image(ctx, qr_png, width - MARGIN - QR_SIZE, height - MARGIN - QR_SIZE, QR_SIZE)

    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return ComposedPoster(png_bytes=buffer.getvalue(), text_blocks=text_blocks)
