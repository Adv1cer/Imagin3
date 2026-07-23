import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class DomainResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedDomain:
    domain: str
    canonical_url: str
    http_status: int


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise DomainResolutionError(f"cannot resolve host {host}: {exc}") from exc
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


def resolve_official_domain(domain: str, client: httpx.Client) -> ResolvedDomain:
    host = urlparse(f"https://{domain}").hostname or domain
    if not _is_public_host(host):
        raise DomainResolutionError(f"configured domain {domain} resolves to a non-public address")

    response = client.get(f"https://{domain}/", follow_redirects=True, timeout=10.0)
    if response.status_code >= 400:
        raise DomainResolutionError(f"official domain {domain} returned {response.status_code}")

    return ResolvedDomain(domain=domain, canonical_url=str(response.url), http_status=response.status_code)
