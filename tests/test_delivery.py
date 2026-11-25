import smtplib
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.delivery import drain_outbox, ensure_delivery
from app.models import Base, Delivery, DeliveryAttempt, Edition

EDITION_DATE = date(2026, 11, 25)
NOW = datetime(2026, 11, 25, 12, tzinfo=UTC)
CONFIG = {"host": "smtp.test", "port": 465, "username": "u@test", "password": "p"}
DESTINATION = "reader@kindle.test"


@pytest.fixture
def sessions():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory, engine
    engine.dispose()


def seed_edition(session, tmp_path, content=b"epub-bytes"):
    path = tmp_path / "2026-11-25.epub"
    path.write_bytes(content)
    edition = Edition(
        edition_date=EDITION_DATE,
        status="validated",
        epub_key=str(path),
        epub_sha256=sha256(content).hexdigest(),
    )
    session.add(edition)
    session.flush()
    return edition


def enqueue(session, tmp_path, destination=DESTINATION):
    delivery, created = ensure_delivery(
        session, seed_edition(session, tmp_path), destination
    )
    delivery.available_at = NOW
    session.flush()
    return delivery, created


class FakeSMTP:
    """Records commands; raises the exception planned for each phase."""

    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def _phase(self, name, *args):
        self.calls.append((name,) + args)
        error = self.plan.get(name)
        if error is not None:
            raise error

    def ehlo_or_helo_if_needed(self):
        self.calls.append(("ehlo",))

    def login(self, username, password):
        self._phase("login", username)

    def mail(self, sender):
        self._phase("mail", sender)
        return (250, b"OK")

    def rcpt(self, recipient):
        self._phase("rcpt", recipient)
        return (250, b"OK")

    def data(self, payload):
        self._phase("data", payload)
        return (250, b"OK id=queue-1")

    def close(self):
        self.calls.append(("close",))


def factory_for(plan, seen=None):
    seen = [] if seen is None else seen

    def factory(config):
        client = FakeSMTP(plan)
        seen.append(client)
        return client

    factory.seen = seen
    return factory


def attempts(session, delivery_id):
    return session.scalars(
        select(DeliveryAttempt)
        .where(DeliveryAttempt.delivery_id == delivery_id)
        .order_by(DeliveryAttempt.attempt_number)
    ).all()


def test_ensure_delivery_is_idempotent(sessions, tmp_path):
    factory, _ = sessions
    with factory() as session:
        delivery, created = enqueue(session, tmp_path)
        assert created and delivery.status == "pending"
        assert len(delivery.epub_sha256) == 64
        again, created = ensure_delivery(
            session,
            session.scalar(select(Edition)),
            DESTINATION,
        )
        assert not created and again.id == delivery.id


