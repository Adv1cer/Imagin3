import uuid
from dataclasses import dataclass
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
from .entity_resolution import resolve_official_domain
from .extractor import extract_organization_page
from .scoring import score_logo_candidate


FRESHNESS_DAYS = 30


class NoUsableBrandAssetError(RuntimeError):
    pass


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


def _latest_profile(
    session: Session,
    organization_id: uuid.UUID,
) -> BrandProfile | None:
    return session.scalar(
        select(BrandProfile)
        .where(BrandProfile.organization_id == organization_id)
        .order_by(BrandProfile.version.desc())
        .limit(1)
    )


def _to_resolved(
    session: Session,
    profile: BrandProfile,
) -> ResolvedBrand | None:
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


def _upsert_verified_domain(
    session: Session,
    organization_id: uuid.UUID,
    domain: str,
) -> VerifiedDomain:
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


def resolve_brand(
    session: Session,
    org_name: str,
    official_domain: str,
    http_client,
    object_store: LocalObjectStore,
) -> ResolvedBrand:
    org = session.scalar(
        select(Organization).where(
            Organization.canonical_name == org_name
        )
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
                return cached

            # The cached profile has no usable logo.
            # Continue with a fresh discovery.
    else:
        org = Organization(
            canonical_name=org_name,
            status="active",
        )
        session.add(org)
        session.flush()

    _upsert_verified_domain(
        session=session,
        organization_id=org.id,
        domain=official_domain,
    )

    resolved_domain = resolve_official_domain(
        official_domain,
        http_client,
    )

    crawler = RespectfulCrawler(http_client)
    base_url = f"https://{official_domain}"

    page = crawler.fetch(
        resolved_domain.canonical_url,
        base_url,
    )

    stored_snapshot = object_store.put(
        page.body,
        suffix=".html",
    )

    snapshot = SourceSnapshot(
        url=page.url,
        domain=official_domain,
        http_status=page.status_code,
        content_type=page.content_type,
        content_sha256=stored_snapshot.sha256,
    )
    session.add(snapshot)
    session.flush()

    extraction = extract_organization_page(
        page.body,
        page.url,
    )

    best_asset: BrandAsset | None = None
    best_score = -1000

    for candidate in extraction.logo_candidates:
        scored = score_logo_candidate(
            candidate.evidence,
            candidate.is_svg,
            candidate.filename_hint,
        )

        if scored.status == "excluded":
            continue

        if scored.score <= best_score:
            continue

        fetched_logo = crawler.fetch(
            candidate.url,
            base_url,
        )

        stored_logo = object_store.put(
            fetched_logo.body,
        )

        best_score = scored.score
        best_asset = BrandAsset(
            type="logo",
            status=scored.status,
            storage_key=stored_logo.storage_key,
            sha256=stored_logo.sha256,
            score=scored.score,
            source_snapshot_id=snapshot.id,
        )

    latest_profile = _latest_profile(session, org.id)
    next_version = (
        latest_profile.version + 1
        if latest_profile is not None
        else 1
    )

    if best_asset is None:
        profile_status = "invalid"
    elif best_asset.status == "auto_accepted":
        profile_status = "verified"
    else:
        profile_status = "provisional"

    profile = BrandProfile(
        organization_id=org.id,
        version=next_version,
        status=profile_status,
        profile={
            "organizationName": (
                extraction.organization_name or org_name
            ),
            "officialDomain": official_domain,
        },
    )
    session.add(profile)
    session.flush()

    if best_asset is not None:
        best_asset.brand_profile_id = profile.id
        session.add(best_asset)

    session.commit()

    if best_asset is None:
        raise NoUsableBrandAssetError(
            f"no logo candidate scored >= 60 for '{org_name}'; "
            "generation must omit the logo or request a manually "
            "uploaded asset (PROD.md §7.1a)"
        )

    return ResolvedBrand(
        organization_id=org.id,
        brand_profile_id=profile.id,
        profile_version=profile.version,
        logo_asset_id=best_asset.id,
        logo_storage_key=best_asset.storage_key,
        logo_sha256=best_asset.sha256,
    )