import io
import cairo
import pytest
from PIL import Image

from imagin.compositor import compose_poster, TextOverflowError


def _solid_png(width: int, height: int, rgb=(120, 140, 160)) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*(c / 255 for c in rgb))
    ctx.paint()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def test_compose_poster_produces_png_of_requested_size():
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200, rgb=(255, 255, 255))
    from imagin.qr_gen import generate_qr_png
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    composed = compose_poster(
        hero_png=hero, headline="เปิดบ้าน UTCC",
        body_lines=["มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย"],
        cta="สมัครวันนี้", logo_png=logo, qr_png=qr, width=1080, height=1350,
    )

    image = Image.open(io.BytesIO(composed.png_bytes))
    assert image.size == (1080, 1350)
    assert image.format == "PNG"


def test_compose_poster_returns_bounding_boxes_for_each_text_block():
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200, rgb=(255, 255, 255))
    from imagin.qr_gen import generate_qr_png
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    headline = "เปิดบ้าน UTCC"
    body_lines = ["มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย"]
    cta = "สมัครวันนี้"

    composed = compose_poster(
        hero_png=hero, headline=headline, body_lines=body_lines,
        cta=cta, logo_png=logo, qr_png=qr, width=1080, height=1350,
    )

    assert [block.name for block in composed.text_blocks] == ["headline", "body", "cta"]

    by_name = {block.name: block for block in composed.text_blocks}
    assert by_name["headline"].text == headline
    assert by_name["body"].text == "\n".join(body_lines)
    assert by_name["cta"].text == cta

    # Every block's box must be a real, positive-area region fully inside
    # the poster canvas -- this is the region QA will later crop and OCR.
    for block in composed.text_blocks:
        assert block.width > 0
        assert block.height > 0
        assert 0 <= block.x
        assert block.x + block.width <= 1080
        assert 0 <= block.y
        assert block.y + block.height <= 1350


def _transparent_padded_logo(inner_w: int, inner_h: int, pad: int) -> bytes:
    """A logo: an opaque inner_w x inner_h mark centered inside a fully
    transparent canvas with `pad` px of transparent margin on every side."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, inner_w + 2 * pad, inner_h + 2 * pad)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0.8, 0.1, 0.1)
    ctx.rectangle(pad, pad, inner_w, inner_h)
    ctx.fill()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def test_logo_is_fitted_without_distortion_and_transparent_margins_trimmed():
    from imagin.compositor import LOGO_SIZE

    hero = _solid_png(1080, 1350)
    # 2:1 mark (200x100) with 50px transparent margins all around.
    logo = _transparent_padded_logo(200, 100, 50)
    from imagin.qr_gen import generate_qr_png
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    composed = compose_poster(
        hero_png=hero, headline="เปิดบ้าน UTCC",
        body_lines=["มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย"],
        cta="สมัครวันนี้", logo_png=logo, qr_png=qr, width=1080, height=1350,
    )

    region = composed.logo_region
    assert region is not None
    # Transparent margins trimmed -> effective source is 200x100 (2:1), so a
    # fit into the LOGO_SIZE square must give 120x60 — same aspect ratio,
    # never stretched to fill the square.
    assert region.width == LOGO_SIZE
    assert region.height == LOGO_SIZE // 2
    # Fitted region stays inside the logo box.
    assert region.width <= LOGO_SIZE and region.height <= LOGO_SIZE


def test_compose_poster_exposes_qr_region():
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200, rgb=(255, 255, 255))
    from imagin.qr_gen import generate_qr_png
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    composed = compose_poster(
        hero_png=hero, headline="เปิดบ้าน UTCC",
        body_lines=["มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย"],
        cta="สมัครวันนี้", logo_png=logo, qr_png=qr, width=1080, height=1350,
    )

    region = composed.qr_region
    assert region is not None
    assert region.width > 0 and region.height > 0
    assert region.x + region.width <= 1080
    assert region.y + region.height <= 1350


def test_compose_poster_raises_on_headline_overflow():
    hero = _solid_png(1080, 1350)
    logo = _solid_png(200, 200)
    from imagin.qr_gen import generate_qr_png
    qr = generate_qr_png("https://www.utcc.ac.th/openhouse")

    absurdly_long_headline = "เปิดบ้าน UTCC " * 200

    with pytest.raises(TextOverflowError):
        compose_poster(
            hero_png=hero, headline=absurdly_long_headline, body_lines=["x"],
            cta="สมัครวันนี้", logo_png=logo, qr_png=qr, width=1080, height=1350,
        )
