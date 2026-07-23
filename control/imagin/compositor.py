import io
from dataclasses import dataclass
from typing import NamedTuple

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

from .palette import BrandPalette, DEFAULT_PALETTE, ensure_min_contrast
from .templates import (
    CENTERED_EDITORIAL,
    PosterTemplate,
    ResolvedLayout,
    PixelRect,
    resolve_layout,
)

FONT_FAMILY = "Noto Sans Thai"

# Inner padding between a region's edge and the text drawn inside it.
REGION_INNER_PAD = 16
# Padding inside the action card, and geometric quiet-zone floor for the QR
# (the QR PNG additionally carries the spec's own 4-module quiet border).
ACTION_CARD_PAD = 12
QR_MAX_SIDE = 150


class TextOverflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextBlockBounds:
    """The exact pixel-space box the compositor drew one piece of text
    into, plus the literal text it drew there. QA crops and OCRs each
    block in isolation and compares exactly."""

    name: str
    text: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class RegionBounds:
    """A non-text controlled region on the final poster (logo, QR, panel,
    action card). QA's unexpected-text gate treats logo/QR as allowed
    regions; layout QA validates all of them against the template."""

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
    panel_region: RegionBounds | None = None
    action_region: RegionBounds | None = None
    layout: ResolvedLayout | None = None
    font_sizes: dict | None = None


class _DrawnTextBlock(NamedTuple):
    x: int
    y: int
    width: int
    height: int


def _rounded_rect_path(ctx: cairo.Context, x: float, y: float, w: float, h: float, radius: float) -> None:
    r = min(radius, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -1.5708, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, 1.5708)
    ctx.arc(x + r, y + h - r, r, 1.5708, 3.14159)
    ctx.arc(x + r, y + r, r, 3.14159, 4.71239)
    ctx.close_path()


