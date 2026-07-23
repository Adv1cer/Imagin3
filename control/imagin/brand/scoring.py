from dataclasses import dataclass

EVIDENCE_SCORES = {
    "official_brand_guideline": 40,
    "organization_jsonld": 30,
    "repeated_header_use": 20,
    "svg_source": 15,
    "logo_filename_hint": 10,
    "transparent_background": 5,
    "favicon_only": -15,
    "og_image_only": -20,
    "partner_sponsor_context": -30,
    "inconsistent_aspect_ratio": -20,
}

AUTO_USE_THRESHOLD = 80
PROVISIONAL_THRESHOLD = 60


@dataclass(frozen=True)
class ScoredCandidate:
    score: int
    status: str  # auto_accepted | provisional | excluded


def classify_score(score: int) -> str:
    if score >= AUTO_USE_THRESHOLD:
        return "auto_accepted"
    if score >= PROVISIONAL_THRESHOLD:
        return "provisional"
    return "excluded"


def score_logo_candidate(evidence: list[str], is_svg: bool = False, filename_hint: str = "") -> ScoredCandidate:
    tags = list(evidence)
    if is_svg:
        tags.append("svg_source")
    if any(keyword in filename_hint.lower() for keyword in ("logo", "brand", "wordmark")):
        tags.append("logo_filename_hint")

    score = sum(EVIDENCE_SCORES.get(tag, 0) for tag in tags)
    return ScoredCandidate(score=score, status=classify_score(score))
