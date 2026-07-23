import cairo
import io
import gi
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo

from dataclasses import replace

from imagin.compositor import TextBlockBounds, compose_poster
from imagin.qa.ocr_check import (
    _get_engine,
    check_exact_text_match,
    check_text_block_exact_match,
    check_text_blocks_exact_match,
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


def test_text_is_readable_over_dark_hero_thanks_to_scrim():
    # Regression for the first live UTCC run: black text drawn straight onto
    # a dark/busy AI hero produced OCR garbage (hero texture bled into the
    # body crop, a headline vowel dropped). Compose over a near-black hero —
    # the worst case for black text — and require every block to still OCR
    # exactly. This can only pass if the contrast scrim is actually painted
    # behind the text; without it, black-on-black is unreadable.
    dark_hero = _solid_png(1080, 1350, rgb=(8, 10, 14))
    logo = _solid_png(200, 200, rgb=(255, 255, 255))
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    composed = compose_poster(
        hero_png=dark_hero,
        headline="เปิดบ้าน UTCC",
        body_lines=[
            "มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย",
            "ร่วมค้นหาเส้นทางสู่มหาวิทยาลัยในฝันของคุณ",
        ],
        cta="สมัครวันนี้",
        logo_png=logo,
        qr_png=qr,
        width=1080,
        height=1350,
    )

    passed, detail = check_text_blocks_exact_match(composed.png_bytes, composed.text_blocks)

    assert passed is True, detail


def _render_block_image(
    text: str,
    width: int = 900,
    height: int = 220,
    y: int = 60,
    font: str = "Noto Sans Thai Bold 48",
) -> tuple[bytes, TextBlockBounds]:
    """Render `text` on a clean surface and return (png, block-with-bounds)
    where the bounds are the true logical extents — mirroring exactly what
    the compositor records. Defaults to the compositor's own headline font:
    QA only ever OCRs compositor-rendered text, so probes must use the
    same rendering surface the real pipeline produces."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.set_source_rgb(0, 0, 0)
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription(font))
    layout.set_text(text, -1)
    _ink, logical = layout.get_pixel_extents()
    ctx.translate(20, y)
    PangoCairo.show_layout(ctx, layout)
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    block = TextBlockBounds(
        name="probe", text=text,
        x=20 + logical.x, y=y + logical.y,
        width=logical.width, height=logical.height,
    )
    return buffer.getvalue(), block


def test_multipass_ocr_correctly_rendered_perd_rap_samak_passes():
    # The exact word from the live false negative: เปิดรับสมัคร rendered
    # correctly (compositor headline font) must pass multi-pass exact OCR
    # (at least one deterministic variant reads it exactly).
    png, block = _render_block_image("เปิดรับสมัคร")

    passed, detail = check_text_block_exact_match(png, block)

    assert passed is True, detail


def test_multipass_ocr_actually_rendered_typo_fails():
    # A poster that REALLY renders the typo เปดรับสมัคร (missing the ิ
    # vowel) must fail against the expected เปิดรับสมัคร — no variant can
    # make wrong pixels read as the right word, and nothing may fuzzy-pass it.
    png, block = _render_block_image("เปดรับสมัคร")
    tampered = replace(block, text="เปิดรับสมัคร")

    passed, detail = check_text_block_exact_match(png, tampered)

    assert passed is False
    assert "no variant matched" in detail


def test_upper_vowel_and_tone_mark_survive_tight_crop_padding():
    # This phrase carries stacked upper vowels and tone marks (่ ้ ู ั)
    # that Pango's logical extents sit tightly around; render it near the
    # top of the canvas so the crop's upper padding is what protects the
    # marks. If padding were insufficient, the marks would be shaved off
    # and the words would change.
    png, block = _render_block_image("ร่วมค้นหาเส้นทางสู่ฝันของคุณ", y=30)

    passed, detail = check_text_block_exact_match(png, block)

    assert passed is True, detail


def test_ocr_engine_is_reused_not_rebuilt_per_crop(monkeypatch):
    # Engine construction (model load/download) must happen once per
    # process. Force the singleton to exist, then make any further
    # construction explode — a block check afterwards must not construct.
    _get_engine()  # ensure the singleton exists

    import imagin.qa.ocr_check as ocr_module

    class Bomb:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PaddleOCR was constructed again — engine not reused")

    monkeypatch.setattr(ocr_module, "PaddleOCR", Bomb)

    png, block = _render_block_image("เปิดรับสมัคร")
    # Runs all 5 variants; if any of them constructed a new PaddleOCR the
    # Bomb would raise AssertionError out of this call. The match outcome
    # itself is deliberately not asserted here — recognition accuracy is
    # covered by its own tests; this one only proves engine reuse.
    check_text_block_exact_match(png, block)

    assert ocr_module._get_engine() is ocr_module._get_engine()


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
