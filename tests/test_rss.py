from datetime import UTC, datetime

import pytest

from app import rss


def test_rss_metadata_only():
    entries = rss.parse_feed(b"""<rss version="2.0"><channel><item>
        <guid>first</guid><link>https://EXAMPLE.org:443/news#comments</link>
        <title> A   story </title><pubDate>Tue, 24 Nov 2026 12:15:00 -0500</pubDate>
        <description>Publisher text</description>
        </item><item><link>file:///tmp/file</link><title>Ignore</title></item>
        </channel></rss>""")

    assert entries == [
        rss.FeedItem(
            "first",
            "https://example.org/news",
            "A story",
            datetime(2026, 11, 24, 17, 15, tzinfo=UTC),
        )
    ]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"broken xml", "invalid_xml"),
        (b"<!DOCTYPE rss><rss><channel/></rss>", "invalid_xml"),
        (b"<html/>", "unsupported_feed"),
        (
            b"<rss><channel><item><link>invalid</link></item></channel></rss>",
            "no_valid_items",
        ),
    ],
)
def test_invalid_feeds(body, code):
    with pytest.raises(rss.FeedError, match=code):
        rss.parse_feed(body)


@pytest.mark.parametrize(
    "endpoint",
    ["http://example.org", "https://u@example.org", "https://example.org:81"],
)
def test_invalid_endpoint(endpoint):
    with pytest.raises(rss.FeedError, match="invalid_endpoint"):
        rss.fetch_feed(endpoint, None, None)


def test_reject_non_public_dns(monkeypatch):
    monkeypatch.setattr(
        rss.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(rss.socket.AF_INET, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(rss.FeedError, match="unsafe_address"):
        rss.fetch_feed("https://example.org/feed", None, None)


@pytest.mark.parametrize("status", [301, 304, 503])
def test_fetch_response(monkeypatch, status):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def getheader(self, name, default=None):
            return default

    response = Response()
    response.status = status

    class Connection:
        def request(self, method, target, *, headers):
            assert method == "GET"
            assert target == "/feed?q=test"
            assert headers["If-None-Match"] == '"original"'

        def getresponse(self):
            return response

        def close(self):
            pass

    monkeypatch.setattr(rss, "_FeedConnection", lambda *args, **kwargs: Connection())
    if status == 304:
        assert rss.fetch_feed(
            "https://example.org/feed?q=test", '"original"', None
        ) == (rss.FeedResponse(None, '"original"', None))
    else:
        with pytest.raises(rss.FeedError, match=f"http_{status}"):
            rss.fetch_feed("https://example.org/feed?q=test", '"original"', None)
