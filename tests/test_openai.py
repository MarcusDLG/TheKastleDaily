import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.drafting import run_drafting
from app.models import (
    Article,
    ArticleSource,
    Base,
    EditorialRun,
    EditorialStory,
    IngestionRun,
    Source,
)
from app.openai import OpenAIGenerator, ProviderError, openai_generator

EVIDENCE = (
    "Engineers shipped a new relay protocol after three years of field "
    "testing across four continents and dozens of production networks.\n\n"
    "The maintainers described the rollout as cautious, citing earlier "
    "incidents where premature changes caused several days of downtime.\n\n"
    "Community feedback will decide whether the older relay mode is retired "
    "before the next major release is tagged later this spring."
)

STORY = {
    "article_id": str(uuid4()),
    "title": "Relay protocol ships",
    "url": "https://example.com/story",
    "publisher": "Fixture Press",
    "category": "technology_ai",
    "observed_urls": ["https://example.com/story"],
}

DRAFT = {
    "headline": "New relay protocol reaches production",
    "paragraphs": [
        "Engineers shipped the protocol after three years of testing "
        "across four continents and many production networks today.",
        "Maintainers called the rollout cautious and pointed to earlier "
        "incidents that caused multi-day downtime for several networks.",
    ],
    "sources": [{"url": "https://example.com/story", "label": "Fixture Press"}],
}


def transport_returning(response):
    calls = []

    def transport(payload, api_key):
        calls.append(payload)
        return response

    transport.calls = calls
    return transport


def ok_response(draft=None):
    return {
        "choices": [{"message": {"content": json.dumps(draft or DRAFT)}}],
        "usage": {"prompt_tokens": 800, "completion_tokens": 200},
    }


def generator_for(response, **kwargs):
    return OpenAIGenerator(
        "test-key", "gpt-5-mini", transport=transport_returning(response), **kwargs
    )


def test_generate_builds_payload_and_parses_draft():
    transport = transport_returning(ok_response())
    generator = OpenAIGenerator("test-key", "gpt-5-mini", transport=transport)
    output = generator.generate(STORY, EVIDENCE)

    assert output.headline == DRAFT["headline"]
    assert output.paragraphs == tuple(DRAFT["paragraphs"])
    assert output.sources[0]["url"] == "https://example.com/story"

    (payload,) = transport.calls
    assert payload["model"] == "gpt-5-mini"
    assert payload["response_format"]["json_schema"]["strict"] is True
    system, user = payload["messages"]
    assert system["role"] == "system" and "data" in system["content"]
    brief = json.loads(user["content"])
    assert brief["evidence"] == EVIDENCE
    assert brief["observed_urls"] == ["https://example.com/story"]


def test_usage_and_estimated_cost_accumulate():
    generator = generator_for(ok_response())
    generator.generate(STORY, EVIDENCE)
    generator.generate(STORY, EVIDENCE)
    assert generator.input_tokens == 1600
    assert generator.output_tokens == 400
    # gpt-5-mini: $0.25 in / $2.00 out per million tokens.
    expected = Decimal(1600) * Decimal("0.25") / 1_000_000 + Decimal(400) * Decimal(
        "2.00"
    ) / 1_000_000
    assert generator.estimated_cost_usd == expected


def test_malformed_model_output_raises_for_blocking():
    bad = {"choices": [{"message": {"content": "{ not json"}}], "usage": {}}
    generator = generator_for(bad)
    with pytest.raises(ValueError):
        generator.generate(STORY, EVIDENCE)

    missing = {"choices": [], "usage": {}}
    generator = generator_for(missing)
    with pytest.raises(ValueError):
        generator.generate(STORY, EVIDENCE)


def test_two_transport_failures_degrade_the_adapter():
    def dead(payload, api_key):
        dead.calls += 1
        raise ProviderError("http_500")

    dead.calls = 0
    generator = OpenAIGenerator("k", "gpt-5-mini", transport=dead)
    assert generator.generate(STORY, EVIDENCE) is None
    assert generator.generate(STORY, EVIDENCE) is None
    assert generator.generate(STORY, EVIDENCE) is None
    assert dead.calls == 2


def test_cost_cap_declines_remaining_stories():
    generator = generator_for(ok_response(), max_cost_usd=Decimal("0.0000001"))
    assert generator.generate(STORY, EVIDENCE) is not None
    assert generator.generate(STORY, EVIDENCE) is None


def test_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert openai_generator() is None


def test_from_env_uses_configured_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-nano")
    monkeypatch.setenv("OPENAI_MAX_COST_USD", "0.05")
    monkeypatch.setenv("OPENAI_INPUT_COST_PER_MTOK", "0.10")
    monkeypatch.setenv("OPENAI_OUTPUT_COST_PER_MTOK", "0.50")
    generator = openai_generator()
    assert generator.name == "openai/gpt-5-nano"
    assert generator.max_cost_usd == Decimal("0.05")
    assert generator.pricing == (Decimal("0.10"), Decimal("0.50"))


@pytest.fixture
def sessions():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_run_drafting_records_model_and_usage(sessions):
    with sessions() as session:
        source = Source(
            kind="rss",
            endpoint="https://example.com/feed",
            publisher="Fixture Press",
            category="technology_ai",
            approval="approved",
            licensing_note="Fixture",
        )
        session.add(source)
        session.flush()
        ingest = IngestionRun(source_id=source.id, status="succeeded")
        session.add(ingest)
        session.flush()
        article = Article(canonical_url=STORY["url"], title=STORY["title"])
        session.add(article)
        session.flush()
        session.add(
            ArticleSource(
                article_id=article.id,
                source_id=source.id,
                ingestion_run_id=ingest.id,
                external_id="1",
                source_url=STORY["url"],
                attributed_to="Fixture Press",
                published_at=datetime(2026, 11, 24, 12, tzinfo=UTC),
            )
        )
        session.flush()

        plan = {
            "edition_date": "2026-11-25",
            "coverage_floor_met": True,
            "stories": [STORY | {"article_id": article.id}],
        }
        transport = transport_returning(ok_response())
        generator = OpenAIGenerator("k", "gpt-5-mini", transport=transport)
        result = run_drafting(
            session,
            plan,
            fetch=lambda url: b"<html>ok</html>",
            extract=lambda body: EVIDENCE,
            generator=generator,
        )
        assert result["drafted"] == 1

        # The adapter saw the enriched observed_urls from the run.
        (payload,) = transport.calls
        assert json.loads(payload["messages"][1]["content"])["observed_urls"] == [
            STORY["url"]
        ]

        story = session.scalar(select(EditorialStory))
        assert story.headline == DRAFT["headline"]
        run = session.scalar(select(EditorialRun))
        assert run.model == "openai/gpt-5-mini"
        assert run.input_tokens == 800
        assert run.output_tokens == 200
        assert run.estimated_cost_usd > 0