def test_accepted_send_marks_delivery(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        delivery, _ = enqueue(session, tmp_path)
        delivery_id = delivery.id
        session.commit()

    result = drain_outbox(engine, config=CONFIG, factory=factory_for({}), now=NOW)
    assert result["smtp_accepted"] == 1

    with factory() as session:
        delivery = session.get(Delivery, delivery_id)
        assert delivery.status == "smtp_accepted"
        (attempt,) = attempts(session, delivery_id)
        assert attempt.outcome == "smtp_accepted"
        assert attempt.smtp_message_id == f"<{delivery_id}@kastle-daily>"

    again = drain_outbox(engine, config=CONFIG, factory=factory_for({}), now=NOW)
    assert again["claimed"] == 0


def test_message_carries_the_epub_attachment(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        enqueue(session, tmp_path)
        session.commit()

    sender = factory_for({})
    drain_outbox(engine, config=CONFIG, factory=sender, now=NOW)
    (data,) = [call for call in sender.seen[0].calls if call[0] == "data"]
    assert b'filename="2026-11-25.epub"' in data[1]
    assert b"ZXB1Yi1ieXRlcw==" in data[1]
    assert b"Content-Type: application/epub+zip" in data[1]


def test_transient_refusal_retries_with_backoff(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        delivery, _ = enqueue(session, tmp_path)
        delivery_id = delivery.id
        session.commit()

    plan = {"rcpt": smtplib.SMTPRecipientsRefused({DESTINATION: (450, b"busy")})}
    result = drain_outbox(engine, config=CONFIG, factory=factory_for(plan), now=NOW)
    assert result["retried"] == 1

    with factory() as session:
        delivery = session.get(Delivery, delivery_id)
        assert delivery.status == "pending"
        assert delivery.available_at == NOW + timedelta(minutes=5)
        (attempt,) = attempts(session, delivery_id)
        assert attempt.outcome == "failed"
        assert "RecipientsRefused" in attempt.error_code


def test_permanent_refusal_fails_immediately(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        delivery, _ = enqueue(session, tmp_path)
        delivery_id = delivery.id
        session.commit()

    plan = {"rcpt": smtplib.SMTPRecipientsRefused({DESTINATION: (550, b"no")})}
    result = drain_outbox(engine, config=CONFIG, factory=factory_for(plan), now=NOW)
    assert result["failed"] == 1
    with factory() as session:
        assert session.get(Delivery, delivery_id).status == "failed"


def test_disconnect_during_data_is_ambiguous_and_held(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        delivery, _ = enqueue(session, tmp_path)
        delivery_id = delivery.id
        session.commit()

    plan = {"data": smtplib.SMTPServerDisconnected("connection dropped")}
    result = drain_outbox(engine, config=CONFIG, factory=factory_for(plan), now=NOW)
    assert result["ambiguous"] == 1

    with factory() as session:
        delivery = session.get(Delivery, delivery_id)
        assert delivery.status == "ambiguous"
        (attempt,) = attempts(session, delivery_id)
        assert attempt.outcome == "ambiguous"

    # Ambiguous outcomes are not retried automatically.
    again = drain_outbox(engine, config=CONFIG, factory=factory_for({}), now=NOW)
    assert again["claimed"] == 0
    with factory() as session:
        assert len(attempts(session, delivery_id)) == 1


def test_disconnect_before_data_retries(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        enqueue(session, tmp_path)
        session.commit()

    plan = {"login": smtplib.SMTPServerDisconnected("connection dropped")}
    result = drain_outbox(engine, config=CONFIG, factory=factory_for(plan), now=NOW)
    assert result["retried"] == 1


def test_stale_sending_row_is_reconciled_as_ambiguous(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        delivery, _ = enqueue(session, tmp_path)
        delivery.status = "sending"
        session.add(DeliveryAttempt(delivery_id=delivery.id, attempt_number=1))
        delivery_id = delivery.id
        session.commit()

    result = drain_outbox(engine, config=CONFIG, factory=factory_for({}), now=NOW)
    assert result["reconciled"] == 1 and result["claimed"] == 0
    with factory() as session:
        assert session.get(Delivery, delivery_id).status == "ambiguous"
        assert attempts(session, delivery_id)[0].outcome == "ambiguous"


def test_attempt_budget_is_bounded(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        delivery, _ = enqueue(session, tmp_path)
        delivery_id = delivery.id
        session.commit()

    plan = {"mail": smtplib.SMTPSenderRefused(421, b"try later", "u@test")}
    moment = NOW
    for expected in range(1, 6):
        result = drain_outbox(
            engine, config=CONFIG, factory=factory_for(plan), now=moment
        )
        if expected < 5:
            assert result["retried"] == 1
            moment += timedelta(hours=2)
        else:
            assert result["failed"] == 1

    with factory() as session:
        delivery = session.get(Delivery, delivery_id)
        assert delivery.status == "failed"
        assert len(attempts(session, delivery_id)) == 5


def test_missing_artifact_fails_without_smtp(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        edition = Edition(
            edition_date=EDITION_DATE,
            status="validated",
            epub_key=str(tmp_path / "gone.epub"),
            epub_sha256=sha256(b"x").hexdigest(),
        )
        session.add(edition)
        session.flush()
        delivery, _ = ensure_delivery(session, edition, DESTINATION)
        delivery.available_at = NOW
        delivery_id = delivery.id
        session.commit()

    sender = factory_for({})
    result = drain_outbox(engine, config=CONFIG, factory=sender, now=NOW)
    assert result["failed"] == 1 and not sender.seen
    with factory() as session:
        assert session.get(Delivery, delivery_id).status == "failed"
        assert attempts(session, delivery_id)[0].error_code == "artifact_missing"


def test_checksum_mismatch_fails_closed(sessions, tmp_path):
    factory, engine = sessions
    with factory() as session:
        edition = seed_edition(session, tmp_path)
        edition.epub_sha256 = sha256(b"different").hexdigest()
        session.flush()
        delivery, _ = ensure_delivery(session, edition, DESTINATION)
        delivery.available_at = NOW
        delivery_id = delivery.id
        session.commit()

    sender = factory_for({})
    result = drain_outbox(engine, config=CONFIG, factory=sender, now=NOW)
    assert result["failed"] == 1 and not sender.seen
    with factory() as session:
        assert attempts(session, delivery_id)[0].error_code == "checksum_mismatch"


def test_unconfigured_smtp_leaves_outbox_alone(sessions, tmp_path, monkeypatch):
    factory, engine = sessions
    for variable in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD"):
        monkeypatch.delenv(variable, raising=False)
    with factory() as session:
        delivery, _ = enqueue(session, tmp_path)
        delivery_id = delivery.id
        session.commit()

    result = drain_outbox(engine, now=NOW)
    assert result["status"] == "skipped"
    assert result["reason"] == "smtp_not_configured"
    with factory() as session:
        assert session.get(Delivery, delivery_id).status == "pending"
        assert attempts(session, delivery_id) == []
