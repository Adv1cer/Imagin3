import json
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Keywords (English + Thai) that, when they appear in a link's href, anchor
# text, rel, aria-label, title, or immediately surrounding text, mark that
# link as a likely route to official brand assets. Kept generic on purpose
# — NO organization name and NO fixed path like "/logo/" is hardcoded, so
# this works for any org's site, not just one.
BRAND_LINK_KEYWORDS = (
    "logo",
    "brand",
    "branding",
    "identity",
    "media kit",
    "media-kit",
    "mediakit",
    "press kit",
    "press-kit",
    "download",
    "ตราสัญลักษณ์",   # "logo/emblem" (Thai)
    "โลโก้",           # "logo" (Thai, loanword)
    "อัตลักษณ์",       # "identity" (Thai)
)

# File extensions that indicate a direct downloadable asset link (an <a
# href> pointing straight at an image/vector/print file), as opposed to a
# navigational page link.
DOWNLOAD_EXTENSIONS = (".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp", ".ai", ".eps", ".pdf")

# Contexts that mark an image as a *third party's* mark (a partner or
# sponsor logo) rather than the organization's own — a strong negative
# signal for §7.3 scoring.
PARTNER_CONTEXT_KEYWORDS = ("partner", "sponsor", "affiliate", "supporter", "member")


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


def _link_signal_text(anchor) -> str:
    parts = [
        anchor.get("href", ""),
        anchor.get_text(" ", strip=True),
        " ".join(anchor.get("rel") or []),
        anchor.get("aria-label", "") or "",
        anchor.get("title", "") or "",
    ]
    # Surrounding text: the anchor's parent block often labels the link
    # ("Downloads: Logo (PNG)") even when the anchor text itself is terse.
    if anchor.parent is not None:
        parts.append(anchor.parent.get_text(" ", strip=True))
    return " ".join(p for p in parts if p).lower()


def discover_brand_page_links(html: bytes, page_url: str) -> list[str]:
    """Find same-site links that plausibly lead to official brand assets.

    Scans every anchor's href, visible text, rel, aria-label, title, and
    surrounding text for BRAND_LINK_KEYWORDS. Returns absolute URLs, de-
    duplicated, order-preserved. Direct downloadable-asset links (an <a>
    pointing straight at a .png/.svg/... file) are intentionally excluded
    here — those are asset candidates, surfaced by extract_logo_candidates,
    not additional pages to crawl.
    """
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        path = urlparse(absolute).path.lower()
        if path.endswith(DOWNLOAD_EXTENSIONS):
            continue  # a direct asset link, not a page
        if any(keyword in _link_signal_text(anchor) for keyword in BRAND_LINK_KEYWORDS):
            if absolute not in seen:
                seen.add(absolute)
                found.append(absolute)

    return found


def _in_partner_context(node) -> bool:
    current = node
    depth = 0
    while current is not None and depth < 4:
        get = getattr(current, "get", None)
        if callable(get):
            classes = current.get("class") or []
            haystack = " ".join([*classes, current.get("id", "") or ""]).lower()
            if any(keyword in haystack for keyword in PARTNER_CONTEXT_KEYWORDS):
                return True
        current = current.parent
        depth += 1
    return False


def extract_logo_candidates(
    html: bytes, page_url: str, from_brand_guideline: bool = False
) -> ExtractionResult:
    """Extract logo/brand-asset candidates from a single page.

    Sources: JSON-LD Organization.logo, header <img>/<svg>, every <img>
    (with srcset), OpenGraph image, favicon, and explicit downloadable
    asset links (<a href="...png/.svg/.ai">). All candidate URLs are
    resolved to absolute against page_url. When from_brand_guideline is
    True, every candidate on the page additionally earns the strong
    'official_brand_guideline' provenance signal (§7.3 requirement 7).
    """
    soup = BeautifulSoup(html, "lxml")
    organization_name: str | None = None
    by_url: dict[str, LogoCandidate] = {}

    def add(raw_url: str | None, tag: str) -> None:
        if not raw_url:
            return
        absolute = urljoin(page_url, raw_url.strip())
        if not absolute.lower().startswith(("http://", "https://")):
            return
        _add_evidence(by_url, absolute, tag)
        if from_brand_guideline:
            _add_evidence(by_url, absolute, "official_brand_guideline")

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
                if isinstance(logo, dict):
                    logo = logo.get("url")
                if isinstance(logo, str):
                    add(logo, "organization_jsonld")

    for img in soup.select("header img, header svg"):
        add(img.get("src") or img.get("data-src"), "repeated_header_use")

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        tag = "partner_sponsor_context" if _in_partner_context(img) else "page_image"
        add(src, tag)
        srcset = img.get("srcset")
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            add(first, "srcset_source")

    icon_link = soup.find("link", rel=lambda v: v and "icon" in v)
    if icon_link and icon_link.get("href"):
        add(icon_link["href"], "favicon_only")

    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_image and og_image.get("content"):
        add(og_image["content"], "og_image_only")

    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(page_url, anchor["href"].strip())
        if urlparse(absolute).path.lower().endswith(DOWNLOAD_EXTENSIONS):
            add(anchor["href"], "explicit_download_link")

    return ExtractionResult(organization_name=organization_name, logo_candidates=list(by_url.values()))
