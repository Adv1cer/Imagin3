import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .brand.registry import resolve_brand
from .comfyui_client import ComfyUiClient, WorkflowNodeMap
from .compositor import compose_poster
from .design_spec import build_poster_design_spec
from .object_store import LocalObjectStore
from .qa.logo_check import check_logo_provenance
from .qa.ocr_check import check_text_blocks_exact_match
from .qa.qr_check import check_qr
from .qa.report import QaCheck, QaReport, build_qa_report
from .qr_gen import generate_qr_png


@dataclass(frozen=True)
class PipelineResult:
    poster_png_storage_key: str
    qa_report: QaReport


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
) -> PipelineResult:
    resolved_brand = resolve_brand(session, org_name, official_domain, http_client, object_store)

    spec = build_poster_design_spec(
        prompt=prompt,
        brand_profile_id=str(resolved_brand.brand_profile_id),
        brand_asset_id=str(resolved_brand.logo_asset_id),
        qr_target_url=qr_target_url,
    )

    hero_png = comfyui_client.generate_image(
        workflow, node_map, prompt_text=prompt, seed=seed, width=spec.width, height=spec.height
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
    # box and upscaled) and compared against only that block's own text —
    # not run over the whole poster and checked for substrings anywhere in
    # one big blob. This is still an exact match, not fuzzy/similarity
    # scoring, so a genuine typo still fails the gate.
    ocr_passed, ocr_detail = check_text_blocks_exact_match(poster_png, composed.text_blocks)

    checks = [
        QaCheck(
            name="ocr_exact_match",
            passed=ocr_passed,
            detail=ocr_detail,
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
    return PipelineResult(poster_png_storage_key=stored.storage_key, qa_report=report)
