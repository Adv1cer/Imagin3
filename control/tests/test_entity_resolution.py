import httpx
import pytest
from imagin.brand.entity_resolution import resolve_official_domain, DomainResolutionError


def test_resolve_official_domain_succeeds_for_reachable_https_domain(monkeypatch):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host", lambda host: True
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "utcc.ac.th"
        return httpx.Response(200, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    resolved = resolve_official_domain("utcc.ac.th", client)

    assert resolved.domain == "utcc.ac.th"
    assert resolved.http_status == 200


def test_resolve_official_domain_rejects_non_public_address(monkeypatch):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host", lambda host: False
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, request=r)))

    with pytest.raises(DomainResolutionError):
        resolve_official_domain("internal.local", client)


def test_resolve_official_domain_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        "imagin.brand.entity_resolution._is_public_host", lambda host: True
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, request=r)))

    with pytest.raises(DomainResolutionError):
        resolve_official_domain("utcc.ac.th", client)
