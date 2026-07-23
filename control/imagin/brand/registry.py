import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    BrandAsset,
    BrandProfile,
    Organization,
    SourceSnapshot,
    VerifiedDomain,
)
from ..object_store import LocalObjectStore
from .crawler import RespectfulCrawler
from .discovery import DiscoveryResult, discover_brand_assets
from .entity_resolution import resolve_official_domain

FRESHNESS_DAYS = 30


@dataclass(frozen=True)
class BrandResolutionFallback:
    """Structured outcome returned (via the raised error) when automatic
    discovery finds no usable official logo.

    The point is that the caller — CLI, API, or a human operator — can make
    an informed decision (proceed with the logo omitted, or supply a
    manually-verified asset) from real data, instead of being handed a
    Python traceback. It records what was considered and why each candidate
    was rejected, so the decision is auditable.
    """

    organization_name: str | None
    official_domain: str
    outcome: str
    considered: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    suggested_actions: tuple[str, ...] = ("omit_logo", "upload_manual_asset")


class NoUsableBrandAssetError(RuntimeError):
    """No discovered candidate cleared the §7.3 usability threshold.

    Carries a BrandResolutionFallback on `.fallback` so callers can present
    a clean, actionable outcome without exposing internals.
    """

    def __init__(self, message: str, fallback: BrandResolutionFallback | None = None):
        super().__init__(message)
        self.fallback = fallback


@dataclass(frozen=True)
class ResolvedBrand:
    organization_id: uuid.UUID
    brand_profile_id: uuid.UUID
    profile_version: int
    logo_asset_id: uuid.UUID
    logo_storage_key: str
    logo_sha256: str


def _is_fresh(profile: BrandProfile) -> bool:
    return (
        datetime.now(timezone.utc) - profile.created_at
        < timedelta(days=FRESHNESS_DAYS)
    )


def _latest_profile(session: Session, organization_id: uuid.UUID) -> BrandProfile | None:
    return session.scalar(
        select(BrandProfile)
        .where(BrandProfile.organization_id == organization_id)
        .order_by(BrandProfile.version.desc())
        .limit(1)
    )


def _to_resolved(session: Session, profile: BrandProfile) -> ResolvedBrand | None:
    asset = session.scalar(
        select(BrandAsset)
        .where(
            BrandAsset.brand_profile_id == profile.id,
            BrandAsset.type == "logo",
            BrandAsset.storage_key.is_not(None),
            BrandAsset.sha256.is_not(None),
        )
        .order_by(BrandAsset.score.desc().nullslast())
        .limit(1)
    )
    if asset is None:
        return None
    return ResolvedBrand(
        organization_id=profile.organization_id,
        brand_profile_id=profile.id,
        profile_version=profile.version,
        logo_asset_id=asset.id,
        logo_storage_key=asset.storage_key,
        logo_sha256=asset.sha256,
    )


def _upsert_verified_domain(session: Session, organization_id: uuid.UUID, domain: str) -> VerifiedDomain:
    existing = session.scalar(
        select(VerifiedDomain).where(
            VerifiedDomain.organization_id == organization_id,
            VerifiedDomain.domain == domain,
        )
    )
    if existing is not None:
        existing.status = "verified"
        existing.verification_method = "configured_official_domain"
        existing.verified_at = datetime.now(timezone.utc)
        return existing

    verified_domain = VerifiedDomain(
        organization_id=organization_id,
        domain=domain,
        verification_method="configured_official_domain",
        status="verified",
    )
    session.add(verified_domain)
    return verified_domain


def _record_page_snapshots(
    session: Session,
    object_store: LocalObjectStore,
    discovery: DiscoveryResult,
    official_domain: str,
) -> dict[str, uuid.UUID]:
    """Persist every crawled page as an immutable SourceSnapshot and return
    a {page_url: snapshot_id} map for provenance linking."""
    snapshot_ids: dict[str, uuid.UUID] = {}
    for page in discovery.pages:
        stored = object_store.put(page.body, suffix=".html")
        snapshot = SourceSnapshot(
            url=page.url,
            domain=official_domain,
            http_status=page.status_code,
            content_type=page.content_type,
            content_sha256=stored.sha256,
        )
        session.add(snapshot)
        session.flush()
        snapshot_ids[page.url] = snapshot.id
    return snapshot_ids


