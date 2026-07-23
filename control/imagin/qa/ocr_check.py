import io
import unicodedata
from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from paddleocr import PaddleOCR

from ..compositor import TextBlockBounds


# One engine per process. PaddleOCR construction downloads/loads models and
# is by far the most expensive step, so it must never happen per block or
# per variant — every extraction below goes through this singleton.
_engine: PaddleOCR | None = None


def _get_engine() -> PaddleOCR:
    global _engine

    if _engine is None:
        _engine = PaddleOCR(
            lang="th",
            ocr_version="PP-OCRv5",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    return _engine


def _predict_payloads(image: Image.Image) -> list[dict]:
    results = _get_engine().predict(np.array(image.convert("RGB")))
    payloads: list[dict] = []
    for result in results:
        payload = result.json
        if callable(payload):
            payload = payload()
        payloads.append(payload.get("res", payload))
    return payloads


def _extract_text_from_image(image: Image.Image) -> str:
    texts: list[str] = []
    for payload in _predict_payloads(image):
        texts.extend(payload.get("rec_texts", []))
    return "\n".join(texts)


def extract_text(png_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    return _extract_text_from_image(image)


@dataclass(frozen=True)
class OcrDetection:
    """One detected text region in full-image OCR, with its pixel box."""

    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


def _poly_to_bbox(points) -> tuple[int, int, int, int]:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys))


def detect_text_regions(png_bytes: bytes) -> list[OcrDetection]:
    """OCR the full image and return every detected text region with its
    bounding box and confidence. Used by the unexpected-text gate and by
    background validation — both need *where* text is, not just what it
    says."""
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    return _detect_in_image(image)


def _detect_in_image(image: Image.Image) -> list[OcrDetection]:
    detections: list[OcrDetection] = []

    for payload in _predict_payloads(image):
        texts = payload.get("rec_texts", []) or []
        scores = payload.get("rec_scores", []) or []
        boxes = payload.get("rec_boxes", None)
        polys = payload.get("dt_polys", None)

        for index, text in enumerate(texts):
            confidence = float(scores[index]) if index < len(scores) else 1.0
            bbox: tuple[int, int, int, int] | None = None

            if boxes is not None and index < len(boxes):
                raw = np.asarray(boxes[index]).flatten().tolist()
                if len(raw) >= 4:
                    x1, y1, x2, y2 = raw[0], raw[1], raw[2], raw[3]
                    bbox = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            if bbox is None and polys is not None and index < len(polys):
                bbox = _poly_to_bbox(np.asarray(polys[index]).tolist())
            if bbox is None:
                # No geometry available for this detection — treat as
                # covering nothing rather than silently dropping the text.
                bbox = (0, 0, 0, 0)

            detections.append(
                OcrDetection(
                    text=text,
                    confidence=confidence,
                    x=bbox[0],
                    y=bbox[1],
                    width=bbox[2],
                    height=bbox[3],
                )
            )

    return detections


# Crop padding. Horizontal padding covers anti-aliased glyph edges;
# vertical padding is deliberately larger because Thai stacks vowels and
# tone marks above (and vowels below) the base consonant line — a crop cut
# from Pango's logical extents can shave those marks off, which reads as a
# different word (เปิด -> เปด is exactly a lost upper vowel).
_CROP_PAD_X = 12
_CROP_PAD_Y = 24


def _crop_block(image: Image.Image, block: TextBlockBounds) -> Image.Image:
    left = max(0, block.x - _CROP_PAD_X)
    top = max(0, block.y - _CROP_PAD_Y)
    right = min(image.width, block.x + block.width + _CROP_PAD_X)
    bottom = min(image.height, block.y + block.height + _CROP_PAD_Y)
    return image.crop((left, top, right, bottom))


def _upscale(image: Image.Image, factor: float) -> Image.Image:
    # Aspect ratio preserved by construction (both axes scaled equally);
    # LANCZOS for quality — OCR accuracy is the whole point of the resize.
    return image.resize(
        (max(1, round(image.width * factor)), max(1, round(image.height * factor))),
        Image.LANCZOS,
    )


# Per-detection confidence floor used ONLY inside a controlled text-block
# crop. Real text lines score high (typically > 0.85); the spurious
# fragments the first Docker run produced at crop borders ('2', '1', 'นZ')
# are separate low-confidence detections. Dropping them is noise removal,
# not tolerance: a real typo is a *high-confidence* read of the wrong
# characters and still fails the exact comparison.
BLOCK_DETECTION_MIN_CONFIDENCE = 0.5


def _extract_block_text_ordered(image: Image.Image) -> str:
    """Extract text from a block crop as top-to-bottom, left-to-right
    ordered lines. The detector does NOT guarantee reading order — the
    first Docker run read a two-line block's lines in reverse, failing an
    exact match whose every character was correct. Sorting by geometry
    makes the comparison depend only on what the block says, not on
    detector-internal ordering."""
    detections = [
        d for d in _detect_in_image(image)
        if d.confidence >= BLOCK_DETECTION_MIN_CONFIDENCE
    ]
    detections.sort(key=lambda d: (d.y + d.height / 2, d.x))
    return "\n".join(d.text for d in detections)


def _otsu_binarize(gray: Image.Image) -> Image.Image:
    array = np.asarray(gray, dtype=np.uint8)
    hist = np.bincount(array.ravel(), minlength=256).astype(np.float64)
    total = array.size
    sum_total = np.dot(np.arange(256), hist)
    sum_b = 0.0
    weight_b = 0.0
    max_variance = -1.0
    threshold = 127
    for t in range(256):
        weight_b += hist[t]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += t * hist[t]
        mean_b = sum_b / weight_b
        mean_f = (sum_total - sum_b) / weight_f
        variance = weight_b * weight_f * (mean_b - mean_f) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = t
    return gray.point(lambda p: 255 if p > threshold else 0)


