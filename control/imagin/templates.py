"""The shared layout contract.

One PosterTemplate (normalized 0.0–1.0 coordinates) is the single source
of truth consumed by ALL stages: template selection, the ComfyUI
background prompt builder, the deterministic compositor, and layout QA.
The root cause of the "panel over the students / empty top half" output
was that the generator and compositor made independent, incompatible
layout decisions — this module is where that stops: the generator is told
to keep the content region calm and put subjects in the hero region, and
the compositor puts content in exactly that content region.

Templates are organization-agnostic and resolution-agnostic: nothing here
knows about UTCC, and pixel geometry only exists after resolve_layout()
projects normalized regions onto a concrete canvas.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NormRect:
    """A rectangle in normalized [0, 1] canvas coordinates."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        for name, value in (("x", self.x), ("y", self.y), ("width", self.width), ("height", self.height)):
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"NormRect.{name}={value} outside [0, 1]")
        if self.x + self.width > 1.0 + 1e-9:
            raise ValueError(f"NormRect exceeds right edge: x+width={self.x + self.width}")
        if self.y + self.height > 1.0 + 1e-9:
            raise ValueError(f"NormRect exceeds bottom edge: y+height={self.y + self.height}")

    def resolve(self, canvas_width: int, canvas_height: int) -> "PixelRect":
        return PixelRect(
            x=int(round(self.x * canvas_width)),
            y=int(round(self.y * canvas_height)),
            width=int(round(self.width * canvas_width)),
            height=int(round(self.height * canvas_height)),
        )


@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class PosterTemplate:
    template_id: str
    description: str
    # Normalized safe margins (fraction of each axis).
    safe_margin_x: float
    safe_margin_y: float
    # Content regions (all normalized).
    logo_region: NormRect
    panel_region: NormRect
    headline_region: NormRect
    body_region: NormRect
    action_region: NormRect       # CTA + QR live together in one card here
    # Image regions.
    hero_region: NormRect          # where the generated subject belongs
    protected_subject_region: NormRect  # compositor content must NOT enter
    # Typography / styling.
    text_align: str                # "left" | "center"
    panel_style: str               # "card"
    panel_opacity: float
    spacing_scale: float
    headline_sizes: tuple[int, int]  # (min, max) pt
    body_sizes: tuple[int, int]
    cta_sizes: tuple[int, int]
    min_contrast_ratio: float
    # Generation-side instructions (organization-agnostic).
    background_instructions: str
    subject_instructions: str
    allow_content_overlap: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedLayout:
    """The template projected onto a concrete canvas, in pixels."""

    template_id: str
    width: int
    height: int
    margin_x: int
    margin_y: int
    logo: PixelRect
    panel: PixelRect
    headline: PixelRect
    body: PixelRect
    action: PixelRect
    hero: PixelRect
    protected_subject: PixelRect


def resolve_layout(template: PosterTemplate, width: int, height: int) -> ResolvedLayout:
    return ResolvedLayout(
        template_id=template.template_id,
        width=width,
        height=height,
        margin_x=int(round(template.safe_margin_x * width)),
        margin_y=int(round(template.safe_margin_y * height)),
        logo=template.logo_region.resolve(width, height),
        panel=template.panel_region.resolve(width, height),
        headline=template.headline_region.resolve(width, height),
        body=template.body_region.resolve(width, height),
        action=template.action_region.resolve(width, height),
        hero=template.hero_region.resolve(width, height),
        protected_subject=template.protected_subject_region.resolve(width, height),
    )


# Image-only constraints appended to every background prompt. Advisory —
# the pre-composition OCR background gate is the enforcement.
IMAGE_ONLY_PROMPT_SUFFIX = (
    "clean visual background, photographic scene only, "
    "no text, no letters, no words, no typography, no logo, no watermark, "
    "no signage, no symbols, no poster design, no captions"
)


def build_hero_prompt(user_prompt: str, template: PosterTemplate) -> str:
    """Compose the background-generation prompt from the user's subject
    description plus the TEMPLATE's placement instructions.

    Deliberately excludes the final poster copy (headline/body/CTA), the
    organization logo, and the QR content — those belong exclusively to
    the deterministic compositor. The image model only learns where the
    subject goes and which area must stay calm for overlaid content.
    """
    return (
        f"{user_prompt}. {template.background_instructions} "
        f"{template.subject_instructions} {IMAGE_ONLY_PROMPT_SUFFIX}"
    )


