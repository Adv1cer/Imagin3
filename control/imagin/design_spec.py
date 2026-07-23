from dataclasses import dataclass

POSTER_WIDTH = 1080
POSTER_HEIGHT = 1350
TEMPLATE_ID = "centered_editorial"


@dataclass(frozen=True)
class PosterCopy:
    headline: str
    body: list[str]
    cta: str


@dataclass(frozen=True)
class DesignSpec:
    mode: str
    width: int
    height: int
    template_id: str
    copy: PosterCopy
    qr_target_url: str
    negative_prompt: list[str]
    brand_profile_id: str
    brand_asset_id: str


def build_poster_design_spec(prompt: str, brand_profile_id: str, brand_asset_id: str, qr_target_url: str) -> DesignSpec:
    # Research automation is PROD-phase scope (PROD.md §6.4, FR-013); Week 1 uses a
    # hardcoded verified copy fixture for this one known prompt, per OKF §9.1 Week 1/4.
    #
    # qr_target_url is deliberately a REQUIRED caller-supplied argument, not a
    # default baked in here. A QR destination is operational config, not brand
    # copy — inventing one (e.g. guessing "/openhouse" exists on utcc.ac.th)
    # would risk printing a poster with a broken or misleading link. PROD.md
    # §7.4 additionally requires the destination be validated *fresh*,
    # immediately before the artifact is finalized — this function has no
    # business fabricating that value, only accepting one the caller already
    # verified (patched 2026-07-22; see ADR-001 patch notes).
    if not qr_target_url:
        raise ValueError(
            "qr_target_url must be supplied by the caller from a verified source; "
            "it must never be fabricated or guessed (PROD.md §7.4)"
        )

    copy = PosterCopy(
        headline="เปิดบ้าน UTCC",
        body=[
            "มหาวิทยาลัยหอการค้าไทย เปิดรับสมัครนักเรียนมัธยมปลาย",
            "ร่วมค้นหาเส้นทางสู่มหาวิทยาลัยในฝันของคุณ",
        ],
        cta="สมัครวันนี้",
    )
    return DesignSpec(
        mode="poster",
        width=POSTER_WIDTH,
        height=POSTER_HEIGHT,
        template_id=TEMPLATE_ID,
        copy=copy,
        qr_target_url=qr_target_url,
        # Image-only background constraints. The negative prompt lowers the
        # odds of the model drawing text/typography, but it is advisory —
        # the pipeline's pre-composition OCR background gate is what
        # actually enforces a text-free background.
        negative_prompt=[
            "text", "letters", "words", "typography", "logo", "watermark",
            "signage", "symbols", "poster design", "captions", "qr code",
            "writing", "characters", "subtitles",
        ],
        brand_profile_id=brand_profile_id,
        brand_asset_id=brand_asset_id,
    )