def _build_layout_at_size(ctx: cairo.Context, text: str, weight: str, size: int, max_width: int, align: str):
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription(f"{FONT_FAMILY} {weight} {size}".replace("  ", " ")))
    layout.set_width(max_width * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_alignment(Pango.Alignment.CENTER if align == "center" else Pango.Alignment.LEFT)
    layout.set_text(text, -1)
    return layout


def _fit_text(
    ctx: cairo.Context,
    text: str,
    weight: str,
    sizes: tuple[int, int],
    region: PixelRect,
    align: str,
    inner_pad: int = REGION_INNER_PAD,
):
    """Find the largest font size in [min, max] whose wrapped layout fits
    the region (minus inner padding). Deterministic; if even the minimum
    size overflows, raise TextOverflowError — the hard overflow gate."""
    min_size, max_size = sizes
    max_w = region.width - 2 * inner_pad
    max_h = region.height - 2 * inner_pad
    for size in range(max_size, min_size - 1, -2):
        layout = _build_layout_at_size(ctx, text, weight, size, max_w, align)
        _ink, logical = layout.get_pixel_extents()
        if logical.height <= max_h and logical.width <= max_w:
            return layout, size, logical
    raise TextOverflowError(
        f"text '{text[:30]}...' cannot fit region {region.width}x{region.height}px "
        f"even at minimum size {min_size}pt"
    )


def _draw_layout(ctx: cairo.Context, layout, region: PixelRect, logical, rgb, inner_pad: int = REGION_INNER_PAD) -> _DrawnTextBlock:
    x = region.x + inner_pad
    y = region.y + inner_pad
    ctx.save()
    ctx.set_source_rgb(*rgb)
    ctx.translate(x, y)
    PangoCairo.show_layout(ctx, layout)
    ctx.restore()
    return _DrawnTextBlock(x=x + logical.x, y=y + logical.y, width=logical.width, height=logical.height)


def _trim_transparent_margins(png_bytes: bytes) -> bytes:
    """Crop fully-transparent outer margins from a logo PNG for placement.

    Affects ONLY the in-memory composition copy — the stored asset bytes,
    their sha256, and the provenance record are untouched. The logo is
    never redrawn, stretched non-uniformly, or touched by the image model.
    """
    from PIL import Image

    image = Image.open(io.BytesIO(png_bytes))
    if image.mode != "RGBA":
        return png_bytes
    bbox = image.getchannel("A").getbbox()
    if bbox is None or bbox == (0, 0, image.width, image.height):
        return png_bytes
    buffer = io.BytesIO()
    image.crop(bbox).save(buffer, format="PNG")
    return buffer.getvalue()


def _paint_logo_fitted(ctx: cairo.Context, logo_png: bytes, region: PixelRect) -> RegionBounds:
    """Paint the logo inside its region, preserving aspect ratio (uniform
    scale, centered) — fitted, never stretched or cropped."""
    trimmed = _trim_transparent_margins(logo_png)
    source = cairo.ImageSurface.create_from_png(io.BytesIO(trimmed))
    sw, sh = source.get_width(), source.get_height()
    scale = min(region.width / sw, region.height / sh)
    draw_w, draw_h = sw * scale, sh * scale
    offset_x = region.x + (region.width - draw_w) / 2
    offset_y = region.y + (region.height - draw_h) / 2

    ctx.save()
    ctx.translate(offset_x, offset_y)
    ctx.scale(scale, scale)
    ctx.set_source_surface(source, 0, 0)
    ctx.paint()
    ctx.restore()

    return RegionBounds(
        name="logo", x=int(offset_x), y=int(offset_y),
        width=int(round(draw_w)), height=int(round(draw_h)),
    )


def _paint_qr(ctx: cairo.Context, qr_png: bytes, x: int, y: int, side: int) -> RegionBounds:
    source = cairo.ImageSurface.create_from_png(io.BytesIO(qr_png))
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(side / source.get_width(), side / source.get_height())
    ctx.set_source_surface(source, 0, 0)
    ctx.paint()
    ctx.restore()
    return RegionBounds(name="qr", x=x, y=y, width=side, height=side)


def _draw_action_card(
    ctx: cairo.Context,
    region: PixelRect,
    cta: str,
    cta_sizes: tuple[int, int],
    qr_png: bytes,
    accent_rgb,
    align: str,
) -> tuple[TextBlockBounds, RegionBounds, int]:
    """One coherent action component: a card containing the CTA (accent
    colour, bold) and the QR together. The QR is fully contained in the
    card with its quiet zone preserved (card padding >= geometric quiet
    floor, plus the QR image's own spec border)."""
    ctx.save()
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.98)
    _rounded_rect_path(ctx, region.x, region.y, region.width, region.height, 14)
    ctx.fill()
    ctx.set_source_rgb(*accent_rgb)
    ctx.set_line_width(3)
    _rounded_rect_path(ctx, region.x + 1.5, region.y + 1.5, region.width - 3, region.height - 3, 13)
    ctx.stroke()
    ctx.restore()

    inner = PixelRect(
        x=region.x + ACTION_CARD_PAD,
        y=region.y + ACTION_CARD_PAD,
        width=region.width - 2 * ACTION_CARD_PAD,
        height=region.height - 2 * ACTION_CARD_PAD,
    )

    if inner.width >= int(2.2 * inner.height):
        # Row layout: CTA left, QR right.
        qr_side = min(inner.height, QR_MAX_SIDE, int(inner.width * 0.45))
        qr_x = inner.right - qr_side
        qr_y = inner.y + (inner.height - qr_side) // 2
        cta_region = PixelRect(inner.x, inner.y, inner.width - qr_side - 16, inner.height)
    else:
        # Stacked layout: CTA on top, QR below, centered.
        qr_side = min(int(inner.height * 0.62), QR_MAX_SIDE, inner.width)
        qr_x = inner.x + (inner.width - qr_side) // 2
        qr_y = inner.bottom - qr_side
        cta_region = PixelRect(inner.x, inner.y, inner.width, inner.height - qr_side - 8)

    qr_region = _paint_qr(ctx, qr_png, qr_x, qr_y, qr_side)

    cta_layout, cta_size, logical = _fit_text(ctx, cta, "Bold", cta_sizes, cta_region, align, inner_pad=8)
    cta_bounds = _draw_layout(ctx, cta_layout, cta_region, logical, accent_rgb, inner_pad=8)
    cta_block = TextBlockBounds(name="cta", text=cta, **cta_bounds._asdict())
    return cta_block, qr_region, cta_size


