"""Hard QA gate: no readable text outside the controlled regions.

The compositor is the only component allowed to put text on a poster, and
it does so only inside known regions (text blocks, the verified logo box,
the QR box). Anything else that OCR can read on the final artifact —
a hallucinated headline the image model drew, corrupted Thai glyphs, an
unauthorized "logo" — is unauthorized content that the previous QA never
looked for. This gate scans the *whole* poster and fails when a detection
falls outside every allowed region.

Containment, not overlap: a detection is allowed only when MOST of its box
(>= containment_threshold of its area) lies inside allowed regions. A huge
generated word that merely clips the corner of a legitimate text panel is
still mostly outside it, so it still fails.
"""

import unicodedata
from dataclasses import dataclass

from .ocr_check import OcrDetection, detect_text_regions

DEFAULT_REGION_TOLERANCE_PX = 16
DEFAULT_CONTAINMENT_THRESHOLD = 0.7
DEFAULT_MIN_CONFIDENCE = 0.30


@dataclass(frozen=True)
class AllowedRegion:
    name: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class UnexpectedDetection:
    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    containment: float
    nearest_region: str | None


def _is_noise(text: str, confidence: float, min_confidence: float) -> bool:
    """Filter only zero-information detections. Readable Thai/Latin text is
    never filtered — a hallucinated word is exactly what this gate exists
    to catch."""
    normalized = "".join(unicodedata.normalize("NFC", text).split())
    if not normalized:
        return True
    if confidence < min_confidence:
        return True
    # A single character that is not a letter or digit (stray punctuation
    # blob, QR-ish speckle read as "|" etc.) carries no information.
    if len(normalized) == 1 and not normalized.isalnum():
        return True
    return False


def _intersection_area(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
) -> float:
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _containment_fraction(
    detection: OcrDetection,
    regions: list[AllowedRegion],
    tolerance: int,
) -> tuple[float, str | None]:
    """Fraction of the detection's own area covered by allowed regions
    (each expanded by `tolerance` for OCR box variance), plus the region
    contributing the most coverage. Summed across regions so one OCR
    detection legitimately spanning two adjacent text blocks isn't
    penalized; the sum is capped at 1.0."""
    area = float(detection.width * detection.height)
    if area <= 0:
        return 0.0, None

    total = 0.0
    best_region: str | None = None
    best_overlap = 0.0
    for region in regions:
        overlap = _intersection_area(
            detection.x, detection.y, detection.width, detection.height,
            region.x - tolerance, region.y - tolerance,
            region.width + 2 * tolerance, region.height + 2 * tolerance,
        )
        total += overlap
        if overlap > best_overlap:
            best_overlap = overlap
            best_region = region.name

    return min(1.0, total / area), best_region


def check_no_unexpected_text(
    png_bytes: bytes,
    allowed_regions: list[AllowedRegion],
    tolerance: int = DEFAULT_REGION_TOLERANCE_PX,
    containment_threshold: float = DEFAULT_CONTAINMENT_THRESHOLD,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> tuple[bool, str, list[UnexpectedDetection]]:
    detections = detect_text_regions(png_bytes)

    unexpected: list[UnexpectedDetection] = []
    for detection in detections:
        if _is_noise(detection.text, detection.confidence, min_confidence):
            continue
        containment, nearest = _containment_fraction(detection, allowed_regions, tolerance)
        if containment < containment_threshold:
            unexpected.append(
                UnexpectedDetection(
                    text=detection.text,
                    confidence=detection.confidence,
                    x=detection.x,
                    y=detection.y,
                    width=detection.width,
                    height=detection.height,
                    containment=containment,
                    nearest_region=nearest,
                )
            )

    passed = not unexpected
    if passed:
        detail = (
            f"no readable text outside {len(allowed_regions)} allowed region(s) "
            f"({len(detections)} detection(s) scanned)"
        )
    else:
        items = "; ".join(
            f"text={u.text!r} conf={u.confidence:.2f} "
            f"box=({u.x},{u.y},{u.width}x{u.height}) "
            f"containment={u.containment:.2f} nearest={u.nearest_region!r}"
            for u in unexpected
        )
        detail = f"{len(unexpected)} unexpected text detection(s) outside allowed regions: {items}"
    return passed, detail, unexpected
