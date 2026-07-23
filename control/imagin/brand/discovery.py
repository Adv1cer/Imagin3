"""Automatic official brand-asset discovery.

Starting from a verified official domain, this crawls the homepage and a
single additional level of same-site "brand / logo / media kit / download"
pages (respecting robots.txt, SSRF protection, redirect/size/page caps and
timeouts via RespectfulCrawler), extracts logo candidates, downloads and
validates each promising candidate's bytes, scores them with §7.3
evidence, and returns a structured result. The caller (registry) persists
accepted assets immutably and, when nothing qualifies, surfaces a
structured fallback rather than forcing a human to hand-upload a logo mid
flow.

No organization name and no fixed asset path (e.g. "/logo/") is hardcoded
anywhere here — discovery is driven entirely by on-page signals, so it
generalizes to any official domain.
"""

import hashlib
from dataclasses import dataclass, replace
from urllib.parse import urljoin, urlparse

import httpx

from . import entity_resolution
from .asset_validation import AssetValidationError, validate_asset_bytes
from .crawler import USER_AGENT, CrawlBlockedError, RespectfulCrawler
from .extractor import discover_brand_page_links, extract_logo_candidates
from .scoring import PROVISIONAL_THRESHOLD, score_logo_candidate

# One extra crawl level only, with hard caps.
MAX_BRAND_PAGES = 6
MAX_CANDIDATES_TO_DOWNLOAD = 15
MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_ASSET_REDIRECTS = 5
ASSET_TIMEOUT = 10.0

# Only bother downloading candidates whose pre-download evidence already
# gets them within reach of the usability threshold. This keeps us from
# fetching favicons, OG banners, partner logos, and bare page images while
# still leaving headroom for post-download signals (transparent bg) to
# lift a borderline candidate over the line. The acceptance threshold
# itself is unchanged (PROVISIONAL_THRESHOLD) — this only gates downloads.
DOWNLOAD_MIN_PRESCORE = PROVISIONAL_THRESHOLD - 20

# Aspect ratio beyond this (either orientation) is treated as "not a
# self-contained logo mark" — e.g. a full-width hero banner.
_MAX_LOGO_ASPECT_RATIO = 4.0


class AssetDownloadError(RuntimeError):
    """Raised when a candidate asset cannot be safely downloaded."""


@dataclass(frozen=True)
class CrawledPageRecord:
    url: str
    status_code: int
    content_type: str
    body: bytes


@dataclass(frozen=True)
class DiscoveredAsset:
    asset_url: str
    source_page_url: str
    redirect_chain: list[str]
    sha256: str
    content: bytes
    content_type: str
    format: str
    width: int | None
    height: int | None
    evidence: list[str]
    score: int
    status: str


@dataclass(frozen=True)
class RejectedCandidate:
    asset_url: str
    source_page_url: str
    reason: str


@dataclass(frozen=True)
class DiscoveryResult:
    organization_name: str | None
    outcome: str                       # "accepted" | "no_usable_asset"
    accepted: DiscoveredAsset | None
    candidates: list[DiscoveredAsset]  # downloaded + validated (may still be excluded by score)
    rejected: list[RejectedCandidate]  # download/validation failures
    pages: list[CrawledPageRecord]


def _host_of(url: str) -> str | None:
    return (urlparse(url).hostname or None)


def _is_public(host: str | None) -> bool:
    # Referenced through the module so tests that monkeypatch
    # imagin.brand.entity_resolution._is_public_host take effect here too.
    if not host:
        return False
    return entity_resolution._is_public_host(host)


def _same_host(url: str, host: str) -> bool:
    return (_host_of(url) or "").lower() == host.lower()


def _download_asset(client: httpx.Client, url: str) -> tuple[bytes, str, list[str]]:
    """Download an asset while following redirects *manually*, checking
    each hop's host is public BEFORE connecting to it.

    httpx's own follow_redirects would connect to a redirect target before
    we could inspect it — the classic SSRF hole where a public URL 302s to
    169.254.169.254 or an internal host. Following hops by hand lets us
    reject a redirect into private/loopback/link-local space, and also
    yields the full redirect chain for provenance recording.
    """
    chain: list[str] = []
    current = url
    for _ in range(MAX_ASSET_REDIRECTS + 1):
        host = _host_of(current)
        if not _is_public(host):
            raise AssetDownloadError(
                f"refusing to fetch {current}: host {host!r} is not a public address"
            )
        response = client.get(
            current,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
            timeout=ASSET_TIMEOUT,
        )
        chain.append(current)
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise AssetDownloadError(f"redirect with no Location while fetching {url}")
            current = urljoin(current, location)
            continue
        if response.status_code != 200:
            raise AssetDownloadError(f"asset {url} returned HTTP {response.status_code}")
        content = response.content
        if len(content) > MAX_ASSET_BYTES:
            raise AssetDownloadError(
                f"asset {url} exceeds max size {MAX_ASSET_BYTES} bytes"
            )
        return content, response.headers.get("content-type", ""), chain
    raise AssetDownloadError(f"too many redirects while fetching {url}")