def _fallback_from(discovery: DiscoveryResult, official_domain: str) -> BrandResolutionFallback:
    return BrandResolutionFallback(
        organization_name=discovery.organization_name,
        official_domain=official_domain,
        outcome=discovery.outcome,
        considered=[
            {
                "asset_url": c.asset_url,
                "source_page_url": c.source_page_url,
                "score": c.score,
                "status": c.status,
                "evidence": c.evidence,
            }
            for c in discovery.candidates
        ],
        rejected=[
            {"asset_url": r.asset_url, "source_page_url": r.source_page_url, "reason": r.reason}
            for r in discovery.rejected
        ],
    )


def resolve_brand(
    session: Session,
    org_name: str,
    official_domain: str,
    http_client,
    object_store: LocalObjectStore,
) -> ResolvedBrand:
    org = session.scalar(
        select(Organization).where(Organization.canonical_name == org_name)
    )

    if org is not None:
        latest = _latest_profile(session, org.id)
        if (
            latest is not None
            and latest.status in ("verified", "provisional")
            and _is_fresh(latest)
        ):
            cached = _to_resolved(session, latest)
            if cached is not None:
                # Cache hit with a usable asset — reuse immediately, no recrawl.
                return cached
            # Cached profile has no usable logo; fall through to re-discover.
    else:
        org = Organization(canonical_name=org_name, status="active")
        session.add(org)
        session.flush()

    _upsert_verified_domain(session=session, organization_id=org.id, domain=official_domain)

    resolved_domain = resolve_official_domain(official_domain, http_client)
    crawler = RespectfulCrawler(http_client)

    discovery = discover_brand_assets(
        canonical_url=resolved_domain.canonical_url,
        official_domain=official_domain,
        crawler=crawler,
        client=http_client,
    )

    snapshot_ids = _record_page_snapshots(session, object_store, discovery, official_domain)

    latest_profile = _latest_profile(session, org.id)
    next_version = latest_profile.version + 1 if latest_profile is not None else 1

    accepted = discovery.accepted

    if accepted is None:
        # Record the (asset-less) discovery attempt as a profile version so
        # the audit trail is complete, then hand back a structured fallback
        # instead of a bare failure. Bytes/versions are never overwritten.
        profile = BrandProfile(
            organization_id=org.id,
            version=next_version,
            status="logo_unresolved",
            profile={
                "organizationName": discovery.organization_name or org_name,
                "officialDomain": official_domain,
                "logoOutcome": discovery.outcome,
            },
        )
        session.add(profile)
        session.commit()
        raise NoUsableBrandAssetError(
            f"automatic brand-asset discovery found no logo candidate scoring "
            f">= 60 for '{org_name}' at {official_domain}; the caller may proceed "
            "with the logo omitted or supply a manually-verified asset "
            "(PROD.md §7.1a).",
            fallback=_fallback_from(discovery, official_domain),
        )

    stored_logo = object_store.put(accepted.content)

    profile_status = "verified" if accepted.status == "auto_accepted" else "provisional"
    profile = BrandProfile(
        organization_id=org.id,
        version=next_version,
        status=profile_status,
        profile={
            "organizationName": discovery.organization_name or org_name,
            "officialDomain": official_domain,
            "logoProvenance": {
                "assetUrl": accepted.asset_url,
                "sourcePageUrl": accepted.source_page_url,
                "redirectChain": accepted.redirect_chain,
                "sha256": accepted.sha256,
                "format": accepted.format,
                "width": accepted.width,
                "height": accepted.height,
                "evidence": accepted.evidence,
                "score": accepted.score,
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
            },
        },
    )
    session.add(profile)
    session.flush()

    asset = BrandAsset(
        brand_profile_id=profile.id,
        type="logo",
        status=accepted.status,
        storage_key=stored_logo.storage_key,
        sha256=accepted.sha256,
        score=accepted.score,
        source_snapshot_id=snapshot_ids.get(accepted.source_page_url),
    )
    session.add(asset)
    session.commit()

    return ResolvedBrand(
        organization_id=org.id,
        brand_profile_id=profile.id,
        profile_version=profile.version,
        logo_asset_id=asset.id,
        logo_storage_key=asset.storage_key,
        logo_sha256=asset.sha256,
    )
