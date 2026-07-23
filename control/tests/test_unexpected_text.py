import io

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

from imagin.compositor import compose_poster
from imagin.qa.ocr_check import OcrDetection
from imagin.qa.report import QaCheck, build_qa_report
from imagin.qa.unexpected_text import (
    AllowedRegion,
    check_no_unexpected_text,
)
from imagin.qr_gen import generate_qr_png


def _solid_png(width: int, height: int, rgb=(120, 140, 160)) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*(c / 255 for c in rgb))
    ctx.paint()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def _draw_text_at(png_bytes: bytes, text: str, x: int, y: int, font: str = "Noto Sans Thai Bold 60") -> bytes:
    surface = cairo.ImageSurface.create_from_png(io.BytesIO(png_bytes))
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0, 0, 0)
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription(font))
    layout.set_text(text, -1)
    ctx.translate(x, y)
    PangoCairo.show_layout(ctx, layout)
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def _compose_sample_poster():
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200, rgb=(255, 255, 255))
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")
    return compose_poster(
        hero_png=hero,
        headline="เปิดบ้าน UTCC",
        body_lines=["มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย"],
        cta="สมัครวันนี้",
        logo_png=logo,
        qr_png=qr,
        width=1080,
        height=1350,
    )


def _regions_of(composed) -> list[AllowedRegion]:
    regions = [
        AllowedRegion(name=b.name, x=b.x, y=b.y, width=b.width, height=b.height)
        for b in composed.text_blocks
    ]
    for extra in (composed.logo_region, composed.qr_region):
        if extra is not None:
            regions.append(
                AllowedRegion(name=extra.name, x=extra.x, y=extra.y, width=extra.width, height=extra.height)
            )
    return regions


# ---- Real-OCR tests (need PaddleOCR; run in Docker) -----------------------


def test_expected_text_inside_allowed_regions_passes_and_qr_causes_no_false_failure():
    # The composed poster contains ONLY authorized content: compositor text
    # in its blocks, the logo, and the QR (whose module pattern must not
    # produce a false unexpected-text failure — its region is allowed).
    composed = _compose_sample_poster()

    passed, detail, unexpected = check_no_unexpected_text(composed.png_bytes, _regions_of(composed))

    assert passed is True, detail
    assert unexpected == []


def test_text_rendered_outside_all_allowed_regions_fails():
    # Simulate the live defect: a big hallucinated word in the HERO region
    # — with the centered_editorial template that's the lower half of the
    # poster, far from every allowed region (panel ends ~57% down; logo is
    # at the top; the action card ends above the hero band). NOTE: the
    # coordinates must track the template layout — placing this inside or
    # adjacent to a real text region would legitimately merge with allowed
    # content and prove nothing.
    composed = _compose_sample_poster()
    hero_y = composed.layout.hero.y + 200
    contaminated = _draw_text_at(composed.png_bytes, "UTCC", 350, hero_y, font="Noto Sans Bold 120")

    passed, detail, unexpected = check_no_unexpected_text(contaminated, _regions_of(composed))

    assert passed is False
    assert any("UTCC" in u.text for u in unexpected), detail


# ---- Geometry tests (deterministic, no OCR: containment math) -------------


def _run_with_fake_detections(monkeypatch, detections, regions, **kwargs):
    import imagin.qa.unexpected_text as module

    monkeypatch.setattr(module, "detect_text_regions", lambda _png: detections)
    return module.check_no_unexpected_text(b"unused-png", regions, **kwargs)


def test_huge_word_partially_overlapping_allowed_region_still_fails(monkeypatch):
    # A 900x300 generated word that clips the corner of a 400x120 text
    # panel: the overlap is a small fraction of the detection's own area,
    # so "mostly contained" is false and it must fail.
    regions = [AllowedRegion(name="text:headline", x=100, y=800, width=400, height=120)]
    detections = [OcrDetection(text="มหาลัยปลอม", confidence=0.9, x=50, y=600, width=900, height=300)]

    passed, detail, unexpected = _run_with_fake_detections(monkeypatch, detections, regions)

    assert passed is False
    assert unexpected[0].containment < 0.7
    assert unexpected[0].nearest_region == "text:headline"


def test_text_inside_verified_logo_region_is_allowed(monkeypatch):
    # The official logo may contain its own wordmark text; a detection
    # fully inside the logo region is authorized.
    regions = [AllowedRegion(name="logo", x=64, y=64, width=120, height=120)]
    detections = [OcrDetection(text="UTCC", confidence=0.95, x=70, y=100, width=100, height=40)]

    passed, _detail, unexpected = _run_with_fake_detections(monkeypatch, detections, regions)

    assert passed is True
    assert unexpected == []


def test_detection_spanning_two_adjacent_text_blocks_is_allowed(monkeypatch):
    # OCR sometimes merges two stacked compositor blocks into one detection
    # spanning both plus the small gap; summing containment across regions
    # keeps that from false-failing.
    regions = [
        AllowedRegion(name="text:headline", x=64, y=900, width=800, height=70),
        AllowedRegion(name="text:body", x=64, y=986, width=800, height=70),
    ]
    detections = [OcrDetection(text="รวมสองบรรทัด", confidence=0.9, x=64, y=905, width=780, height=140)]

    passed, _detail, unexpected = _run_with_fake_detections(monkeypatch, detections, regions)

    assert passed is True, unexpected


def test_zero_information_noise_is_filtered_but_readable_text_is_not(monkeypatch):
    regions = [AllowedRegion(name="text:headline", x=0, y=0, width=10, height=10)]
    detections = [
        OcrDetection(text="|", confidence=0.9, x=500, y=500, width=8, height=20),      # 1-char punctuation
        OcrDetection(text="  ", confidence=0.9, x=500, y=550, width=8, height=20),     # whitespace only
        OcrDetection(text="ปลอม", confidence=0.15, x=500, y=600, width=80, height=30),  # below min confidence
        OcrDetection(text="ข้อความหลอน", confidence=0.85, x=500, y=650, width=200, height=40),  # real -> caught
    ]

    passed, _detail, unexpected = _run_with_fake_detections(monkeypatch, detections, regions)

    assert passed is False
    assert len(unexpected) == 1
    assert unexpected[0].text == "ข้อความหลอน"


def test_qa_report_fails_overall_when_no_unexpected_text_fails():
    checks = [
        QaCheck(name="ocr_exact_match", passed=True, detail="ok"),
        QaCheck(name="no_unexpected_text", passed=False, detail="hallucinated UTCC at (300,200)"),
        QaCheck(name="qr_decode_match", passed=True, detail="ok"),
        QaCheck(name="logo_provenance_match", passed=True, detail="ok"),
        QaCheck(name="no_text_overflow", passed=True, detail="ok"),
    ]

    report = build_qa_report(checks)

    assert report.overall_status == "fail"
