import pytest

from imagin.template_selection import (
    UnknownTemplateError,
    infer_template_from_intent,
    select_template,
)


def test_invalid_template_identifier_fails_with_readable_error():
    with pytest.raises(UnknownTemplateError) as exc_info:
        select_template("any prompt", "totally_bogus_template")

    message = str(exc_info.value)
    assert "totally_bogus_template" in message
    assert "centered_editorial" in message  # available options are listed


def test_explicit_override_wins_over_automatic_selection():
    # Prompt intent says split-left; explicit override must win anyway.
    template = select_template("โปสเตอร์ ภาพด้านซ้าย", "hero_split_right")
    assert template.template_id == "hero_split_right"


def test_generic_open_house_institutional_intent_selects_centered_editorial():
    # Generic institutional/open-house prompt — deliberately NOT the UTCC
    # prompt and containing no organization name.
    template = select_template("ทำโปสเตอร์เปิดบ้านมหาวิทยาลัยสำหรับนักเรียนมัธยมปลาย")
    assert template.template_id == "centered_editorial"


def test_selection_does_not_depend_on_literal_organization_name():
    # Same design intent, three different (fictional) organizations —
    # selection result is identical because it only reads layout intent.
    prompts = [
        "ทำโปสเตอร์โปรโมต Acme สำหรับนักเรียน ม.ปลาย",
        "ทำโปสเตอร์โปรโมต Beta College สำหรับนักเรียน ม.ปลาย",
        "ทำโปสเตอร์งาน open house ของวิทยาลัยแห่งหนึ่ง",
    ]
    results = {infer_template_from_intent(p) for p in prompts}
    assert results == {"centered_editorial"}


def test_split_layout_intent_selects_split_templates():
    assert infer_template_from_intent("โปสเตอร์ วางภาพด้านซ้าย ข้อความขวา") == "hero_split_left"
    assert infer_template_from_intent("poster with the image on the right") == "hero_split_right"
