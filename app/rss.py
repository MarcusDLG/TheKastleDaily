"""Fetch approved RSS 2.0 and Atom feeds and extract article metadata."""

import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException, HTTPSConnection
from ssl import create_default_context
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

import feedparser

MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 200
TIMEOUT = 5


class FeedError(Exception):
    """A source-specific failure with a safe, machine-readable code."""


@dataclass(frozen=True)
class FeedResponse:
    body: bytes | None
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class FeedItem:
    external_id: str
    url: str
    title: str
    published_at: datetime | None


def _url(value: str, *, feed: bool):
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("Invalid URL")
    parsed = urlsplit(value)
    allowed = {"https"} if feed else {"https", "http"}
    if (
        parsed.scheme not in allowed
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443 if parsed.scheme == "https" else 80)
        or not parsed.hostname.isascii()
        or len(value.encode()) > 2000
    ):
        raise ValueError("Invalid URL")
    return parsed


class _FeedConnection(HTTPSConnection):
    def connect(self) -> None:
        # Connect to the checked socket address while authenticating the feed hostname.
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        for _, _, _, _, address in addresses:
            ip = ipaddress.ip_address(address[0])
            ip = getattr(ip, "ipv4_mapped", None) or ip
            if not ip.is_global or ip.is_multicast or ip.is_reserved:
                raise FeedError("unsafe_address")
        if not addresses:
            raise FeedError("dns_failure")
        error = None
        deadline = monotonic() + TIMEOUT
        for family, kind, protocol, _, address in addresses:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise FeedError("timeout")
            try:
                with socket.socket(family, kind, protocol) as raw:
                    raw.settimeout(remaining)
                    raw.connect(address)
                    self.sock = self._context.wrap_socket(
                        raw, server_hostname=self.host
                    )
                self.sock.settimeout(TIMEOUT)
                return
            except OSError as exc:
                error = exc
        raise FeedError("connection_failure") from error


def _read_body(response, limit=MAX_BYTES) -> bytes:
    """Read a bounded, uncompressed response body within the fetch timeout."""
    if response.getheader("Content-Encoding", "identity").lower() != "identity":
        raise FeedError("unsupported_encoding")
    body = bytearray()
    deadline = monotonic() + TIMEOUT
    while len(body) <= limit:
        if monotonic() > deadline:
            raise FeedError("timeout")
        chunk = response.read1(min(65536, limit + 1 - len(body)))
        if not chunk:
            if response.length:
                raise FeedError("response_truncated")
            return bytes(body)
        body.extend(chunk)
    raise FeedError("response_too_large")


def _validator(value: str | None) -> str | None:
    if value and len(value) <= 1024 and all(32 <= ord(char) <= 126 for char in value):
        return value
    return None


def fetch_feed(
    endpoint: str, etag: str | None, last_modified: str | None
) -> FeedResponse:
    try:
        url = _url(endpoint, feed=True)
    except ValueError as exc:
        raise FeedError("invalid_endpoint") from exc

    headers = {"User-Agent": "TheKastleDaily/0.1", "Accept-Encoding": "identity"}
    if _validator(etag):
        headers["If-None-Match"] = etag
    if _validator(last_modified):
        headers["If-Modified-Since"] = last_modified

    connection = _FeedConnection(
        url.hostname, timeout=TIMEOUT, context=create_default_context()
    )
    try:
        connection.request(
            "GET", urlunsplit(("", "", url.path or "/", url.query, "")), headers=headers
        )
        with connection.getresponse() as response:
            current_etag = _validator(response.getheader("ETag"))
            current_modified = _validator(response.getheader("Last-Modified"))
            if response.status == 304 and (len(headers) > 2):
                return FeedResponse(
                    None, current_etag or etag, current_modified or last_modified
                )
            if response.status != 200:
                raise FeedError(f"http_{response.status}")
            return FeedResponse(
                _read_body(response), current_etag, current_modified
            )
    except TimeoutError as exc:
        raise FeedError("timeout") from exc
    except (OSError, HTTPException, ValueError) as exc:
        raise FeedError("request_failed") from exc
    finally:
        connection.close()


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=UTC)
    return None


def parse_feed(body: bytes) -> list[FeedItem]:
    # feedparser tolerates real-world feed quirks but never resolves DTDs.
    if b"<!DOCTYPE" in body:
        raise FeedError("invalid_xml")
    parsed = feedparser.parse(body)
    if parsed.bozo and not parsed.entries:
        raise FeedError("invalid_xml")
    if not parsed.version:
        raise FeedError("unsupported_feed")

    items = []
    for entry in parsed.entries[:MAX_ITEMS]:
        title = " ".join((entry.get("title") or "").split())[:500]
        try:
            target = _url((entry.get("link") or "").strip(), feed=False)
        except ValueError:
            continue
        host = target.hostname
        authority = f"[{host}]" if ":" in host else host
        url = urlunsplit(
            (target.scheme, authority, target.path or "/", target.query, "")
        )
        external_id = (entry.get("id") or "").strip() or url
        if title and len(external_id.encode()) <= 2000:
            items.append(
                FeedItem(external_id, url, title, _entry_time(entry))
            )
    if not items and parsed.entries:
        raise FeedError("no_valid_items")
    return items
