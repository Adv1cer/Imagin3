"""Brand palette with safe defaults, deterministic contrast enforcement,
and optional conservative derivation from the verified logo asset.

Derivation is generic (dominant saturated colour of the asset bytes) and
NEVER the only path — any failure falls back to the defaults, and every
palette records its source in design metadata. No organization-specific
colour is hardcoded anywhere.
"""

import io
from dataclasses import dataclass

RGB = tuple[float, float, float]  # each channel 0.0–1.0


@dataclass(frozen=True)
class BrandPalette:
    text_rgb: RGB     # body/headline text (drawn on the panel)
    accent_rgb: RGB   # CTA emphasis / action-card border
    panel_rgb: RGB    # content panel base colour
    source: str       # "default" | "derived_from_logo"


DEFAULT_PALETTE = BrandPalette(
    text_rgb=(0.08, 0.09, 0.11),
    accent_rgb=(0.10, 0.23, 0.47),
    panel_rgb=(1.0, 1.0, 1.0),
    source="default",
)


def _channel_lum(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (_channel_lum(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def ensure_min_contrast(fg: RGB, bg: RGB, minimum: float) -> RGB:
    """Deterministically darken fg until it meets `minimum` against bg
    (25-step bound). If it still cannot meet the target, return the
    default text colour — a colour that cannot be made readable is not
    used for text, ever."""
    current = fg
    for _ in range(25):
        if contrast_ratio(current, bg) >= minimum:
            return current
        current = tuple(c * 0.9 for c in current)
    return DEFAULT_PALETTE.text_rgb


def derive_palette_from_logo(logo_png: bytes, min_contrast: float = 4.5) -> BrandPalette:
    """Conservative accent derivation: most frequent saturated colour of
    the logo, darkened as needed to meet the contrast target on the panel.
    Any failure — undecodable bytes, no saturated colour — falls back to
    DEFAULT_PALETTE."""
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(logo_png)).convert("RGBA")
        base = Image.new("RGBA", image.size, (255, 255, 255, 255))
        base.alpha_composite(image)
        small = base.convert("RGB").resize((48, 48))
        counts: dict[tuple[int, int, int], int] = {}
        for pixel in small.getdata():
            r, g, b = pixel
            mx, mn = max(pixel), min(pixel)
            if mx > 235 and mn > 220:
                continue  # near-white background
            if mx - mn < 30:
                continue  # grays: not a usable accent
            counts[pixel] = counts.get(pixel, 0) + 1
        if not counts:
            return DEFAULT_PALETTE
        dominant = max(counts, key=counts.get)
        accent_raw: RGB = tuple(c / 255 for c in dominant)
        accent = ensure_min_contrast(accent_raw, DEFAULT_PALETTE.panel_rgb, min_contrast)
        return BrandPalette(
            text_rgb=DEFAULT_PALETTE.text_rgb,
            accent_rgb=accent,
            panel_rgb=DEFAULT_PALETTE.panel_rgb,
            source="derived_from_logo",
        )
    except Exception:
        return DEFAULT_PALETTE
