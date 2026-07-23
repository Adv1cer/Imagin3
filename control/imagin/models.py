import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)


class VerifiedDomain(Base):
    __tablename__ = "verified_domains"
    __table_args__ = (UniqueConstraint("organization_id", "domain"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    domain: Mapped[str] = mapped_column(String, nullable=False)
    verification_method: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="verified")
    verified_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class BrandProfile(Base):
    __tablename__ = "brand_profiles"
    __table_args__ = (UniqueConstraint("organization_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    profile: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)


class BrandAsset(Base):
    __tablename__ = "brand_assets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    brand_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brand_profiles.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_snapshots.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_now)
