import io
from dataclasses import dataclass
from typing import NamedTuple

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

FONT_HEADLINE = "Noto Sans Thai Bold 48"
# 28 (was 24): the first Docker QA run showed the OCR recognizer reliably
# reads this typeface at headline size but drops thin Thai upper vowels at
# 24px body size. 28px improves real-world legibility of body copy AND sits
# in the size range the QA recognizer demonstrably reads correctly. The
# overflow gate still holds: two body lines at 28px ≈ 76px < the 140px cap.
FONT_BODY = "Noto Sans Thai 28"
MARGIN = 64
LOGO_SIZE = 120
QR_SIZE = 140
CTA_MAX_HEIGHT = 64

# Text is drawn in solid black over a near-opaque light "scrim" panel that
# is painted between the hero image and the text. Without it, black text
# sits directly on a busy, arbitrary AI-generated background: unreadable in
# dark regions for a human, and — as the first live run proved — a source
# of OCR garbage where the hero's own texture bleeds into the text crop.
# The scrim guarantees a known high-contrast backing for every glyph, which
# is what makes the deterministic OCR exact-match gate meaningful.
# Opacity 0.96: high enough that hallucinated background text/typography
# cannot remain legible through the panel (the live run showed generated
# white Thai text bleeding through at 0.9), while keeping a hint of the
# hero's tone so the panel doesn't read as a pasted white sticker.
TEXT_RGB = (0.0, 0.0, 0.0)
SCRIM_RGBA = (1.0, 1.0, 1.0, 0.96)
SCRIM_PAD = 24


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
class RegionBounds:
    """A non-text controlled region on the final poster (logo, QR). QA's
    unexpected-text gate treats these as allowed regions: the official
    logo may legitimately contain wordmark text, and QR modules sometimes
    trip OCR detection — both are authorized content at known positions."""

    name: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ComposedPoster:
    png_bytes: bytes
    text_blocks: list[TextBlockBounds]
    logo_region: RegionBounds | None = None
    qr_region: RegionBounds | None = None


class _DrawnTextBlock(NamedTuple):
    x: int
    y: int
    width: int
    height: int


