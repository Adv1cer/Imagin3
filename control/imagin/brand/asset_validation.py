"""Validation for automatically-downloaded brand-asset bytes.

The brand-discovery flow downloads logo candidates from the open web with
no human in the loop, so before any bytes are trusted, scored, or stored
they must be proven to actually be a supported image — not a spoofed
content-type, an HTML error page served with `image/png`, a truncated
download, or an unsupported/hostile format. This module answers exactly
one question: "are these bytes a real, decodable, supported image, and if
so what are its dimensions/alpha?" It deliberately trusts the *bytes*
(magic numbers + a real decode), never the server's declared MIME type,
because the declared type is attacker/misconfiguration-controlled.
"""

import io
import re
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

# PIL format string -> our lowercase format tag. Only these raster formats
# are considered supported; anything else (BMP, TIFF, ICO, Adobe .ai/EPS,
# etc.) is rejected here even if it downloaded fine, because nothing
# downstream can consume it as a logo.
_SUPPORTED_RASTER = {"PNG": "png", "JPEG": "jpeg", "GIF": "gif", "WEBP": "webp"}

_MIN_DIMENSION = 16
_MAX_DIMENSION = 8000

_SVG_ROOT_RE = re.compile(rb"<svg[\s>]", re.IGNORECASE)
_SVG_OPEN_TAG_RE = re.compile(rb"<svg\b[^>]*>", re.IGNORECASE)
_SVG_DIM_RE = re.compile(
    rb'\b(width|height)\s*=\s*["\']?\s*([0-9.]+)', re.IGNORECASE
)


class AssetValidationError(RuntimeError):
    """Raised when downloaded bytes are not a real, supported image."""


@dataclass(frozen=True)
class ValidatedAsset:
    format: str          # png | jpeg | gif | webp | svg
    is_svg: bool
    width: int | None    # None only for SVGs that declare no width/height
    height: int | None
    has_alpha: bool


def _looks_like_svg(data: bytes) -> bool:
    head = data[:1024].lstrip()
    lowered = head.lower()
    if lowered.startswith(b"<svg"):
        return True
    # XML-prologued SVGs: "<?xml ...?> ... <svg ...>"
    return lowered.startswith(b"<?xml") and bool(_SVG_ROOT_RE.search(data[:4096]))


def _svg_dimensions(data: bytes) -> tuple[int | None, int | None]:
    dims: dict[str, int] = {}
    # Isolate the opening <svg ...> tag, then read literal width/height from
    # within it (viewBox-only SVGs legitimately have neither).
    open_tag_match = _SVG_OPEN_TAG_RE.search(data[:8192])
    if open_tag_match is None:
        return None, None
    for match in _SVG_DIM_RE.finditer(open_tag_match.group(0)):
        name = match.group(1).decode("ascii").lower()
        try:
            dims[name] = int(float(match.group(2)))
        except ValueError:
            continue
    return dims.get("width"), dims.get("height")


def validate_asset_bytes(data: bytes, declared_content_type: str = "") -> ValidatedAsset:
    if not data:
        raise AssetValidationError("empty asset body")

    if _looks_like_svg(data):
        if not _SVG_ROOT_RE.search(data[:8192]):
            raise AssetValidationError(
                "bytes look like SVG/XML but contain no <svg> root element"
            )
        width, height = _svg_dimensions(data)
        return ValidatedAsset(
            format="svg", is_svg=True, width=width, height=height, has_alpha=True
        )

    # Raster path: never trust declared_content_type — decode the actual
    # bytes. verify() catches truncated/corrupt files; a fresh open is then
    # needed for size/mode because verify() leaves the image unusable.
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            has_alpha = (
                image.mode in ("RGBA", "LA")
                or (image.mode == "P" and "transparency" in image.info)
            )
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AssetValidationError(
            f"bytes are not a decodable image "
            f"(declared content-type {declared_content_type!r}): {exc}"
        ) from exc

    if fmt not in _SUPPORTED_RASTER:
        raise AssetValidationError(f"unsupported image format {fmt!r}")
    if not (_MIN_DIMENSION <= width <= _MAX_DIMENSION and _MIN_DIMENSION <= height <= _MAX_DIMENSION):
        raise AssetValidationError(
            f"image dimensions {width}x{height} are outside the supported "
            f"range [{_MIN_DIMENSION}, {_MAX_DIMENSION}]"
        )

    return ValidatedAsset(
        format=_SUPPORTED_RASTER[fmt],
        is_svg=False,
        width=width,
        height=height,
        has_alpha=has_alpha,
    )