def discover_brand_assets(
    canonical_url: str,
    official_domain: str,
    crawler: RespectfulCrawler,
    client: httpx.Client,
) -> DiscoveryResult:
    parsed = urlparse(canonical_url)
    host = parsed.hostname or official_domain
    scheme = parsed.scheme or "https"
    base_url = f"{scheme}://{host}"

    pages: list[CrawledPageRecord] = []
    # asset_url -> (LogoCandidate, source_page_url)
    candidate_map: dict[str, tuple] = {}
    organization_name: str | None = None

    def record(page) -> None:
        pages.append(
            CrawledPageRecord(
                url=page.url,
                status_code=page.status_code,
                content_type=page.content_type,
                body=page.body,
            )
        )

    def absorb(extraction, source_page_url: str) -> None:
        for candidate in extraction.logo_candidates:
            existing = candidate_map.get(candidate.url)
            if existing is None:
                candidate_map[candidate.url] = (candidate, source_page_url)
            else:
                prior, prior_src = existing
                merged = list(dict.fromkeys([*prior.evidence, *candidate.evidence]))
                candidate_map[candidate.url] = (replace(prior, evidence=merged), prior_src)

    # --- Homepage ---
    home = crawler.fetch(canonical_url, base_url)
    record(home)
    home_extraction = extract_logo_candidates(home.body, home.url, from_brand_guideline=False)
    organization_name = home_extraction.organization_name
    absorb(home_extraction, home.url)

    # --- One additional level: same-site brand/media-kit/download pages ---
    brand_links = [
        link
        for link in discover_brand_page_links(home.body, home.url)
        if _same_host(link, host) and link.rstrip("/") != home.url.rstrip("/")
    ]
    for link in brand_links[:MAX_BRAND_PAGES]:
        try:
            page = crawler.fetch(link, base_url)
        except (CrawlBlockedError, httpx.HTTPError):
            continue
        if page.status_code != 200:
            continue
        record(page)
        extraction = extract_logo_candidates(page.body, page.url, from_brand_guideline=True)
        if extraction.organization_name and not organization_name:
            organization_name = extraction.organization_name
        absorb(extraction, page.url)

    # --- Pre-score, then download + validate the promising candidates ---
    ranked = []
    for asset_url, (candidate, source_page) in candidate_map.items():
        pre = score_logo_candidate(candidate.evidence, candidate.is_svg, candidate.filename_hint)
        ranked.append((pre.score, asset_url, candidate, source_page))
    ranked.sort(key=lambda item: item[0], reverse=True)

    discovered: list[DiscoveredAsset] = []
    rejected: list[RejectedCandidate] = []
    downloads = 0

    for pre_score, asset_url, candidate, source_page in ranked:
        if pre_score < DOWNLOAD_MIN_PRESCORE:
            continue
        if downloads >= MAX_CANDIDATES_TO_DOWNLOAD:
            break
        downloads += 1

        try:
            content, content_type, chain = _download_asset(client, asset_url)
            validated = validate_asset_bytes(content, content_type)
        except (AssetDownloadError, AssetValidationError, httpx.HTTPError) as exc:
            rejected.append(RejectedCandidate(asset_url, source_page, str(exc)))
            continue

        evidence = list(candidate.evidence)
        if validated.has_alpha and "transparent_background" not in evidence:
            evidence.append("transparent_background")
        if validated.width and validated.height:
            longer, shorter = max(validated.width, validated.height), min(validated.width, validated.height)
            if shorter and longer / shorter > _MAX_LOGO_ASPECT_RATIO:
                evidence.append("inconsistent_aspect_ratio")

        final = score_logo_candidate(evidence, validated.is_svg, candidate.filename_hint)
        discovered.append(
            DiscoveredAsset(
                asset_url=asset_url,
                source_page_url=source_page,
                redirect_chain=chain,
                sha256=hashlib.sha256(content).hexdigest(),
                content=content,
                content_type=content_type,
                format=validated.format,
                width=validated.width,
                height=validated.height,
                evidence=evidence,
                score=final.score,
                status=final.status,
            )
        )

    usable = sorted(
        (d for d in discovered if d.status != "excluded"),
        key=lambda d: d.score,
        reverse=True,
    )
    accepted = usable[0] if usable else None
    outcome = "accepted" if accepted is not None else "no_usable_asset"

    return DiscoveryResult(
        organization_name=organization_name,
        outcome=outcome,
        accepted=accepted,
        candidates=discovered,
        rejected=rejected,
        pages=pages,
    )
