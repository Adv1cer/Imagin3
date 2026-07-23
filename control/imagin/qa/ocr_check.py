import io
import unicodedata

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

from ..compositor import TextBlockBounds


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


def _extract_text_from_image(image: Image.Image) -> str:
    results = _get_engine().predict(np.array(image))

    texts: list[str] = []

    for result in results:
        payload = result.json

        if callable(payload):
            payload = payload()

        result_data = payload.get("res", payload)
        texts.extend(result_data.get("rec_texts", []))

    return "\n".join(texts)


def extract_text(png_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    return _extract_text_from_image(image)


# Padding added around a text block's exact logical-extent bounding box
# before cropping, so anti-aliased glyph edges, descenders, and Thai
# above/below-baseline vowel and tone marks that sit just outside the
# tight box aren't sheared off by the crop.
_CROP_PADDING_PX = 8


def extract_text_from_block(
    png_bytes: bytes,
    block: TextBlockBounds,
    upscale: float = 2.5,
) -> str:
    """Crop the poster to just this block's own bounding box (padded) and
    upscale it before OCR. Isolating one block at a time — instead of
    running OCR over the full 1080x1350 poster where a 24px-tall line of
    body text is a small fraction of the frame — and upscaling the crop
    gives PaddleOCR far more pixels per glyph to work with, which is what
    actually fixes misreads like a dropped/confused diacritic, rather than
    loosening the comparison itself.
    """
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    left = max(0, block.x - _CROP_PADDING_PX)
    top = max(0, block.y - _CROP_PADDING_PX)
    right = min(image.width, block.x + block.width + _CROP_PADDING_PX)
    bottom = min(image.height, block.y + block.height + _CROP_PADDING_PX)

    crop = image.crop((left, top, right, bottom))

    if upscale and upscale != 1.0:
        new_size = (
            max(1, round(crop.width * upscale)),
            max(1, round(crop.height * upscale)),
        )
        crop = crop.resize(new_size, Image.LANCZOS)

    return _extract_text_from_image(crop)


def _normalize(text: str) -> str:
    # Whitespace is stripped entirely, not collapsed to single spaces.
    # Thai script has no spaces between words, so when the compositor's
    # Pango layout word-wraps a long Thai sentence to fit the poster's text
    # box, the wrap point falls inside what was a single unbroken clause.
    # PaddleOCR then reports the two wrapped halves as separate text lines,
    # and extract_text() joins multi-line OCR output with "\n" — collapsing
    # that to a single space would inject whitespace into the middle of a
    # word that never had any, producing a false mismatch even though the
    # poster rendered correctly. Stripping all whitespace on both sides
    # keeps the check exact (same characters, same order) while making it
    # immune to incidental line-wrap/line-segmentation noise from either
    # the renderer or the OCR engine.
    normalized = unicodedata.normalize("NFC", text)
    return "".join(normalized.split())


def match_with_detail(
    png_bytes: bytes,
    expected_texts: list[str],
) -> tuple[bool, str]:
    """Run OCR once and report both the pass/fail result and what was
    actually read, so callers (the pipeline's QA report) can surface the
    real extracted text instead of a static, uninformative message. This
    is what makes an `ocr_exact_match` failure debuggable from a QA report
    alone, without re-running the pipeline with extra instrumentation.
    """
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


def check_text_block_exact_match(
    png_bytes: bytes,
    block: TextBlockBounds,
    upscale: float = 2.5,
) -> tuple[bool, str]:
    """Compare OCR of just this block's own cropped/upscaled region
    against only that block's own expected text.

    This is deliberately == (exact equality after whitespace
    normalization), not `in`/substring and not a fuzzy similarity score:
    once OCR is scoped to a single block, its output should correspond to
    that block and nothing else, so requiring an exact match is both
    correct and strict — a genuine typo in the composited text must still
    be reported as a failure, not silently passed.
    """
    extracted = _normalize(extract_text_from_block(png_bytes, block, upscale))
    expected = _normalize(block.text)
    passed = extracted == expected
    detail = f"block={block.name!r} expected={expected!r} extracted={extracted!r}"
    return passed, detail


def check_text_blocks_exact_match(
    png_bytes: bytes,
    blocks: list[TextBlockBounds],
    upscale: float = 2.5,
) -> tuple[bool, str]:
    results = [
        check_text_block_exact_match(png_bytes, block, upscale)
        for block in blocks
    ]
    passed = all(ok for ok, _detail in results)
    detail = "; ".join(detail for _ok, detail in results)
    return passed, detail