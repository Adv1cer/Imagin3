import io

import httpx
import pytest
from PIL import Image

from imagin.brand import entity_resolution
from imagin.brand.crawler import RespectfulCrawler
from imagin.brand.discovery import discover_brand_assets

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"


def _png(width: int = 64, height: int = 64, color=(12, 34, 56, 255)) -> bytes:
    image = Image.new("RGBA", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _all_hosts_public(monkeypatch):
    # Default: treat every host as public. The redirect-SSRF test overrides
    # this with a stricter predicate.
    monkeypatch.setattr(entity_resolution, "_is_public_host", lambda host: True)


def _discover(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    crawler = RespectfulCrawler(client, min_interval_seconds=0)
    return discover_brand_assets("https://acme.example/", "acme.example", crawler, client)


def _html_response(request, body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": "text/html"}, request=request)


def test_homepage_to_same_domain_brand_page_to_png_accepted():
    home = b'<html><body><a href="/brand">Logo &amp; Brand Guidelines</a></body></html>'
    brand = b'<html><body><h1>Brand Guidelines</h1><a href="/assets/acme-logo.png">Logo (PNG)</a></body></html>'
    logo = _png()

    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return _html_response(request, home)
        if url == "https://acme.example/brand":
            return _html_response(request, brand)
        if url == "https://acme.example/assets/acme-logo.png":
            return httpx.Response(200, content=logo, headers={"content-type": "image/png"}, request=request)
        return httpx.Response(404, request=request)

    result = _discover(handler)

    assert result.outcome == "accepted"
    assert result.accepted is not None
    assert result.accepted.asset_url == "https://acme.example/assets/acme-logo.png"
    assert result.accepted.format == "png"
    assert result.accepted.score >= 60
    assert "official_brand_guideline" in result.accepted.evidence
    assert result.accepted.source_page_url == "https://acme.example/brand"


def test_brand_page_with_externally_hosted_download_asset_accepted():
    home = b'<html><body><a href="/brand-center">Brand Center</a></body></html>'
    brand = b'<html><body><a href="https://cdn.thirdparty.example/acme-brand-logo.png">Download logo</a></body></html>'
    logo = _png()

    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return _html_response(request, home)
        if url == "https://acme.example/brand-center":
            return _html_response(request, brand)
        if url == "https://cdn.thirdparty.example/acme-brand-logo.png":
            return httpx.Response(200, content=logo, headers={"content-type": "image/png"}, request=request)
        return httpx.Response(404, request=request)

    result = _discover(handler)

    assert result.outcome == "accepted"
    # The *page* was same-domain, but the asset itself is legitimately allowed
    # to live on an external CDN.
    assert result.accepted.asset_url == "https://cdn.thirdparty.example/acme-brand-logo.png"
    assert result.accepted.format == "png"


def test_third_party_candidate_remains_excluded():
    home = (
        b'<html><body><div class="partners">'
        b'<img src="https://partner.example/partner-logo.png">'
        b"</div></body></html>"
    )

    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return _html_response(request, home)
        # A partner logo must never be downloaded/accepted; if discovery tried,
        # this 404 (or absence) keeps it out — but it shouldn't even try.
        return httpx.Response(404, request=request)

    result = _discover(handler)

    assert result.outcome == "no_usable_asset"
    assert result.accepted is None
    assert "https://partner.example/partner-logo.png" not in [c.asset_url for c in result.candidates]


def test_spoofed_mime_or_invalid_bytes_rejected():
    home = b'<html><body><a href="/brand">Brand assets</a></body></html>'
    brand = b'<html><body><a href="/assets/logo.png">Logo PNG</a></body></html>'

    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return _html_response(request, home)
        if url == "https://acme.example/brand":
            return _html_response(request, brand)
        if url == "https://acme.example/assets/logo.png":
            # Claims image/png but the bytes are HTML — classic spoof.
            return httpx.Response(
                200,
                content=b"<html>definitely not a png</html>",
                headers={"content-type": "image/png"},
                request=request,
            )
        return httpx.Response(404, request=request)

    result = _discover(handler)

    assert result.outcome == "no_usable_asset"
    assert result.accepted is None
    assert any(r.asset_url == "https://acme.example/assets/logo.png" for r in result.rejected)


def test_redirect_to_private_host_rejected(monkeypatch):
    # Only the real public site is public; the redirect target is link-local.
    monkeypatch.setattr(entity_resolution, "_is_public_host", lambda host: host == "acme.example")

    home = b'<html><body><a href="/brand">Brand</a></body></html>'
    brand = b'<html><body><a href="/assets/logo.png">Logo</a></body></html>'

    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return _html_response(request, home)
        if url == "https://acme.example/brand":
            return _html_response(request, brand)
        if url == "https://acme.example/assets/logo.png":
            # 302 into the cloud metadata endpoint — the SSRF we must block.
            return httpx.Response(
                302,
                headers={"location": "http://169.254.169.254/latest/logo.png"},
                request=request,
            )
        return httpx.Response(404, request=request)

    result = _discover(handler)

    assert result.accepted is None
    rejected_by_url = {r.asset_url: r.reason for r in result.rejected}
    assert "https://acme.example/assets/logo.png" in rejected_by_url
    assert "not a public address" in rejected_by_url["https://acme.example/assets/logo.png"]


def test_no_accepted_candidate_returns_structured_no_usable_outcome():
    # Homepage with nothing that clears the bar: only a favicon.
    home = b'<html><head><link rel="icon" href="/favicon.ico"></head><body></body></html>'

    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return _html_response(request, home)
        return httpx.Response(404, request=request)

    result = _discover(handler)

    assert result.outcome == "no_usable_asset"
    assert result.accepted is None
    # The result is still structured/inspectable, not an exception.
    assert result.pages  # at least the homepage was recorded
    assert isinstance(result.candidates, list)
    assert isinstance(result.rejected, list)
