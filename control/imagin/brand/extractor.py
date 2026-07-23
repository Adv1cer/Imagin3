import json
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class LogoCandidate:
    url: str
    evidence: list[str]
    is_svg: bool
    filename_hint: str


@dataclass(frozen=True)
class ExtractionResult:
    organization_name: str | None
    logo_candidates: list[LogoCandidate]


def _add_evidence(candidates_by_url: dict[str, LogoCandidate], url: str, evidence_tag: str) -> None:
    # Multiple independent signals (JSON-LD, repeated header use, favicon, ...)
    # frequently point at the exact same logo file — e.g. the header <img> src
    # and the JSON-LD Organization.logo are often literally the same URL. §7.3
    # scoring is meant to accumulate evidence *about a candidate asset*, so
    # evidence for the same normalized URL must merge into one LogoCandidate
    # rather than silently splitting into several single-signal candidates
    # that individually never clear the usability threshold.
    existing = candidates_by_url.get(url)
    if existing is None:
        candidates_by_url[url] = LogoCandidate(
            url=url,
            evidence=[evidence_tag],
            is_svg=url.lower().endswith(".svg"),
            filename_hint=url.rsplit("/", 1)[-1],
        )
    elif evidence_tag not in existing.evidence:
        candidates_by_url[url] = LogoCandidate(
            url=existing.url,
            evidence=[*existing.evidence, evidence_tag],
            is_svg=existing.is_svg,
            filename_hint=existing.filename_hint,
        )


def extract_organization_page(html: bytes, page_url: str) -> ExtractionResult:
    soup = BeautifulSoup(html, "lxml")
    organization_name = None
    candidates_by_url: dict[str, LogoCandidate] = {}

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if isinstance(entry, dict) and entry.get("@type") == "Organization":
                organization_name = entry.get("name") or organization_name
                logo = entry.get("logo")
                if isinstance(logo, str):
                    _add_evidence(candidates_by_url, logo, "organization_jsonld")

    for img in soup.select("header img, header svg"):
        src = img.get("src") or img.get("data-src")
        if src:
            _add_evidence(candidates_by_url, src, "repeated_header_use")

    icon_link = soup.find("link", rel=lambda v: v and "icon" in v)
    if icon_link and icon_link.get("href"):
        _add_evidence(candidates_by_url, icon_link["href"], "favicon_only")

    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_image and og_image.get("content"):
        _add_evidence(candidates_by_url, og_image["content"], "og_image_only")

    return ExtractionResult(organization_name=organization_name, logo_candidates=list(candidates_by_url.values()))