def _build_layout(ctx: cairo.Context, text: str, font_desc: str, max_width: int):
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription(font_desc))
    layout.set_width(max_width * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_text(text, -1)
    return layout


def _measure_text(layout, text: str, x: int, y: int, max_height: int) -> _DrawnTextBlock:
    _ink_rect, logical_rect = layout.get_pixel_extents()
    if logical_rect.height > max_height:
        raise TextOverflowError(
            f"text '{text[:30]}...' is {logical_rect.height}px tall, exceeds region height {max_height}px"
        )
    return _DrawnTextBlock(
        x=x + logical_rect.x,
        y=y + logical_rect.y,
        width=logical_rect.width,
        height=logical_rect.height,
    )


def _render_text(ctx: cairo.Context, layout, x: int, y: int) -> None:
    ctx.save()
    ctx.set_source_rgb(*TEXT_RGB)  # explicit: never inherit the hero as the text colour
    ctx.translate(x, y)
    PangoCairo.show_layout(ctx, layout)
    ctx.restore()


def _paint_scrim(ctx: cairo.Context, blocks: list[_DrawnTextBlock], width: int, height: int) -> None:
    if not blocks:
        return
    left = min(b.x for b in blocks) - SCRIM_PAD
    top = min(b.y for b in blocks) - SCRIM_PAD
    right = max(b.x + b.width for b in blocks) + SCRIM_PAD
    bottom = max(b.y + b.height for b in blocks) + SCRIM_PAD
    left = max(0, left)
    top = max(0, top)
    right = min(width, right)
    bottom = min(height, bottom)
    ctx.save()
    ctx.set_source_rgba(*SCRIM_RGBA)
    ctx.rectangle(left, top, right - left, bottom - top)
    ctx.fill()
    ctx.restore()


def _paint_scaled_image(ctx: cairo.Context, png_bytes: bytes, x: int, y: int, target_size: int) -> None:
    source_surface = cairo.ImageSurface.create_from_png(io.BytesIO(png_bytes))
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(target_size / source_surface.get_width(), target_size / source_surface.get_height())
    ctx.set_source_surface(source_surface, 0, 0)
    ctx.paint()
    ctx.restore()


def _trim_transparent_margins(png_bytes: bytes) -> bytes:
    """Crop fully-transparent outer margins from a logo PNG for placement.

    This affects ONLY the in-memory copy used for composition — the stored
    asset bytes, their sha256, and the provenance record are untouched
    (the provenance gate hashes the stored bytes, not this working copy).
    Official logos frequently ship with generous transparent padding that
    makes an aspect-fitted placement look tiny and off-center; trimming
    the transparent bounds fixes placement without altering a single
    visible pixel of the mark. The logo is never redrawn, stretched
    non-uniformly, or touched by the image model.
    """
    from PIL import Image  # local import: PIL is a runtime dep already

    image = Image.open(io.BytesIO(png_bytes))
    if image.mode != "RGBA":
        return png_bytes
    bbox = image.getchannel("A").getbbox()
    if bbox is None or bbox == (0, 0, image.width, image.height):
        return png_bytes
    buffer = io.BytesIO()
    image.crop(bbox).save(buffer, format="PNG")
    return buffer.getvalue()


def _paint_logo_fitted(
    ctx: cairo.Context, logo_png: bytes, x: int, y: int, box_size: int
) -> RegionBounds:
    """Paint the logo inside a box_size square, preserving aspect ratio.

    Unlike _paint_scaled_image (which scales width and height independently
    and therefore distorts any non-square image), this scales both axes by
    the same factor — the logo is fitted, never stretched or cropped — and
    is centered within the box. Returns the region actually painted.
    """
    trimmed = _trim_transparent_margins(logo_png)
    source_surface = cairo.ImageSurface.create_from_png(io.BytesIO(trimmed))
    source_w = source_surface.get_width()
    source_h = source_surface.get_height()
    scale = min(box_size / source_w, box_size / source_h)
    draw_w = source_w * scale
    draw_h = source_h * scale
    offset_x = x + (box_size - draw_w) / 2
    offset_y = y + (box_size - draw_h) / 2

    ctx.save()
    ctx.translate(offset_x, offset_y)
    ctx.scale(scale, scale)
    ctx.set_source_surface(source_surface, 0, 0)
    ctx.paint()
    ctx.restore()

    return RegionBounds(
        name="logo",
        x=int(offset_x),
        y=int(offset_y),
        width=int(round(draw_w)),
        height=int(round(draw_h)),
    )


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

    max_width = width - 2 * MARGIN
    body_text = "\n".join(body_lines)
    specs = [
        ("headline", headline, FONT_HEADLINE, 160),
        ("body", body_text, FONT_BODY, 140),
        ("cta", cta, FONT_BODY, CTA_MAX_HEIGHT),
    ]

    # Pass 1 — lay out and measure every block (this also enforces the hard
    # overflow gate) so we know the exact region the scrim must cover before
    # any text is painted.
    placed = []
    y = height - 420
    for name, text, font_desc, max_height in specs:
        layout = _build_layout(ctx, text, font_desc, max_width)
        bounds = _measure_text(layout, text, MARGIN, y, max_height)
        placed.append((name, text, layout, y, bounds))
        y += bounds.height + 16

    # Pass 2 — paint the contrast scrim under the text, then the text on top.
    _paint_scrim(ctx, [bounds for *_rest, bounds in placed], width, height)

    text_blocks: list[TextBlockBounds] = []
    for name, text, layout, base_y, bounds in placed:
        _render_text(ctx, layout, MARGIN, base_y)
        text_blocks.append(TextBlockBounds(name=name, text=text, **bounds._asdict()))

    logo_region = _paint_logo_fitted(ctx, logo_png, MARGIN, MARGIN, LOGO_SIZE)

    # QR: the qrcode library's PNG already includes the spec's 4-module
    # quiet zone as part of the image; painting it square (QR codes are
    # square by construction) onto the poster preserves that quiet zone.
    qr_x = width - MARGIN - QR_SIZE
    qr_y = height - MARGIN - QR_SIZE
    _paint_scaled_image(ctx, qr_png, qr_x, qr_y, QR_SIZE)
    qr_region = RegionBounds(name="qr", x=qr_x, y=qr_y, width=QR_SIZE, height=QR_SIZE)

    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return ComposedPoster(
        png_bytes=buffer.getvalue(),
        text_blocks=text_blocks,
        logo_region=logo_region,
        qr_region=qr_region,
    )