def _pad_white(image: Image.Image, pad: int) -> Image.Image:
    return ImageOps.expand(image.convert("RGB"), border=pad, fill=(255, 255, 255))


def _dilate_dark_strokes(gray: Image.Image) -> Image.Image:
    # MinFilter thickens dark-on-light strokes slightly. Thai upper vowels
    # and tone marks are the thinnest marks on the poster; a 1px-radius
    # dilation makes them harder for the recognizer to drop without
    # changing what the text says.
    return gray.filter(ImageFilter.MinFilter(3))


def _ocr_variants(crop: Image.Image) -> list[tuple[str, Callable[[], Image.Image]]]:
    """Deterministic preprocessing variants tried in order. Each gives the
    same OCR engine a genuinely different view of the *same pixels*.

    Chosen from the first Docker run's evidence: plain grayscale and
    autocontrast produced byte-identical reads to raw (the recognizer
    normalizes detected lines to a fixed height, so same-geometry variants
    collapse to the same input) — they were replaced with variants that
    change detection geometry (white padding) or stroke weight (dilation),
    which do reach the recognizer differently. None alter what the text
    says, so an exact match on any variant is still an exact match against
    what was really rendered."""
    gray = crop.convert("L")
    return [
        ("raw_3x", lambda: _upscale(crop, 3.0)),
        ("raw_4x", lambda: _upscale(crop, 4.0)),
        ("pad32_2x", lambda: _upscale(_pad_white(crop, 32), 2.0)),
        ("dilate_3x", lambda: _upscale(_dilate_dark_strokes(gray), 3.0)),
        ("otsu_3x", lambda: _upscale(_otsu_binarize(gray), 3.0)),
    ]


def extract_text_from_block(
    png_bytes: bytes,
    block: TextBlockBounds,
    upscale: float = 3.0,
) -> str:
    """Single-variant crop extraction (kept for compatibility/debugging).
    The QA gate itself uses check_text_block_exact_match's multi-variant
    path."""
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    return _extract_text_from_image(_upscale(_crop_block(image, block), upscale))


def _normalize(text: str) -> str:
    # Only harmless differences are normalized: Unicode NFC, and whitespace
    # removed entirely. Thai has no inter-word spaces, so line wrapping and
    # OCR line segmentation introduce whitespace that was never part of the
    # text; stripping it keeps the comparison exact (same characters, same
    # order) without inventing tolerance for real character differences.
    normalized = unicodedata.normalize("NFC", text)
    return "".join(normalized.split())


@dataclass(frozen=True)
class BlockOcrResult:
    passed: bool
    matched_variant: str | None
    attempts: list[tuple[str, str]]  # (variant_name, normalized_extraction)


def _match_block(png_bytes: bytes, block: TextBlockBounds) -> BlockOcrResult:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    crop = _crop_block(image, block)
    expected = _normalize(block.text)

    attempts: list[tuple[str, str]] = []
    for name, build in _ocr_variants(crop):
        extracted = _normalize(_extract_block_text_ordered(build()))
        attempts.append((name, extracted))
        if extracted == expected:
            # Exact equality after normalization — never Levenshtein,
            # fuzzy scores, substring containment, or typo correction.
            return BlockOcrResult(passed=True, matched_variant=name, attempts=attempts)

    return BlockOcrResult(passed=False, matched_variant=None, attempts=attempts)


def check_text_block_exact_match(
    png_bytes: bytes,
    block: TextBlockBounds,
    upscale: float | None = None,  # retained for signature compatibility
) -> tuple[bool, str]:
    """Multi-pass exact match for one block: the block passes when at least
    one deterministic OCR variant of its padded crop reads *exactly* the
    expected text after normalization. A rendering that truly says
    something else fails every variant, because no variant changes what the
    pixels spell."""
    result = _match_block(png_bytes, block)
    expected = _normalize(block.text)

    if result.passed:
        detail = (
            f"block={block.name!r} matched exactly via variant="
            f"{result.matched_variant!r} after {len(result.attempts)} attempt(s)"
        )
    else:
        tried = "; ".join(f"{name}->{text!r}" for name, text in result.attempts)
        detail = f"block={block.name!r} expected={expected!r} no variant matched [{tried}]"
    return result.passed, detail


def check_text_blocks_exact_match(
    png_bytes: bytes,
    blocks: list[TextBlockBounds],
    upscale: float | None = None,  # retained for signature compatibility
) -> tuple[bool, str]:
    results = [check_text_block_exact_match(png_bytes, block) for block in blocks]
    passed = all(ok for ok, _detail in results)
    detail = "; ".join(detail for _ok, detail in results)
    return passed, detail


def match_with_detail(
    png_bytes: bytes,
    expected_texts: list[str],
) -> tuple[bool, str]:
    """Whole-image substring check (legacy; block-based checks are the QA
    gate). Kept because existing tests and debugging tools use it."""
    extracted = _normalize(extract_text(png_bytes))
    missing = [
        expected
        for expected in expected_texts
        if _normalize(expected) not in extracted
    ]

    passed = not missing
    detail = (
        f"extracted_text={extracted!r}; missing_expected_lines={missing!r}"
        if missing
        else f"extracted_text={extracted!r}; all expected lines matched"
    )
    return passed, detail


def check_exact_text_match(
    png_bytes: bytes,
    expected_texts: list[str],
) -> bool:
    passed, _detail = match_with_detail(png_bytes, expected_texts)
    return passed
