"""Task 0: native-dependency smoke test.

Every later task in this plan depends on native/system libraries that are
notoriously fragile to install (PyGObject needs gobject-introspection dev
headers + typelibs, pycairo needs cairo dev headers, pyzbar needs a real
libzbar.so at runtime, paddleocr/paddlepaddle are large C++-backed wheels,
psycopg2 needs libpq). If any of these are missing or mis-built inside the
`control` image, every downstream TDD task (compositor, QR, OCR QA, DB
migrations) fails with a confusing, unrelated-looking error deep inside its
own test. This module exists purely to fail fast, in one place, with a clear
message, before any of that work starts.

Run inside the real container (this is what actually exercises the Dockerfile's
apt-get list):
    docker compose build control
    docker compose run --rm control pytest tests/test_native_dependencies.py -v
"""
import io


def test_pycairo_can_create_and_paint_argb32_surface():
    import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 0, 0)
    ctx.paint()

    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    assert len(buffer.getvalue()) > 0

    stride = surface.get_stride()
    data = surface.get_data()
    # BGRA-ish pixel layout on little-endian: byte 2 (red channel) should be
    # fully saturated after painting pure red.
    assert data[2] == 255


def test_pango_cairo_can_shape_and_render_thai_text_via_harfbuzz():
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo
    import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 100)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    ctx.set_source_rgb(0, 0, 0)

    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription("Noto Sans Thai 32"))
    # Thai text requires HarfBuzz-driven complex shaping (combining vowel/tone
    # marks); a broken shaping stack renders empty glyphs or raises, but
    # doesn't necessarily raise a Python exception, so we assert actual ink.
    layout.set_text("เปิดบ้าน UTCC", -1)
    PangoCairo.show_layout(ctx, layout)

    ink_rect, logical_rect = layout.get_pixel_extents()
    assert logical_rect.width > 0
    assert ink_rect.width > 0

    data = surface.get_data()
    assert any(byte != 255 for byte in data), "expected some non-white (rendered) pixels"


def test_qrcode_and_pyzbar_round_trip_through_zbar_shared_library():
    import qrcode
    from PIL import Image
    from pyzbar.pyzbar import decode as zbar_decode

    target_url = "https://example.invalid/native-dep-smoke-test"
    image = qrcode.make(target_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    decoded = zbar_decode(Image.open(buffer))
    assert [d.data.decode("utf-8") for d in decoded] == [target_url]


def test_psycopg2_driver_is_importable_and_dbapi_compliant():
    import psycopg2

    assert psycopg2.apilevel == "2.0"
    assert psycopg2.paramstyle == "pyformat"


def test_paddle_and_paddleocr_are_importable():
    # Import-only: this is where paddlepaddle's glibc/AVX/CUDA-vs-CPU wheel
    # mismatches usually blow up. Full OCR inference (model download + a real
    # forward pass) is exercised later by the QA OCR tests (Task 13); this
    # smoke test only needs to prove the module loads in this image.
    import paddle
    import paddleocr

    assert hasattr(paddle, "__version__")
    assert hasattr(paddleocr, "PaddleOCR")
