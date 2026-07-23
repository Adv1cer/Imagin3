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
