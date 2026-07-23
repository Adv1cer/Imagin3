import hashlib
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from .brand.registry import resolve_brand
from .comfyui_client import ComfyUiClient, WorkflowNodeMap
from .compositor import compose_poster_from_spec
from .design_spec import DesignSpec, build_poster_design_spec
from .object_store import LocalObjectStore
from .qa.layout_check import check_layout_contract
from .qa.logo_check import check_logo_provenance
from .qa.ocr_check import check_text_blocks_exact_match, detect_text_regions
from .qa.qr_check import check_qr
from .qa.report import QaCheck, QaReport, build_qa_report
from .qa.unexpected_text import AllowedRegion, check_no_unexpected_text
from .qr_gen import generate_qr_png
from .subject_detection import SubjectDetector
from .templates import IMAGE_ONLY_PROMPT_SUFFIX, build_hero_prompt  # noqa: F401 (suffix re-exported for compat)

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
    selected_template: str = ""
    design_metadata: dict = field(default_factory=dict)


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


def _rect_dict(r) -> dict:
    return {"x": r.x, "y": r.y, "width": r.width, "height": r.height}


def build_design_metadata(
    spec: DesignSpec,
    composed,
    requested_seed: int,
    background_attempts: list[BackgroundAttempt],
    resolved_brand,
) -> dict:
    """Reproducible design metadata: everything needed to debug or replay
    this exact output. Deterministic content for identical inputs."""
    template = spec.template
    layout = spec.layout
    return {
        "template": spec.template_id,
        "canvas": {"width": spec.width, "height": spec.height},
        "normalizedRegions": {
            "logo": asdict(template.logo_region),
            "panel": asdict(template.panel_region),
            "headline": asdict(template.headline_region),
            "body": asdict(template.body_region),
            "action": asdict(template.action_region),
            "hero": asdict(template.hero_region),
            "protectedSubject": asdict(template.protected_subject_region),
        },
        "pixelRegions": {
            "logo": _rect_dict(layout.logo),
            "panel": _rect_dict(layout.panel),
            "headline": _rect_dict(layout.headline),
            "body": _rect_dict(layout.body),
            "action": _rect_dict(layout.action),
            "hero": _rect_dict(layout.hero),
            "protectedSubject": _rect_dict(layout.protected_subject),
        },
        "composedRegions": {
            "textBlocks": [
                {"name": b.name, **_rect_dict(b)} for b in composed.text_blocks
            ],
            "logo": _rect_dict(composed.logo_region) if composed.logo_region else None,
            "qr": _rect_dict(composed.qr_region) if composed.qr_region else None,
            "panel": _rect_dict(composed.panel_region) if composed.panel_region else None,
            "action": _rect_dict(composed.action_region) if composed.action_region else None,
        },
        "palette": {
            "text": list(spec.palette.text_rgb),
            "accent": list(spec.palette.accent_rgb),
            "panel": list(spec.palette.panel_rgb),
            "source": spec.palette.source,
        },
        "typography": {
            "fontSizes": composed.font_sizes,
            "alignment": template.text_align,
            "spacingScale": template.spacing_scale,
        },
        "panelStyle": {"style": template.panel_style, "opacity": template.panel_opacity},
        "requestedSeed": requested_seed,
        "backgroundAttemptSeeds": [a.seed for a in background_attempts],
        "brand": {
            "profileId": str(resolved_brand.brand_profile_id),
            "profileVersion": resolved_brand.profile_version,
            "assetId": str(resolved_brand.logo_asset_id),
            "assetSha256": resolved_brand.logo_sha256,
        },
    }


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
    template_id: str | None = None,
    subject_detector: SubjectDetector | None = None,
) -> PipelineResult:
    resolved_brand = resolve_brand(session, org_name, official_domain, http_client, object_store)
    logo_png = object_store.get(resolved_brand.logo_storage_key)

    # ONE design spec, built once, consumed by BOTH the background prompt
    # builder and the compositor — the shared layout contract.
    spec = build_poster_design_spec(
        prompt=prompt,
        brand_profile_id=str(resolved_brand.brand_profile_id),
        brand_asset_id=str(resolved_brand.logo_asset_id),
        qr_target_url=qr_target_url,
        template_id=template_id,
        logo_png=logo_png,
    )

    hero_prompt = build_hero_prompt(prompt, spec.template)
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

    qr_png = generate_qr_png(spec.qr_target_url)

    composed = compose_poster_from_spec(hero_png, spec, logo_png, qr_png)
    poster_png = composed.png_bytes

    # The provenance gate hashes the bytes actually composited into the
    # poster (read from object storage moments ago) and compares them
    # against the registry's approved hash — not the approved hash against
    # itself, which would be a tautology that can never fail.
    composited_logo_sha256 = hashlib.sha256(logo_png).hexdigest()

    ocr_passed, ocr_detail = check_text_blocks_exact_match(poster_png, composed.text_blocks)

    unexpected_passed, unexpected_detail, _unexpected = check_no_unexpected_text(
        poster_png, _allowed_regions(composed)
    )

    subject_boxes = subject_detector.detect(poster_png) if subject_detector is not None else []
    layout_passed, layout_detail = check_layout_contract(
        composed, spec.template, spec.layout, spec.palette, subject_boxes
    )

    checks = [
        QaCheck(name="ocr_exact_match", passed=ocr_passed, detail=ocr_detail),
        QaCheck(name="no_unexpected_text", passed=unexpected_passed, detail=unexpected_detail),
        QaCheck(name="layout_contract_match", passed=layout_passed, detail=layout_detail),
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
        QaCheck(name="no_text_overflow", passed=True, detail="compose raises TextOverflowError on failure, so reaching here means no overflow"),
    ]
    report = build_qa_report(checks)

    design_metadata = build_design_metadata(spec, composed, seed, background_attempts, resolved_brand)

    stored = object_store.put(poster_png, suffix=".png")
    return PipelineResult(
        poster_png_storage_key=stored.storage_key,
        qa_report=report,
        background_attempts=background_attempts,
        selected_template=spec.template_id,
        design_metadata=design_metadata,
    )
