import pytest

from imagin.palette import DEFAULT_PALETTE, contrast_ratio, ensure_min_contrast
from imagin.templates import (
    CENTERED_EDITORIAL,
    HERO_SPLIT_LEFT,
    HERO_SPLIT_RIGHT,
    IMAGE_ONLY_PROMPT_SUFFIX,
    NormRect,
    TEMPLATES,
    build_hero_prompt,
    resolve_layout,
)


def _regions(template):
    return {
        "logo": template.logo_region,
        "panel": template.panel_region,
        "headline": template.headline_region,
        "body": template.body_region,
        "action": template.action_region,
        "hero": template.hero_region,
        "protected": template.protected_subject_region,
    }


def _pixel_regions(layout):
    return {
        "logo": layout.logo,
        "panel": layout.panel,
        "headline": layout.headline,
        "body": layout.body,
        "action": layout.action,
        "hero": layout.hero,
        "protected": layout.protected_subject,
    }


def test_all_normalized_regions_are_within_unit_range():
    for template in TEMPLATES.values():
        for name, region in _regions(template).items():
            assert 0.0 <= region.x <= 1.0, (template.template_id, name)
            assert 0.0 <= region.y <= 1.0, (template.template_id, name)
            assert region.x + region.width <= 1.0 + 1e-9, (template.template_id, name)
            assert region.y + region.height <= 1.0 + 1e-9, (template.template_id, name)


def test_norm_rect_rejects_out_of_range_values():
    with pytest.raises(ValueError):
        NormRect(0.9, 0.0, 0.2, 0.1)  # x+width > 1
    with pytest.raises(ValueError):
        NormRect(-0.1, 0.0, 0.2, 0.1)


@pytest.mark.parametrize("canvas", [(1080, 1350), (900, 1600)])
def test_all_resolved_pixel_regions_are_inside_the_canvas(canvas):
    width, height = canvas
    for template in TEMPLATES.values():
        layout = resolve_layout(template, width, height)
        for name, rect in _pixel_regions(layout).items():
            assert rect.x >= 0 and rect.y >= 0, (template.template_id, name)
            assert rect.right <= width, (template.template_id, name)
            assert rect.bottom <= height, (template.template_id, name)


def _intersects(a, b) -> bool:
    return not (a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y)


def test_centered_editorial_content_and_protected_subject_regions_are_separate():
    layout = resolve_layout(CENTERED_EDITORIAL, 1080, 1350)
    protected = layout.protected_subject
    for name, rect in (("logo", layout.logo), ("panel", layout.panel),
                       ("headline", layout.headline), ("body", layout.body),
                       ("action", layout.action)):
        assert not _intersects(rect, protected), f"{name} overlaps protected subject region"


def test_hero_split_left_places_hero_left_and_content_right():
    layout = resolve_layout(HERO_SPLIT_LEFT, 1080, 1350)
    assert layout.hero.x < layout.panel.x
    assert layout.hero.right <= layout.panel.x
    assert layout.panel.x > 1080 // 2
    assert not _intersects(layout.panel, layout.protected_subject)


def test_hero_split_right_places_hero_right_and_content_left():
    layout = resolve_layout(HERO_SPLIT_RIGHT, 1080, 1350)
    assert layout.panel.x < layout.hero.x
    assert layout.panel.right <= layout.hero.x
    assert layout.panel.right < 1080 // 2
    assert not _intersects(layout.panel, layout.protected_subject)


def test_text_regions_sit_inside_panel_and_margins_for_every_template():
    for template in TEMPLATES.values():
        layout = resolve_layout(template, 1080, 1350)
        panel = layout.panel
        for name, rect in (("headline", layout.headline), ("body", layout.body), ("action", layout.action)):
            assert rect.x >= panel.x and rect.right <= panel.right, (template.template_id, name)
            assert rect.y >= panel.y and rect.bottom <= panel.bottom, (template.template_id, name)
        # Content regions respect safe margins (tolerance 2px for rounding).
        for name, rect in (("logo", layout.logo), ("panel", panel)):
            assert rect.x >= layout.margin_x - 2, (template.template_id, name)
            assert rect.right <= 1080 - layout.margin_x + 2, (template.template_id, name)
            assert rect.y >= layout.margin_y - 2, (template.template_id, name)
            assert rect.bottom <= 1350 - layout.margin_y + 2, (template.template_id, name)


def test_hero_prompt_reflects_selected_template_regions():
    centered = build_hero_prompt("โปสเตอร์ค่ายวิทยาศาสตร์เยาวชน", CENTERED_EDITORIAL)
    assert "lower portion" in centered and "upper" in centered

    left = build_hero_prompt("event poster", HERO_SPLIT_LEFT)
    assert "left side" in left and "right side" in left

    right = build_hero_prompt("event poster", HERO_SPLIT_RIGHT)
    assert "right side" in right and "left side" in right


def test_hero_prompt_contains_no_final_poster_copy():
    from imagin.design_spec import build_poster_design_spec

    spec = build_poster_design_spec(
        prompt="ทำโปสเตอร์เปิดบ้านมหาวิทยาลัยสำหรับนักเรียนมัธยมปลาย",
        brand_profile_id="p", brand_asset_id="a",
        qr_target_url="https://example.ac.th/verified",
    )
    prompt = build_hero_prompt("ทำโปสเตอร์เปิดบ้านมหาวิทยาลัยสำหรับนักเรียนมัธยมปลาย", spec.template)

    # Headline, body copy, and CTA belong exclusively to the compositor —
    # none of them may leak into the image-generation prompt.
    for copy_text in (spec.copy.headline, *spec.copy.body, spec.copy.cta):
        assert copy_text not in prompt
    assert IMAGE_ONLY_PROMPT_SUFFIX in prompt


def test_negative_prompt_still_prohibits_generated_text_and_logos():
    from imagin.design_spec import build_poster_design_spec

    spec = build_poster_design_spec(
        prompt="โปสเตอร์กิจกรรม", brand_profile_id="p", brand_asset_id="a",
        qr_target_url="https://example.ac.th/verified",
    )
    assert {"text", "logo", "watermark", "typography"} <= set(spec.negative_prompt)


def test_low_contrast_colour_is_deterministically_corrected():
    nearly_white = (0.93, 0.94, 0.95)
    corrected = ensure_min_contrast(nearly_white, DEFAULT_PALETTE.panel_rgb, 4.5)

    assert contrast_ratio(corrected, DEFAULT_PALETTE.panel_rgb) >= 4.5
    # Deterministic: identical input, identical output.
    assert corrected == ensure_min_contrast(nearly_white, DEFAULT_PALETTE.panel_rgb, 4.5)
