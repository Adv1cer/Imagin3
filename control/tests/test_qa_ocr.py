import cairo
import io
import gi
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo

from dataclasses import replace

from imagin.compositor import compose_poster
from imagin.qa.ocr_check import check_exact_text_match, check_text_blocks_exact_match
from imagin.qr_gen import generate_qr_png


def _solid_png(width: int, height: int, rgb=(120, 140, 160)) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*(c / 255 for c in rgb))
    ctx.paint()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def _render_text_image(text: str) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 200)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.set_source_rgb(0, 0, 0)
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription("Noto Sans Thai 40"))
    layout.set_text(text, -1)
    ctx.translate(20, 60)
    PangoCairo.show_layout(ctx, layout)
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def test_check_exact_text_match_true_for_rendered_expected_text():
    image_bytes = _render_text_image("เปิดบ้าน UTCC")

    assert check_exact_text_match(image_bytes, ["เปิดบ้าน UTCC"]) is True


def test_check_exact_text_match_false_when_text_differs():
    image_bytes = _render_text_image("เปิดบ้าน UTCC")

    assert check_exact_text_match(image_bytes, ["ข้อความที่ไม่ตรงกันเลย"]) is False


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


def test_check_text_blocks_exact_match_passes_for_real_composed_poster():
    # This is the actual end-to-end proof for the per-block cropped/upscaled
    # OCR approach: run it against a real compose_poster() output (not a
    # hand-crafted single-line image) and expect every block to match
    # exactly. If this ever regresses, whole-poster OCR concatenation is
    # not the reason -- something in the compositor or crop/upscale path is.
    composed = _compose_sample_poster()

    passed, detail = check_text_blocks_exact_match(composed.png_bytes, composed.text_blocks)

    assert passed is True, detail


def test_check_text_blocks_exact_match_catches_a_real_typo_not_fuzzy_passed():
    # Per Chet's directive: per-block comparison must stay an exact match,
    # not a fuzzy/similarity score, specifically so a genuine typo can't
    # slip through. Simulate a real mismatch -- the block's recorded
    # expected text no longer matches what was actually rendered -- and
    # confirm it is reported as a failure, not silently passed.
    composed = _compose_sample_poster()

    tampered_blocks = [
        replace(block, text="เปิดบ้าน ABCD") if block.name == "headline" else block
        for block in composed.text_blocks
    ]

    passed, detail = check_text_blocks_exact_match(composed.png_bytes, tampered_blocks)

    assert passed is False
    assert "headline" in detail
