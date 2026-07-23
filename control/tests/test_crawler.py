import httpx
import pytest
from imagin.brand.crawler import RespectfulCrawler, CrawlBlockedError
from imagin.brand.crawler import MAX_BYTES
ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"
ROBOTS_DISALLOW_ALL = "User-agent: *\nDisallow: /\n"


def _client_with(pages: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return pages[str(request.url)]
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_succeeds_when_robots_allows(monkeypatch):
    client = _client_with({
        "https://example.ac.th/robots.txt": httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=httpx.Request("GET", "https://example.ac.th/robots.txt")),
        "https://example.ac.th/": httpx.Response(200, text="<html>home</html>", headers={"content-type": "text/html"}, request=httpx.Request("GET", "https://example.ac.th/")),
    })
    crawler = RespectfulCrawler(client, min_interval_seconds=0)

    page = crawler.fetch("https://example.ac.th/", "https://example.ac.th")

    assert page.status_code == 200
    assert b"home" in page.body


def test_fetch_raises_when_robots_disallows():
    client = _client_with({
        "https://example.ac.th/robots.txt": httpx.Response(200, text=ROBOTS_DISALLOW_ALL, request=httpx.Request("GET", "https://example.ac.th/robots.txt")),
    })
    crawler = RespectfulCrawler(client, min_interval_seconds=0)

    with pytest.raises(CrawlBlockedError):
        crawler.fetch("https://example.ac.th/", "https://example.ac.th")


def test_fetch_raises_when_response_too_large():
    big_body = b"x" * (MAX_BYTES + 1)

    client = _client_with({
        "https://example.ac.th/robots.txt": httpx.Response(
            200,
            text=ROBOTS_ALLOW_ALL,
            request=httpx.Request(
                "GET",
                "https://example.ac.th/robots.txt",
            ),
        ),
        "https://example.ac.th/": httpx.Response(
            200,
            content=big_body,
            headers={"content-type": "text/html"},
            request=httpx.Request(
                "GET",
                "https://example.ac.th/",
            ),
        ),
    })

    crawler = RespectfulCrawler(
        client,
        min_interval_seconds=0,
    )

    with pytest.raises(CrawlBlockedError):
        crawler.fetch(
            "https://example.ac.th/",
            "https://example.ac.th",
        )