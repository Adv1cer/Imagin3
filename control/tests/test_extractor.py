from imagin.brand.extractor import extract_organization_page
from tests.fixtures.acme_pages import ACME_HOME_PAGE_HTML


def test_extract_organization_page_finds_jsonld_logo_and_name():
    result = extract_organization_page(ACME_HOME_PAGE_HTML, "https://acme.example/")

    assert result.organization_name == "Acme University"
    jsonld_candidates = [c for c in result.logo_candidates if "organization_jsonld" in c.evidence]
    assert len(jsonld_candidates) == 1
    assert jsonld_candidates[0].url == "https://acme.example/brand/logo.svg"
    assert jsonld_candidates[0].is_svg is True


def test_extract_organization_page_tags_header_favicon_and_og_image():
    result = extract_organization_page(ACME_HOME_PAGE_HTML, "https://acme.example/")

    evidence_tags = {tag for c in result.logo_candidates for tag in c.evidence}
    assert "repeated_header_use" in evidence_tags
    assert "favicon_only" in evidence_tags
    assert "og_image_only" in evidence_tags
