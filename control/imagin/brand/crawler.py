import time
from dataclasses import dataclass
from urllib.robotparser import RobotFileParser

import httpx

MAX_REDIRECTS = 5
MAX_BYTES = 10 * 1024 * 1024
REQUEST_TIMEOUT = 10.0
USER_AGENT = "ImaginBrandCrawler/0.1 (+contact: brand-registry@imagin.local)"


class CrawlBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedPage:
    url: str
    status_code: int
    content_type: str
    body: bytes


class RespectfulCrawler:
    def __init__(self, client: httpx.Client, min_interval_seconds: float = 1.0):
        self._client = client
        self._min_interval = min_interval_seconds
        self._last_request_at = 0.0
        self._robots_cache: dict[str, RobotFileParser] = {}

    def _robots_for(self, base_url: str) -> RobotFileParser:
        if base_url not in self._robots_cache:
            parser = RobotFileParser()
            try:
                response = self._client.get(f"{base_url}/robots.txt", timeout=REQUEST_TIMEOUT)
                parser.parse(response.text.splitlines() if response.status_code < 400 else [])
            except httpx.HTTPError:
                parser.parse([])
            self._robots_cache[base_url] = parser
        return self._robots_cache[base_url]

    def fetch(self, url: str, base_url: str) -> FetchedPage:
        robots = self._robots_for(base_url)
        if not robots.can_fetch(USER_AGENT, url):
            raise CrawlBlockedError(f"robots.txt disallows fetching {url}")

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        response = self._client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        self._last_request_at = time.monotonic()

        if len(response.history) > MAX_REDIRECTS:
            raise CrawlBlockedError(f"too many redirects fetching {url}")
        if len(response.content) > MAX_BYTES:
            raise CrawlBlockedError(f"response for {url} exceeds max size of {MAX_BYTES} bytes")

        return FetchedPage(
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            body=response.content,
        )
