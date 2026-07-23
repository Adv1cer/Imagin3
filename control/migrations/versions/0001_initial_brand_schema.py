"""initial brand schema"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_name", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_table(
        "verified_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String, nullable=False),
        sa.Column("verification_method", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="verified"),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "domain"),
    )
    op.create_table(
        "source_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.String, nullable=False),
        sa.Column("domain", sa.String, nullable=False),
        sa.Column("retrieved_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
    )
    op.create_table(
        "brand_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("profile", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "version"),
    )
    op.create_table(
        "brand_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("storage_key", sa.String, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_snapshots.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("brand_assets")
    op.drop_table("brand_profiles")
    op.drop_table("source_snapshots")
    op.drop_table("verified_domains")
    op.drop_table("organizations")