def compose_poster_from_layout(
    hero_png: bytes,
    template: PosterTemplate,
    layout: ResolvedLayout,
    palette: BrandPalette,
    headline: str,
    body_lines: list[str],
    cta: str,
    logo_png: bytes,
    qr_png: bytes,
) -> ComposedPoster:
    """Core composition: place every element into the SAME resolved layout
    the background generator was instructed with. No element chooses its
    own position; the template contract decides everything."""
    width, height = layout.width, layout.height
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)

    hero_surface = cairo.ImageSurface.create_from_png(io.BytesIO(hero_png))
    ctx.save()
    ctx.scale(width / hero_surface.get_width(), height / hero_surface.get_height())
    ctx.set_source_surface(hero_surface, 0, 0)
    ctx.paint()
    ctx.restore()

    # Contrast is enforced, deterministically, before any text is drawn.
    text_rgb = ensure_min_contrast(palette.text_rgb, palette.panel_rgb, template.min_contrast_ratio)
    accent_rgb = ensure_min_contrast(palette.accent_rgb, palette.panel_rgb, template.min_contrast_ratio)

    # Content panel: sized to its assigned template region — never a
    # canvas-wide band, never covering the protected subject region.
    panel = layout.panel
    ctx.save()
    ctx.set_source_rgba(*palette.panel_rgb, template.panel_opacity)
    _rounded_rect_path(ctx, panel.x, panel.y, panel.width, panel.height, 18)
    ctx.fill()
    ctx.restore()
    panel_region = RegionBounds(name="panel", x=panel.x, y=panel.y, width=panel.width, height=panel.height)

    text_blocks: list[TextBlockBounds] = []
    font_sizes: dict = {}

    headline_layout, headline_size, logical = _fit_text(
        ctx, headline, "Bold", template.headline_sizes, layout.headline, template.text_align
    )
    bounds = _draw_layout(ctx, headline_layout, layout.headline, logical, text_rgb)
    text_blocks.append(TextBlockBounds(name="headline", text=headline, **bounds._asdict()))
    font_sizes["headline"] = headline_size

    body_text = "\n".join(body_lines)
    body_layout, body_size, logical = _fit_text(
        ctx, body_text, "", template.body_sizes, layout.body, template.text_align
    )
    bounds = _draw_layout(ctx, body_layout, layout.body, logical, text_rgb)
    text_blocks.append(TextBlockBounds(name="body", text=body_text, **bounds._asdict()))
    font_sizes["body"] = body_size

    cta_block, qr_region, cta_size = _draw_action_card(
        ctx, layout.action, cta, template.cta_sizes, qr_png, accent_rgb, template.text_align
    )
    text_blocks.append(cta_block)
    font_sizes["cta"] = cta_size

    logo_region = _paint_logo_fitted(ctx, logo_png, layout.logo)
    action_region = RegionBounds(
        name="action", x=layout.action.x, y=layout.action.y,
        width=layout.action.width, height=layout.action.height,
    )

    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return ComposedPoster(
        png_bytes=buffer.getvalue(),
        text_blocks=text_blocks,
        logo_region=logo_region,
        qr_region=qr_region,
        panel_region=panel_region,
        action_region=action_region,
        layout=layout,
        font_sizes=font_sizes,
    )


def compose_poster_from_spec(hero_png: bytes, spec, logo_png: bytes, qr_png: bytes) -> ComposedPoster:
    """Compose using the shared DesignSpec — the same object the ComfyUI
    prompt builder consumed. This is the pipeline's entry point."""
    template = spec.template if spec.template is not None else CENTERED_EDITORIAL
    layout = spec.layout if spec.layout is not None else resolve_layout(template, spec.width, spec.height)
    return compose_poster_from_layout(
        hero_png=hero_png, template=template, layout=layout, palette=spec.palette,
        headline=spec.copy.headline, body_lines=spec.copy.body, cta=spec.copy.cta,
        logo_png=logo_png, qr_png=qr_png,
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
    """Compatibility wrapper (pre-template signature): composes with the
    centered_editorial template resolved at the requested canvas size and
    the default palette."""
    template = CENTERED_EDITORIAL
    layout = resolve_layout(template, width, height)
    return compose_poster_from_layout(
        hero_png=hero_png, template=template, layout=layout, palette=DEFAULT_PALETTE,
        headline=headline, body_lines=body_lines, cta=cta,
        logo_png=logo_png, qr_png=qr_png,
    )
