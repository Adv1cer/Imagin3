import hashlib
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .brand.registry import resolve_brand
from .comfyui_client import ComfyUiClient, WorkflowNodeMap
from .compositor import compose_poster
from .design_spec import build_poster_design_spec
from .object_store import LocalObjectStore
from .qa.logo_check import check_logo_provenance
from .qa.ocr_check import check_text_blocks_exact_match, detect_text_regions
from .qa.qr_check import check_qr
from .qa.report import QaCheck, QaReport, build_qa_report
from .qa.unexpected_text import AllowedRegion, check_no_unexpected_text
from .qr_gen import generate_qr_png

# --- Background generation constraints -----------------------------------
# The hero is a *background*: it must arrive image-only. Both prompts state
# that explicitly, and the OCR gate below enforces it regardless of whether
# the model listened.
IMAGE_ONLY_PROMPT_SUFFIX = (
    "clean visual background, empty composition space, photographic scene only, "
    "no text, no letters, no words, no typography, no logo, no watermark, "
    "no signage, no symbols, no poster design, no captions"
)

# Deterministic retry-seed derivation: attempt 0 uses the requested seed;
# attempt N uses seed + N * stride (mod 2^31). Reproducible: the same
# requested seed always yields the same retry sequence.
BACKGROUND_RETRY_SEED_STRIDE = 104729  # a large prime, arbitrary but fixed
DEFAULT_BACKGROUND_MAX_RETRIES = 2

# Minimum OCR confidence for a background detection to count as "readable
# text". Below this, detections on pure imagery are mostly detector noise.
BACKGROUND_TEXT_MIN_CONFIDENCE = 0.30


def derive_background_seed(requested_seed: int, attempt: int) -> int:
    return (requested_seed + attempt * BACKGROUND_RETRY_SEED_STRIDE) % (2**31)


@dataclass(frozen=True)
class BackgroundAttempt:
    seed: int
    accepted: bool
    rejection_reason: str | None
    detected_texts: list[str] = field(default_factory=list)


class BackgroundTextError(RuntimeError):
    """All background-generation attempts contained readable text.

    Structured (carries every attempt with its seed and rejection reason)
    so callers can report cleanly and audit what was tried; the pipeline
    refuses to compose and export a poster over a text-contaminated
    background."""

    def __init__(self, message: str, attempts: list[BackgroundAttempt]):
        super().__init__(message)
        self.attempts = attempts


def validate_background_text_free(
    png_bytes: bytes,
    min_confidence: float = BACKGROUND_TEXT_MIN_CONFIDENCE,
) -> tuple[bool, list[str]]:
    """OCR the raw generated background. It passes only when no readable
    text is detected anywhere — the background is not allowed to contain
    text, letters, watermarks, or generated typography at all."""
    detections = detect_text_regions(png_bytes)
    readable = [
        d.text
        for d in detections
        if d.confidence >= min_confidence and "".join(d.text.split())
    ]
    return (not readable), readable


def generate_validated_background(
    comfyui_client: ComfyUiClient,
    workflow: dict,
    node_map: WorkflowNodeMap,
    prompt_text: str,
    negative_prompt_text: str,
    seed: int,
    width: int,
    height: int,
    max_retries: int = DEFAULT_BACKGROUND_MAX_RETRIES,
) -> tuple[bytes, list[BackgroundAttempt]]:
    """Generate a background and reject it if OCR finds readable text,
    retrying with deterministically derived seeds up to max_retries times.
    Bounded loop: exactly 1 + max_retries attempts, never more."""
    attempts: list[BackgroundAttempt] = []

    for attempt_index in range(max_retries + 1):
        attempt_seed = derive_background_seed(seed, attempt_index)
        hero_png = comfyui_client.generate_image(
            workflow,
            node_map,
            prompt_text=prompt_text,
            seed=attempt_seed,
            width=width,
            height=height,
            negative_prompt_text=negative_prompt_text,
        )
        clean, readable = validate_background_text_free(hero_png)
        if clean:
            attempts.append(BackgroundAttempt(seed=attempt_seed, accepted=True, rejection_reason=None))
            return hero_png, attempts
        attempts.append(
            BackgroundAttempt(
                seed=attempt_seed,
                accepted=False,
                rejection_reason=f"background contains readable text: {readable!r}",
                detected_texts=readable,
            )
        )

    raise BackgroundTextError(
        f"all {max_retries + 1} background generation attempt(s) contained readable "
        "text; refusing to compose a poster over a text-contaminated background "
        f"(seeds tried: {[a.seed for a in attempts]})",
        attempts=attempts,
    )


