import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from imagin.brand.registry import resolve_brand, NoUsableBrandAssetError
from imagin.models import BrandProfile, BrandAsset, VerifiedDomain
from tests.fixtures.acme_pages import ACME_HOME_PAGE_HTML

ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"


def _acme_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return httpx.Response(200, content=ACME_HOME_PAGE_HTML, headers={"content-type": "text/html"}, request=request)
        if url == "https://acme.example/brand/logo.svg":
            return httpx.Response(200, content=b"<svg>acme-logo</svg>", headers={"content-type": "image/svg+xml"}, request=request)
        return httpx.Response(404, request=request)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_resolve_brand_creates_new_org_and_versioned_profile(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))

    resolved = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    assert resolved.profile_version == 1
    profile = db_session.get(BrandProfile, resolved.brand_profile_id)
    assert profile.status in ("verified", "provisional")
    asset = db_session.scalar(select(BrandAsset).where(BrandAsset.brand_profile_id == profile.id))
    assert asset.storage_key == resolved.logo_storage_key
    assert store.get(asset.storage_key) == b"<svg>acme-logo</svg>"


def test_resolve_brand_reuses_fresh_cached_profile_without_recrawling(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))
    first = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not re-crawl when cache is fresh")
    second = resolve_brand(db_session, "Acme University", "acme.example", httpx.Client(transport=httpx.MockTransport(failing_handler)), store)

    assert second.brand_profile_id == first.brand_profile_id
    assert second.profile_version == first.profile_version


def test_resolve_brand_never_overwrites_prior_version_row(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))
    first = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    # force staleness so a second resolve re-crawls and creates version 2
    profile = db_session.get(BrandProfile, first.brand_profile_id)
    from datetime import datetime, timedelta, timezone
    profile.created_at = datetime.now(timezone.utc) - timedelta(days=999)
    db_session.commit()

    second = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    assert second.profile_version == 2
    still_present = db_session.get(BrandProfile, first.brand_profile_id)
    assert still_present is not None  # version 1 row untouched, not overwritten


def test_resolve_brand_upserts_verified_domain_on_refresh_instead_of_duplicating(db_session: Session, tmp_path, monkeypatch):
    # Regression test for the VerifiedDomain unique-constraint violation: a
    # second (refresh) resolve_brand() call for the same organization+domain
    # must update the existing verified_domains row in place, not insert a
    # second one (organization_id, domain) is unique.
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))
    first = resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    profile = db_session.get(BrandProfile, first.brand_profile_id)
    from datetime import datetime, timedelta, timezone
    first_verified_at = db_session.scalar(
        select(VerifiedDomain.verified_at).where(
            VerifiedDomain.organization_id == first.organization_id,
            VerifiedDomain.domain == "acme.example",
        )
    )
    profile.created_at = datetime.now(timezone.utc) - timedelta(days=999)
    db_session.commit()

    resolve_brand(db_session, "Acme University", "acme.example", _acme_client(), store)

    domain_rows = db_session.scalars(
        select(VerifiedDomain).where(
            VerifiedDomain.organization_id == first.organization_id,
            VerifiedDomain.domain == "acme.example",
        )
    ).all()
    assert len(domain_rows) == 1
    assert domain_rows[0].verified_at >= first_verified_at


def test_resolve_brand_raises_when_no_candidate_scores_above_exclusion(db_session: Session, tmp_path, monkeypatch):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore
    store = LocalObjectStore(str(tmp_path))

    only_favicon_html = b"""
    <html><head><link rel="icon" href="https://noassets.example/favicon.ico"></head><body></body></html>
    """
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://noassets.example/":
            return httpx.Response(200, content=only_favicon_html, headers={"content-type": "text/html"}, request=request)
        return httpx.Response(404, request=request)
    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(NoUsableBrandAssetError):
        resolve_brand(db_session, "No Assets Org", "noassets.example", client, store)


def _png(width: int = 64, height: int = 64, color=(12, 34, 56, 255)) -> bytes:
    import io

    from PIL import Image

    image = Image.new("RGBA", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _brandpage_client() -> httpx.Client:
    home = b'<html><body><a href="/brand">Logo &amp; Brand Guidelines</a></body></html>'
    brand = b'<html><body><a href="/assets/acme-logo.png">Download logo (PNG)</a></body></html>'
    logo = _png()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://acme.example/":
            return httpx.Response(200, content=home, headers={"content-type": "text/html"}, request=request)
        if url == "https://acme.example/brand":
            return httpx.Response(200, content=brand, headers={"content-type": "text/html"}, request=request)
        if url == "https://acme.example/assets/acme-logo.png":
            return httpx.Response(200, content=logo, headers={"content-type": "image/png"}, request=request)
        return httpx.Response(404, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_resolve_brand_auto_discovers_logo_from_brand_page_and_records_provenance(
    db_session: Session, tmp_path, monkeypatch
):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore

    store = LocalObjectStore(str(tmp_path))

    resolved = resolve_brand(db_session, "Acme University", "acme.example", _brandpage_client(), store)

    profile = db_session.get(BrandProfile, resolved.brand_profile_id)
    provenance = profile.profile["logoProvenance"]
    assert provenance["assetUrl"] == "https://acme.example/assets/acme-logo.png"
    assert provenance["sourcePageUrl"] == "https://acme.example/brand"
    assert provenance["format"] == "png"
    assert provenance["sha256"] == resolved.logo_sha256
    assert "official_brand_guideline" in provenance["evidence"]

    asset = db_session.scalar(select(BrandAsset).where(BrandAsset.brand_profile_id == profile.id))
    assert asset.source_snapshot_id is not None  # linked to the brand page it came from
    assert store.get(asset.storage_key)  # bytes were stored immutably


def test_resolve_brand_no_usable_asset_raises_with_structured_fallback(
    db_session: Session, tmp_path, monkeypatch
):
    monkeypatch.setattr("imagin.brand.entity_resolution._is_public_host", lambda host: True)
    from imagin.object_store import LocalObjectStore

    store = LocalObjectStore(str(tmp_path))

    home = b'<html><body><a href="/brand">Brand assets</a></body></html>'
    brand = b'<html><body><a href="/assets/logo.png">Logo PNG</a></body></html>'

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("robots.txt"):
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)
        if url == "https://spoof.example/":
            return httpx.Response(200, content=home, headers={"content-type": "text/html"}, request=request)
        if url == "https://spoof.example/brand":
            return httpx.Response(200, content=brand, headers={"content-type": "text/html"}, request=request)
        if url == "https://spoof.example/assets/logo.png":
            return httpx.Response(
                200, content=b"<html>not a png</html>",
                headers={"content-type": "image/png"}, request=request,
            )
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(NoUsableBrandAssetError) as exc_info:
        resolve_brand(db_session, "Spoof Org", "spoof.example", client, store)

    fallback = exc_info.value.fallback
    assert fallback is not None
    assert fallback.outcome == "no_usable_asset"
    assert "omit_logo" in fallback.suggested_actions
    assert any(r["asset_url"] == "https://spoof.example/assets/logo.png" for r in fallback.rejected)
