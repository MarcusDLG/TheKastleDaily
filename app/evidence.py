"""Acquire extracted article text as drafting evidence."""

import hashlib
from datetime import UTC, datetime
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from ssl import create_default_context
from urllib.parse import urljoin, urlunsplit

import trafilatura
from sqlalchemy import select

from app.database import database_path
from app.models import EvidenceAcquisition
from app.rss import FeedError, _FeedConnection, _read_body, _url, MAX_BYTES, TIMEOUT

# Matches the edition renderer's per-image contract limit.
PHOTO_MAX_BYTES = 4 * 1024 * 1024


def fetch_document(url: str, *, max_bytes: int = MAX_BYTES) -> bytes:
    """Fetch an article page with the feed fetcher's transport rules."""
    try:
        target = _url(url, feed=True)
    except ValueError as exc:
        raise FeedError("invalid_endpoint") from exc

    connection = _FeedConnection(
        target.hostname, timeout=TIMEOUT, context=create_default_context()
    )
    try:
        connection.request(
            "GET",
            urlunsplit(("", "", target.path or "/", target.query, "")),
            headers={
                "User-Agent": "TheKastleDaily/0.1",
                "Accept-Encoding": "identity",
            },
        )
        with connection.getresponse() as response:
            if response.status != 200:
                raise FeedError(f"http_{response.status}")
            return _read_body(response, max_bytes)
    except TimeoutError as exc:
        raise FeedError("timeout") from exc
    except (OSError, HTTPException, ValueError) as exc:
        raise FeedError("request_failed") from exc
    finally:
        connection.close()


def fetch_image(url: str) -> bytes:
    """Fetch a story photo under the same rules, at the renderer's size cap."""
    return fetch_document(url, max_bytes=PHOTO_MAX_BYTES)


def extract_text(html: bytes) -> str | None:
    """Reduce a fetched page to clean article text with trafilatura."""
    return trafilatura.extract(
        html, include_comments=False, include_tables=False, output_format="txt"
    )


class _OpenGraphParser(HTMLParser):
    """Collect the first content value per `og:` meta key."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        attributes = dict(attrs)
        key = (attributes.get("property") or attributes.get("name") or "")
        content = attributes.get("content")
        if content is None:
            return
        key = key.strip().lower()
        if key.startswith("og:") and key not in self.tags:
            self.tags[key] = content.strip()


def open_graph_image(html: bytes) -> dict | None:
    """Return the page's `og:image` URL and `og:image:alt` when declared."""
    parser = _OpenGraphParser()
    try:
        parser.feed(html.decode("utf-8", errors="replace"))
    except Exception:  # malformed markup is best-effort
        return None
    url = parser.tags.get("og:image")
    if not url:
        return None
    return {"url": url, "alt": parser.tags.get("og:image:alt") or None}


def photos_dir() -> Path:
    """Story photos live in a `photos` directory beside the built EPUBs."""
    db = database_path()
    base = Path(db).parent if db != ":memory:" else Path(".")
    return base / "editions" / "photos"


def store_photo(image_url: str, page_url: str, *, fetch_image=fetch_image) -> dict | None:
    """Download a declared story photo and store it for the edition build.

    Returns the render contract's `file` name (relative to the editions
    directory) plus the resolved source URL, or None when the photo is
    unavailable or outside the image contract. Missing photos never
    block a story — the renderer simply skips the figure.
    """
    resolved = urljoin(page_url, image_url)
    try:
        payload = fetch_image(resolved)
    except FeedError:
        return None
    if payload.startswith(b"\xff\xd8\xff"):
        suffix = "jpg"
    elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix = "png"
    else:
        return None
    name = f"{hashlib.sha256(payload).hexdigest()}.{suffix}"
    try:
        directory = photos_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / name
        if not target.exists():
            target.write_bytes(payload)
    except OSError:
        return None
    return {"file": f"photos/{name}", "url": resolved}


def acquire(
    session,
    article,
    *,
    fetch=fetch_document,
    extract=extract_text,
    fetch_image=fetch_image,
):
    """Return the article's evidence record, fetching only when needed.

    Successful extractions are reused across runs; failed records are
    retried on the next pass. When the page declares an `og:image`, the
    photo is fetched alongside the text for the edition render.
    """
    record = session.scalar(
        select(EvidenceAcquisition).where(
            EvidenceAcquisition.article_id == article.id
        )
    )
    if record is not None and record.status == "extracted":
        return record

    body = None
    try:
        body = fetch(article.canonical_url)
        text = extract(body)
    except FeedError as error:
        text, detail = None, str(error)
    except Exception as error:  # extraction is best-effort on untrusted input
        text, detail = None, f"extract_{type(error).__name__}"
    else:
        detail = "trafilatura" if text else "no_article_text"

    photo = None
    if text:
        declared = open_graph_image(body)
        if declared:
            photo = store_photo(
                declared["url"], article.canonical_url, fetch_image=fetch_image
            )
            if photo:
                photo["alt"] = declared["alt"]

    if record is None:
        record = EvidenceAcquisition(article_id=article.id)
        session.add(record)
    record.url = article.canonical_url
    record.fetched_at = datetime.now(UTC)
    record.status = "extracted" if text else "failed"
    record.detail = detail
    record.extracted_text = text
    record.content_sha256 = hashlib.sha256(body).hexdigest() if body else None
    record.photo_url = photo["url"] if photo else None
    record.photo_file = photo["file"] if photo else None
    record.photo_alt = photo["alt"] if photo else None
    return record
