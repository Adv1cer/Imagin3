import io
import json
from dataclasses import replace
from types import SimpleNamespace

import cairo

from imagin.compositor import compose_poster_from_spec
from imagin.design_spec import build_poster_design_spec
from imagin.palette import BrandPalette
from imagin.pipeline import BackgroundAttempt, build_design_metadata
from imagin.qa.layout_check import check_layout_contract
from imagin.qa.report import QaCheck, build_qa_report
from imagin.qr_gen import generate_qr_png
from imagin.subject_detection import NullSubjectDetector, SubjectBox


def _solid_png(width: int, height: int, rgb=(0.45, 0.5, 0.62)) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*rgb)
    ctx.paint()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def _spec(template_id=None):
    return build_poster_design_spec(
        prompt="ทำโปสเตอร์เปิดบ้านมหาวิทยาลัยสำหรับนักเรียนมัธยมปลาย",
        brand_profile_id="11111111-1111-1111-1111-111111111111",
        brand_asset_id="22222222-2222-2222-2222-222222222222",
        qr_target_url="https://example.ac.th/verified",
        template_id=template_id,
    )


def _compose(template_id=None):
    spec = _spec(template_id)
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200, rgb=(0.9, 0.9, 0.95))
    qr = generate_qr_png(spec.qr_target_url)
    return spec, compose_poster_from_spec(hero, spec, logo, qr)


def test_valid_composition_passes_layout_contract_for_every_template():
    for template_id in ("centered_editorial", "hero_split_left", "hero_split_right"):
        spec, composed = _compose(template_id)

        passed, detail = check_layout_contract(
            composed, spec.template, spec.layout, spec.palette, NullSubjectDetector().detect(b"")
        )

        assert passed is True, f"{template_id}: {detail}"


def test_text_block_escaping_its_region_fails_layout_contract():
    spec, composed = _compose()
    # Fabricate objectively invalid geometry: shove the headline block far
    # outside its assigned region.
    bad_blocks = [
        replace(b, x=b.x + 600, y=b.y + 700) if b.name == "headline" else b
        for b in composed.text_blocks
    ]
    bad_composed = replace(composed, text_blocks=bad_blocks)

    passed, detail = check_layout_contract(bad_composed, spec.template, spec.layout, spec.palette)

    assert passed is False
    assert "headline" in detail


def test_qr_outside_action_card_fails_layout_contract():
    spec, composed = _compose()
    bad_qr = replace(composed.qr_region, x=spec.layout.action.x + spec.layout.action.width + 40)
    bad_composed = replace(composed, qr_region=bad_qr)

    passed, detail = check_layout_contract(bad_composed, spec.template, spec.layout, spec.palette)

    assert passed is False
    assert "qr" in detail


def test_qr_is_fully_contained_with_quiet_zone_in_real_composition():
    spec, composed = _compose()
    qr, action = composed.qr_region, composed.action_region

    assert qr.x >= action.x + 8
    assert qr.y >= action.y + 8
    assert qr.x + qr.width <= action.x + action.width - 8
    assert qr.y + qr.height <= action.y + action.height - 8


def test_fake_detected_face_overlapping_text_fails_subject_overlap_qa():
    spec, composed = _compose()
    headline = next(b for b in composed.text_blocks if b.name == "headline")
    fake_face = SubjectBox(x=headline.x + 10, y=headline.y + 5, width=80, height=80, kind="face")

    passed, detail = check_layout_contract(
        composed, spec.template, spec.layout, spec.palette, subject_boxes=[fake_face]
    )

    assert passed is False
    assert "detected subject" in detail


def test_low_contrast_palette_fails_layout_contract():
    spec, composed = _compose()
    washed_out = BrandPalette(
        text_rgb=(0.92, 0.93, 0.94), accent_rgb=(0.9, 0.9, 0.9),
        panel_rgb=(1.0, 1.0, 1.0), source="test",
    )

    passed, detail = check_layout_contract(composed, spec.template, spec.layout, washed_out)

    assert passed is False
    assert "contrast" in detail


def test_layout_contract_match_is_a_hard_gate_in_the_report():
    checks = [
        QaCheck(name="ocr_exact_match", passed=True, detail="ok"),
        QaCheck(name="layout_contract_match", passed=False, detail="qr escaped its card"),
    ]

    assert build_qa_report(checks).overall_status == "fail"


def test_design_metadata_is_serialized_reproducibly():
    spec, composed = _compose()
    brand = SimpleNamespace(
        brand_profile_id="11111111-1111-1111-1111-111111111111",
        profile_version=3,
        logo_asset_id="22222222-2222-2222-2222-222222222222",
        logo_sha256="cafe" * 16,
    )
    attempts = [BackgroundAttempt(seed=42, accepted=True, rejection_reason=None)]

    first = build_design_metadata(spec, composed, 42, attempts, brand)
    second = build_design_metadata(spec, composed, 42, attempts, brand)

    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
        second, sort_keys=True, ensure_ascii=False
    )
    # And it carries the reproducibility essentials.
    assert first["template"] == spec.template_id
    assert first["requestedSeed"] == 42
    assert first["backgroundAttemptSeeds"] == [42]
    assert first["palette"]["source"] == spec.palette.source
    assert first["pixelRegions"]["protectedSubject"]["y"] > 0