@dataclass(frozen=True)
class PipelineResult:
    poster_png_storage_key: str
    qa_report: QaReport
    background_attempts: list[BackgroundAttempt] = field(default_factory=list)


def _allowed_regions(composed) -> list[AllowedRegion]:
    regions = [
        AllowedRegion(name=f"text:{block.name}", x=block.x, y=block.y, width=block.width, height=block.height)
        for block in composed.text_blocks
    ]
    if composed.logo_region is not None:
        r = composed.logo_region
        regions.append(AllowedRegion(name="logo", x=r.x, y=r.y, width=r.width, height=r.height))
    if composed.qr_region is not None:
        r = composed.qr_region
        regions.append(AllowedRegion(name="qr", x=r.x, y=r.y, width=r.width, height=r.height))
    return regions


def run_poster_generation(
    session: Session,
    object_store: LocalObjectStore,
    http_client,
    comfyui_client: ComfyUiClient,
    workflow: dict,
    node_map: WorkflowNodeMap,
    prompt: str,
    org_name: str,
    official_domain: str,
    qr_target_url: str,
    seed: int = 0,
    background_max_retries: int = DEFAULT_BACKGROUND_MAX_RETRIES,
) -> PipelineResult:
    resolved_brand = resolve_brand(session, org_name, official_domain, http_client, object_store)

    spec = build_poster_design_spec(
        prompt=prompt,
        brand_profile_id=str(resolved_brand.brand_profile_id),
        brand_asset_id=str(resolved_brand.logo_asset_id),
        qr_target_url=qr_target_url,
    )

    hero_prompt = f"{prompt}, {IMAGE_ONLY_PROMPT_SUFFIX}"
    negative_prompt_text = ", ".join(spec.negative_prompt)

    hero_png, background_attempts = generate_validated_background(
        comfyui_client,
        workflow,
        node_map,
        prompt_text=hero_prompt,
        negative_prompt_text=negative_prompt_text,
        seed=seed,
        width=spec.width,
        height=spec.height,
        max_retries=background_max_retries,
    )

    logo_png = object_store.get(resolved_brand.logo_storage_key)
    qr_png = generate_qr_png(spec.qr_target_url)

    composed = compose_poster(
        hero_png=hero_png, headline=spec.copy.headline, body_lines=spec.copy.body,
        cta=spec.copy.cta, logo_png=logo_png, qr_png=qr_png, width=spec.width, height=spec.height,
    )
    poster_png = composed.png_bytes

    # The provenance gate hashes the bytes actually composited into the
    # poster (read from object storage moments ago) and compares them
    # against the registry's approved hash — not the approved hash against
    # itself, which would be a tautology that can never fail.
    composited_logo_sha256 = hashlib.sha256(logo_png).hexdigest()

    # OCR is scoped per text block (cropped to that block's own bounding
    # box with Thai-mark-safe padding, multiple deterministic variants)
    # and compared against only that block's own text with exact equality.
    ocr_passed, ocr_detail = check_text_blocks_exact_match(poster_png, composed.text_blocks)

    # Unexpected-text hard gate: nothing readable may exist outside the
    # compositor's text blocks, the verified logo box, and the QR box.
    unexpected_passed, unexpected_detail, _unexpected = check_no_unexpected_text(
        poster_png, _allowed_regions(composed)
    )

    checks = [
        QaCheck(
            name="ocr_exact_match",
            passed=ocr_passed,
            detail=ocr_detail,
        ),
        QaCheck(
            name="no_unexpected_text",
            passed=unexpected_passed,
            detail=unexpected_detail,
        ),
        QaCheck(
            name="qr_decode_match",
            passed=check_qr(poster_png, spec.qr_target_url),
            detail=f"expected {spec.qr_target_url}",
        ),
        QaCheck(
            name="logo_provenance_match",
            passed=check_logo_provenance(composited_logo_sha256, resolved_brand.logo_sha256),
            detail=f"asset {resolved_brand.logo_asset_id} version {resolved_brand.profile_version}",
        ),
        QaCheck(name="no_text_overflow", passed=True, detail="compose_poster raises TextOverflowError on failure, so reaching here means no overflow"),
    ]
    report = build_qa_report(checks)

    stored = object_store.put(poster_png, suffix=".png")
    return PipelineResult(
        poster_png_storage_key=stored.storage_key,
        qa_report=report,
        background_attempts=background_attempts,
    )