CENTERED_EDITORIAL = PosterTemplate(
    template_id="centered_editorial",
    description=(
        "Institutional/event poster: logo top-center with clear space, "
        "headline and copy in the calm upper content region, subjects in "
        "the lower hero region, CTA+QR in one action card."
    ),
    safe_margin_x=0.05,
    safe_margin_y=0.05,
    logo_region=NormRect(0.40, 0.055, 0.20, 0.08),
    panel_region=NormRect(0.07, 0.17, 0.86, 0.40),
    headline_region=NormRect(0.10, 0.19, 0.80, 0.11),
    body_region=NormRect(0.10, 0.31, 0.80, 0.13),
    action_region=NormRect(0.10, 0.45, 0.80, 0.10),
    hero_region=NormRect(0.0, 0.57, 1.0, 0.43),
    protected_subject_region=NormRect(0.08, 0.60, 0.84, 0.36),
    text_align="center",
    panel_style="card",
    panel_opacity=0.96,
    spacing_scale=1.0,
    headline_sizes=(36, 52),
    body_sizes=(26, 32),
    cta_sizes=(26, 34),
    min_contrast_ratio=4.5,
    background_instructions=(
        "Clean institutional campaign photograph with balanced, symmetric "
        "composition at eye level. Keep the upper portion of the frame "
        "visually calm, open, and unobstructed (soft sky, architecture, or "
        "gentle bokeh) — that upper area is reserved for overlaid content "
        "and must remain empty of strong detail."
    ),
    subject_instructions=(
        "Place the main subjects together in the lower portion of the "
        "frame, fully visible, with clear separation between the calm "
        "upper area and the subjects below."
    ),
)

HERO_SPLIT_LEFT = PosterTemplate(
    template_id="hero_split_left",
    description="Subject on the left; logo, copy, and action card in a right-hand content column.",
    safe_margin_x=0.05,
    safe_margin_y=0.05,
    logo_region=NormRect(0.60, 0.055, 0.28, 0.08),
    panel_region=NormRect(0.57, 0.17, 0.38, 0.72),
    headline_region=NormRect(0.59, 0.19, 0.34, 0.17),
    body_region=NormRect(0.59, 0.375, 0.34, 0.26),
    action_region=NormRect(0.59, 0.66, 0.34, 0.16),
    hero_region=NormRect(0.0, 0.25, 0.55, 0.75),
    protected_subject_region=NormRect(0.03, 0.32, 0.48, 0.62),
    text_align="left",
    panel_style="card",
    panel_opacity=0.96,
    spacing_scale=1.0,
    headline_sizes=(32, 48),
    body_sizes=(24, 30),
    cta_sizes=(24, 32),
    min_contrast_ratio=4.5,
    background_instructions=(
        "Clean campaign photograph with an asymmetric composition: the "
        "right side of the frame stays visually calm, open, and "
        "unobstructed — it is reserved for overlaid content."
    ),
    subject_instructions=(
        "Place the main subjects on the left side of the frame, facing or "
        "leading slightly toward the right side, fully visible."
    ),
)

HERO_SPLIT_RIGHT = PosterTemplate(
    template_id="hero_split_right",
    description="Subject on the right; logo, copy, and action card in a left-hand content column.",
    safe_margin_x=0.05,
    safe_margin_y=0.05,
    logo_region=NormRect(0.12, 0.055, 0.28, 0.08),
    panel_region=NormRect(0.05, 0.17, 0.38, 0.72),
    headline_region=NormRect(0.07, 0.19, 0.34, 0.17),
    body_region=NormRect(0.07, 0.375, 0.34, 0.26),
    action_region=NormRect(0.07, 0.66, 0.34, 0.16),
    hero_region=NormRect(0.45, 0.25, 0.55, 0.75),
    protected_subject_region=NormRect(0.49, 0.32, 0.48, 0.62),
    text_align="left",
    panel_style="card",
    panel_opacity=0.96,
    spacing_scale=1.0,
    headline_sizes=(32, 48),
    body_sizes=(24, 30),
    cta_sizes=(24, 32),
    min_contrast_ratio=4.5,
    background_instructions=(
        "Clean campaign photograph with an asymmetric composition: the "
        "left side of the frame stays visually calm, open, and "
        "unobstructed — it is reserved for overlaid content."
    ),
    subject_instructions=(
        "Place the main subjects on the right side of the frame, facing or "
        "leading slightly toward the left side, fully visible."
    ),
)

TEMPLATES: dict[str, PosterTemplate] = {
    t.template_id: t for t in (CENTERED_EDITORIAL, HERO_SPLIT_LEFT, HERO_SPLIT_RIGHT)
}
