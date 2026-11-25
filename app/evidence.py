"""Acquire extracted article text as drafting evidence."""

import hashlib
from datetime import UTC, datetime
from http.client import HTTPException
from ssl import create_default_context
from urllib.parse import urlunsplit

import trafilatura
from sqlalchemy import select

from app.models import EvidenceAcquisition
from app.rss import FeedError, _FeedConnection, _read_body, _url, TIMEOUT


def fetch_document(url: str) -> bytes:
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
            return _read_body(response)
    except TimeoutError as exc:
        raise FeedError("timeout") from exc
    except (OSError, HTTPException, ValueError) as exc:
        raise FeedError("request_failed") from exc
    finally:
        connection.close()


def extract_text(html: bytes) -> str | None:
    """Reduce a fetched page to clean article text with trafilatura."""
    return trafilatura.extract(
        html, include_comments=False, include_tables=False, output_format="txt"
    )


def acquire(session, article, *, fetch=fetch_document, extract=extract_text):
    """Return the article's evidence record, fetching only when needed.

    Successful extractions are reused across runs; failed records are
    retried on the next pass.
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

    if record is None:
        record = EvidenceAcquisition(article_id=article.id)
        session.add(record)
    record.url = article.canonical_url
    record.fetched_at = datetime.now(UTC)
    record.status = "extracted" if text else "failed"
    record.detail = detail
    record.extracted_text = text
    record.content_sha256 = hashlib.sha256(body).hexdigest() if body else None
    return record
