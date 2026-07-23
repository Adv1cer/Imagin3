import pytest
from imagin.design_spec import build_poster_design_spec


def test_build_poster_design_spec_has_required_poster_fields():
    spec = build_poster_design_spec(
        prompt="ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย",
        brand_profile_id="11111111-1111-1111-1111-111111111111",
        brand_asset_id="22222222-2222-2222-2222-222222222222",
        qr_target_url="https://example.ac.th/verified-by-caller",
    )

    assert spec.mode == "poster"
    assert spec.width == 1080 and spec.height == 1350
    assert spec.copy.headline
    assert len(spec.copy.body) >= 1
    assert spec.copy.cta
    # The QR target is passed through verbatim from the caller, never invented here.
    assert spec.qr_target_url == "https://example.ac.th/verified-by-caller"
    assert set(spec.negative_prompt) >= {"text", "logo", "qr code"}


def test_build_poster_design_spec_rejects_empty_qr_target_url():
    with pytest.raises(ValueError):
        build_poster_design_spec(
            prompt="ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย",
            brand_profile_id="11111111-1111-1111-1111-111111111111",
            brand_asset_id="22222222-2222-2222-2222-222222222222",
            qr_target_url="",
        )


def test_build_poster_design_spec_requires_caller_to_supply_qr_target_url():
    with pytest.raises(TypeError):
        build_poster_design_spec(
            prompt="ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย",
            brand_profile_id="11111111-1111-1111-1111-111111111111",
            brand_asset_id="22222222-2222-2222-2222-222222222222",
        )
