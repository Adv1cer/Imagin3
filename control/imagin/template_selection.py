"""Deterministic template selection, isolated so a local LLM planner can
replace or augment it later without touching the pipeline.

Selection never depends on a literal organization name — only on layout
intent expressed in the prompt. An explicit caller override always wins.
"""

from .templates import TEMPLATES, PosterTemplate


class UnknownTemplateError(ValueError):
    def __init__(self, template_id: str):
        options = ", ".join(sorted(TEMPLATES))
        super().__init__(
            f"unknown template {template_id!r}; available templates: {options}"
        )


# Layout-intent hints (Thai + English). Deliberately about *layout*, never
# about any organization.
_LEFT_HINTS = (
    "hero left", "split left", "image left", "image on the left", "photo left",
    "ภาพซ้าย", "รูปซ้าย", "ภาพด้านซ้าย", "รูปด้านซ้าย", "ภาพอยู่ซ้าย",
)
_RIGHT_HINTS = (
    "hero right", "split right", "image right", "image on the right", "photo right",
    "ภาพขวา", "รูปขวา", "ภาพด้านขวา", "รูปด้านขวา", "ภาพอยู่ขวา",
)


def validate_template(template_id: str) -> PosterTemplate:
    template = TEMPLATES.get(template_id)
    if template is None:
        raise UnknownTemplateError(template_id)
    return template


def infer_template_from_intent(prompt: str) -> str:
    """Rule-based default: split layouts only when the prompt asks for one;
    everything institutional/event/open-house shaped gets the centered
    editorial layout. This function is the seam for a future LLM planner."""
    lowered = prompt.lower()
    if any(hint in lowered for hint in _LEFT_HINTS):
        return "hero_split_left"
    if any(hint in lowered for hint in _RIGHT_HINTS):
        return "hero_split_right"
    return "centered_editorial"


def select_template(prompt: str, explicit_template_id: str | None = None) -> PosterTemplate:
    if explicit_template_id is not None:
        return validate_template(explicit_template_id)
    return validate_template(infer_template_from_intent(prompt))
