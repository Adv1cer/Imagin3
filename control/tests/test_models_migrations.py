import os
import subprocess
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from imagin.models import Organization, VerifiedDomain, BrandProfile, BrandAsset
from tests.conftest import test_database_url as _test_database_url


def test_migrations_create_expected_tables_and_round_trip():
    subprocess.run(
        ["alembic", "-x", f"db_url={_test_database_url()}", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), check=True,
    )
    engine = create_engine(_test_database_url())
    with Session(engine) as session:
        org = Organization(canonical_name="Test University")
        session.add(org)
        session.flush()

        session.add(VerifiedDomain(
            organization_id=org.id, domain="test.example.ac.th",
            verification_method="configured_official_domain", status="verified",
        ))
        profile = BrandProfile(
            organization_id=org.id, version=1, status="provisional",
            profile={"organizationName": "Test University", "officialDomain": "test.example.ac.th"},
        )
        session.add(profile)
        session.flush()
        session.add(BrandAsset(
            brand_profile_id=profile.id, type="logo", status="auto_accepted",
            storage_key="deadbeef.png", sha256="deadbeef", score=91,
        ))
        session.commit()

        fetched = session.scalar(select(Organization).where(Organization.canonical_name == "Test University"))
        assert fetched is not None
        assert isinstance(fetched.id, uuid.UUID)
