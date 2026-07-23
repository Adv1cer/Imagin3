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
    layout = composed.layout
    assert region is not None and layout is not None
    # Transparent margins trimmed -> effective source is 200x100 (2:1); the
    # fitted region must preserve that aspect ratio (never stretched to
    # fill its box) and stay inside the template's assigned logo region.
    assert abs(region.width / region.height - 2.0) < 0.06
    assert region.x >= layout.logo.x and region.y >= layout.logo.y
    assert region.x + region.width <= layout.logo.x + layout.logo.width + 1
    assert region.y + region.height <= layout.logo.y + layout.logo.height + 1


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


def _contains(outer, inner, tol=4):
    return (
        inner.x >= outer.x - tol
        and inner.y >= outer.y - tol
        and inner.x + inner.width <= outer.x + outer.width + tol
        and inner.y + inner.height <= outer.y + outer.height + tol
    )


def test_compositor_places_blocks_in_assigned_regions_for_all_templates():
    # The compositor and the prompt builder consume the SAME spec; this
    # verifies the compositor half of that contract for every template.
    from imagin.compositor import compose_poster_from_spec
    from imagin.design_spec import build_poster_design_spec
    from imagin.qr_gen import generate_qr_png

    for template_id in ("centered_editorial", "hero_split_left", "hero_split_right"):
        spec = build_poster_design_spec(
            prompt="โปสเตอร์กิจกรรมสถาบันการศึกษา",
            brand_profile_id="p", brand_asset_id="a",
            qr_target_url="https://example.ac.th/verified",
            template_id=template_id,
        )
        hero = _solid_png(1080, 1350)
        logo = _solid_png(200, 200, rgb=(255, 255, 255))
        qr = generate_qr_png(spec.qr_target_url)

        composed = compose_poster_from_spec(hero, spec, logo, qr)
        layout = composed.layout
        blocks = {b.name: b for b in composed.text_blocks}

        assert _contains(layout.headline, blocks["headline"]), template_id
        assert _contains(layout.body, blocks["body"]), template_id
        assert _contains(layout.action, blocks["cta"]), template_id
        assert _contains(layout.action, composed.qr_region, tol=0), template_id
        assert _contains(layout.logo, composed.logo_region), template_id
        # Content never enters the protected subject region.
        protected = layout.protected_subject
        for b in composed.text_blocks:
            assert (
                b.y + b.height <= protected.y
                or b.y >= protected.y + protected.height
                or b.x + b.width <= protected.x
                or b.x >= protected.x + protected.width
            ), (template_id, b.name)


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
