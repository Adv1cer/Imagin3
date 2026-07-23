import io

import cairo
import gi
import pytest

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

from imagin.pipeline import (
    BackgroundTextError,
    derive_background_seed,
    generate_validated_background,
    validate_background_text_free,
)


def _solid_png(width: int = 1080, height: int = 1350, rgb=(0.45, 0.5, 0.62)) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*rgb)
    ctx.paint()
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


def _png_with_text(text: str, width: int = 1080, height: int = 1350) -> bytes:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0.9, 0.9, 0.9)
    ctx.paint()
    ctx.set_source_rgb(0.05, 0.05, 0.05)
    layout = PangoCairo.create_layout(ctx)
    layout.set_font_description(Pango.FontDescription("Noto Sans Thai Bold 90"))
    layout.set_text(text, -1)
    ctx.translate(200, 400)
    PangoCairo.show_layout(ctx, layout)
    buffer = io.BytesIO()
    surface.write_to_png(buffer)
    return buffer.getvalue()


class FakeComfyUi:
    """Duck-typed stand-in for ComfyUiClient: serves a fixed image per seed
    and records every generate_image call. No DGX, no network."""

    def __init__(self, images_by_seed: dict[int, bytes], default: bytes):
        self._images_by_seed = images_by_seed
        self._default = default
        self.calls: list[dict] = []

    def generate_image(self, workflow, node_map, prompt_text, seed, width, height, negative_prompt_text=None):
        self.calls.append({
            "seed": seed,
            "prompt_text": prompt_text,
            "negative_prompt_text": negative_prompt_text,
        })
        return self._images_by_seed.get(seed, self._default)


# ---- Direct background validation (real OCR; Docker) ----------------------


def test_clean_generated_background_passes_validation():
    clean, readable = validate_background_text_free(_solid_png())

    assert clean is True
    assert readable == []


def test_background_containing_utcc_text_is_rejected():
    clean, readable = validate_background_text_free(_png_with_text("UTCC"))

    assert clean is False
    assert readable


def test_background_containing_thai_text_is_rejected():
    clean, readable = validate_background_text_free(_png_with_text("มหาวิทยาลัยหลอนๆ"))

    assert clean is False


# ---- Retry orchestration (real OCR on fixture images; fake ComfyUI) --------


def test_retry_uses_deterministic_derived_seeds_and_succeeds_on_clean_attempt():
    requested = 42
    seed0 = derive_background_seed(requested, 0)
    seed1 = derive_background_seed(requested, 1)
    assert seed0 == 42  # attempt 0 IS the requested seed
    assert seed1 != seed0
    assert derive_background_seed(requested, 1) == seed1  # reproducible

    dirty = _png_with_text("UTCC")
    clean = _solid_png()
    fake = FakeComfyUi(images_by_seed={seed0: dirty, seed1: clean}, default=clean)

    background, attempts = generate_validated_background(
        fake, workflow={}, node_map=None, prompt_text="p", negative_prompt_text="n",
        seed=requested, width=1080, height=1350, max_retries=2,
    )

    assert background == clean
    assert [a.seed for a in attempts] == [seed0, seed1]
    assert attempts[0].accepted is False and attempts[0].rejection_reason
    assert attempts[1].accepted is True
    assert [c["seed"] for c in fake.calls] == [seed0, seed1]


def test_exhausted_retries_raise_structured_failure_and_stop_at_limit():
    requested = 7
    dirty = _png_with_text("UTCC")
    fake = FakeComfyUi(images_by_seed={}, default=dirty)  # every seed dirty
    max_retries = 2

    with pytest.raises(BackgroundTextError) as exc_info:
        generate_validated_background(
            fake, workflow={}, node_map=None, prompt_text="p", negative_prompt_text="n",
            seed=requested, width=1080, height=1350, max_retries=max_retries,
        )

    error = exc_info.value
    # Bounded: exactly 1 + max_retries attempts — no infinite loop.
    assert len(fake.calls) == max_retries + 1
    assert len(error.attempts) == max_retries + 1
    expected_seeds = [derive_background_seed(requested, i) for i in range(max_retries + 1)]
    assert [a.seed for a in error.attempts] == expected_seeds
    assert all(not a.accepted and a.rejection_reason for a in error.attempts)
