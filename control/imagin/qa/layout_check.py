"""layout_contract_match — deterministic geometry QA (hard gate).

Validates that the composed poster actually honours the template contract
the generator and compositor both consumed: regions inside the canvas and
safe margins, text inside its assigned regions, logo clear space, QR fully
contained in the action card with its quiet zone, no content over the
protected subject region, panel matching the template, and text contrast
meeting the configured target. Subjective visual quality is explicitly NOT
automated here — this gate fails only objectively invalid geometry.
"""

from dataclasses import dataclass

from ..compositor import ComposedPoster
from ..palette import BrandPalette, contrast_ratio
from ..subject_detection import SubjectBox
from ..templates import PixelRect, PosterTemplate, ResolvedLayout

# Small tolerances for rounding, not for design errors.
CONTAINMENT_TOL = 4
MARGIN_TOL = 2
PANEL_MATCH_TOL = 4
QR_QUIET_ZONE_MIN_PX = 8


@dataclass(frozen=True)
class _Rect:
    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height


def _rect(name, r) -> _Rect:
    return _Rect(name=name, x=r.x, y=r.y, width=r.width, height=r.height)


def _inside(inner: _Rect, outer_x, outer_y, outer_right, outer_bottom, tol) -> bool:
    return (
        inner.x >= outer_x - tol
        and inner.y >= outer_y - tol
        and inner.right <= outer_right + tol
        and inner.bottom <= outer_bottom + tol
    )


def _inside_rect(inner: _Rect, outer: PixelRect, tol: int) -> bool:
    return _inside(inner, outer.x, outer.y, outer.x + outer.width, outer.y + outer.height, tol)


def _intersects(a: _Rect, b) -> bool:
    return not (
        a.right <= b.x or b.x + b.width <= a.x or a.bottom <= b.y or b.y + b.height <= a.y
    )


def _gap(a: _Rect, b: _Rect) -> int:
    dx = max(b.x - a.right, a.x - b.right, 0)
    dy = max(b.y - a.bottom, a.y - b.bottom, 0)
    return max(dx, dy) if (dx == 0 or dy == 0) else min(dx, dy)


def check_layout_contract(
    composed: ComposedPoster,
    template: PosterTemplate,
    layout: ResolvedLayout,
    palette: BrandPalette,
    subject_boxes: list[SubjectBox] | None = None,
) -> tuple[bool, str]:
    failures: list[str] = []
    width, height = layout.width, layout.height

    blocks = {b.name: _rect(f"text:{b.name}", b) for b in composed.text_blocks}
    content_rects: list[_Rect] = list(blocks.values())
    logo = _rect("logo", composed.logo_region) if composed.logo_region else None
    qr = _rect("qr", composed.qr_region) if composed.qr_region else None
    panel = _rect("panel", composed.panel_region) if composed.panel_region else None
    action = _rect("action", composed.action_region) if composed.action_region else None
    for extra in (logo, qr, panel, action):
        if extra is not None:
            content_rects.append(extra)

    # 1. Everything inside the canvas (nothing clipped).
    for rect in content_rects:
        if not _inside(rect, 0, 0, width, height, 0):
            failures.append(f"{rect.name} clipped by canvas: ({rect.x},{rect.y},{rect.width}x{rect.height})")

    # 2. Safe margins for all content rects.
    for rect in content_rects:
        if not _inside(rect, layout.margin_x, layout.margin_y, width - layout.margin_x, height - layout.margin_y, MARGIN_TOL):
            failures.append(f"{rect.name} violates safe margins ({layout.margin_x},{layout.margin_y})")

    # 3. Text blocks inside their assigned template regions.
    assignments = {"headline": layout.headline, "body": layout.body, "cta": layout.action}
    for name, assigned in assignments.items():
        block = blocks.get(name)
        if block is None:
            failures.append(f"missing text block {name!r}")
        elif not _inside_rect(block, assigned, CONTAINMENT_TOL):
            failures.append(
                f"text:{name} escapes its assigned region "
                f"(block=({block.x},{block.y},{block.width}x{block.height}) "
                f"region=({assigned.x},{assigned.y},{assigned.width}x{assigned.height}))"
            )

    # 4. Logo inside its region, with clear space against other content.
    if logo is None:
        failures.append("missing logo region")
    else:
        if not _inside_rect(logo, layout.logo, CONTAINMENT_TOL):
            failures.append("logo escapes its assigned region")
        clear_px = max(8, round(0.2 * layout.logo.height))
        for rect in content_rects:
            if rect.name in ("logo",):
                continue
            if _gap(logo, rect) < clear_px and _intersects(logo, rect):
                failures.append(f"{rect.name} intrudes into logo clear space")
            elif _gap(logo, rect) < clear_px:
                failures.append(f"{rect.name} within logo clear space ({_gap(logo, rect)}px < {clear_px}px)")

    # 5. QR fully inside the action card with its quiet zone.
    if qr is None or action is None:
        failures.append("missing qr or action region")
    else:
        if not _inside(qr, action.x + QR_QUIET_ZONE_MIN_PX, action.y + QR_QUIET_ZONE_MIN_PX,
                       action.right - QR_QUIET_ZONE_MIN_PX, action.bottom - QR_QUIET_ZONE_MIN_PX, 0):
            failures.append(
                f"qr not contained in action card with >= {QR_QUIET_ZONE_MIN_PX}px quiet zone "
                f"(qr=({qr.x},{qr.y},{qr.width}x{qr.height}) action=({action.x},{action.y},{action.width}x{action.height}))"
            )

    # 6. No content over the protected subject region.
    if not template.allow_content_overlap:
        for rect in content_rects:
            if _intersects(rect, layout.protected_subject):
                failures.append(f"{rect.name} overlaps the protected subject region")

    # 7. Panel matches the template's panel region.
    if panel is not None:
        expected = layout.panel
        deltas = (
            abs(panel.x - expected.x), abs(panel.y - expected.y),
            abs(panel.width - expected.width), abs(panel.height - expected.height),
        )
        if max(deltas) > PANEL_MATCH_TOL:
            failures.append(f"panel does not match template region (deltas={deltas})")

    # 8. Text contrast against the panel colour.
    for name, rgb_name in (("text", palette.text_rgb), ("accent", palette.accent_rgb)):
        ratio = contrast_ratio(rgb_name, palette.panel_rgb)
        if ratio < template.min_contrast_ratio:
            failures.append(
                f"{name} colour contrast {ratio:.2f} below required {template.min_contrast_ratio}"
            )

    # 9. Observed subject boxes (from a pluggable detector, when present):
    # text/QR/logo overlapping a detected subject fails.
    for box in subject_boxes or []:
        for rect in content_rects:
            if rect.name in ("panel",):
                continue  # the translucent panel is not glyph content
            if _intersects(rect, box):
                failures.append(
                    f"{rect.name} overlaps detected subject ({box.kind}) at "
                    f"({box.x},{box.y},{box.width}x{box.height})"
                )

    if failures:
        return False, f"{len(failures)} layout violation(s): " + "; ".join(failures)
    return True, (
        f"layout matches template {template.template_id!r}: all content in assigned "
        f"regions, margins respected, QR contained, subject region untouched"
    )
