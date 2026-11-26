"""Deliver validated editions to the configured Kindle addresses over SMTP.

The deliveries table is a persistent outbox: one row per edition and
destination pair carrying the validated EPUB checksum, plus numbered
attempts. Enqueueing is idempotent; claiming marks a due pending
delivery `sending`; and every send outcome lands on the attempt record:

- The server accepts the message: `smtp_accepted`, and the pair is
  never submitted again.
- A refusal or disconnect before DATA reaches the server: `pending`
  again with a bounded backoff, until the attempt budget is spent and
  the delivery is `failed`. Permanent refusals (5xx, authentication)
  fail immediately.
- Transport lost during or after DATA: `ambiguous` — the server may
  have accepted, so automatic retries are unsafe. A crashed pass that
  leaves a `sending` row is reconciled the same way on the next drain.

The artifact's SHA-256 is verified against the outbox checksum before
every send, so a corrupted or replaced file fails closed. Nothing is
sent without explicit SMTP configuration, and recipient addresses and
server banners stay out of error codes and logs.
"""

import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from hashlib import sha256
from pathlib import Path
from ssl import create_default_context

from sqlalchemy import func, select

from app.models import Delivery, DeliveryAttempt, Edition
from app.secrets import secret

TIMEOUT = 15
MAX_ATTEMPTS = 5
BACKOFF_MINUTES = (5, 10, 20, 40, 60)


def smtp_config() -> dict | None:
    """SMTP settings from the environment; None when delivery is off."""
    host = (secret("SMTP_HOST") or "").strip()
    if not host:
        return None
    return {
        "host": host,
        "port": int(secret("SMTP_PORT") or 465),
        "username": (secret("SMTP_USERNAME") or "").strip(),
        "password": secret("SMTP_PASSWORD") or "",
    }


def destinations() -> list[str]:
    """The Kindle receive addresses — a comma-separated list, or empty."""
    raw = secret("KINDLE_ADDRESS") or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def smtp_client(config):
    """Implicit TLS on port 465, STARTTLS upgrade otherwise."""
    context = create_default_context()
    if config["port"] == 465:
        return smtplib.SMTP_SSL(
            config["host"], config["port"], timeout=TIMEOUT, context=context
        )
    client = smtplib.SMTP(config["host"], config["port"], timeout=TIMEOUT)
    client.starttls(context=context)
    return client


def ensure_delivery(session, edition, destination_key):
    """Get-or-create the outbox row for an edition/destination pair."""
    delivery = session.scalar(
        select(Delivery).where(
            Delivery.edition_id == edition.id,
            Delivery.destination_key == destination_key,
        )
    )
    if delivery is not None:
        return delivery, False
    delivery = Delivery(
        edition_id=edition.id,
        destination_key=destination_key,
        epub_sha256=edition.epub_sha256,
    )
    session.add(delivery)
    session.flush()
    return delivery, True


def build_message(delivery, edition_date, filename, payload, sender):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = delivery.destination_key
    message["Date"] = format_datetime(datetime.now(UTC))
    message["Message-ID"] = f"<{delivery.id}@kastle-daily>"
    message["Subject"] = f"The Kastle Daily — {edition_date.isoformat()}"
    message.set_content("Automated edition delivery.")
    message.add_attachment(
        payload,
        maintype="application",
        subtype="epub+zip",
        filename=filename,
    )
    return message


def _error_code(error) -> str:
    code = getattr(error, "smtp_code", None)
    return f"{type(error).__name__}:{code}" if code else type(error).__name__


def _send(config, factory, delivery, edition):
    """One submission. Returns (outcome, error_code, message_id)."""
    try:
        payload = Path(edition.epub_key).read_bytes()
    except OSError:
        return "failed", "artifact_missing", None
    if sha256(payload).hexdigest() != delivery.epub_sha256:
        return "failed", "checksum_mismatch", None
    sender = config["username"] or "kastle-daily"
    message = build_message(
        delivery, edition.edition_date, Path(edition.epub_key).name, payload, sender
    )

    client = None
    phase = "connect"
    try:
        client = factory(config)
        client.ehlo_or_helo_if_needed()
        phase = "authenticate"
        if config["username"]:
            client.login(config["username"], config["password"])
        phase = "mail"
        client.mail(sender)
        client.rcpt(delivery.destination_key)
        phase = "data"
        client.data(message.as_bytes())
        return "smtp_accepted", None, message["Message-ID"]
    except smtplib.SMTPRecipientsRefused as error:
        codes = {code for code, _ in error.recipients.values()}
        permanent = bool(codes) and all(code >= 500 for code in codes)
        return "failed" if permanent else "transient", _error_code(error), None
    except smtplib.SMTPResponseException as error:
        # An explicit response: classify by code. During DATA it is a
        # refusal, not an ambiguity — the server told us it declined.
        permanent = error.smtp_code >= 500
        return "failed" if permanent else "transient", _error_code(error), None
    except smtplib.SMTPNotSupportedError as error:
        return "failed", _error_code(error), None
    except (
        smtplib.SMTPException,
        TimeoutError,
        ConnectionError,
        OSError,
    ) as error:
        if phase == "data":
            # The wire dropped with the payload possibly delivered.
            return "ambiguous", _error_code(error), None
        return "transient", _error_code(error), None
    finally:
        if client is not None:
            try:
                client.close()
            except (smtplib.SMTPException, OSError):
                pass


def _backoff(attempt_number) -> timedelta:
    index = min(attempt_number, len(BACKOFF_MINUTES)) - 1
    return timedelta(minutes=BACKOFF_MINUTES[index])


def drain_outbox(engine, *, config=None, factory=smtp_client, now=None):
    """Reconcile stale claims, then submit every due pending delivery."""
    from app.database import session_factory

    config = smtp_config() if config is None else config
    now = now or datetime.now(UTC)
    sessions = session_factory(engine)
    result = {
        "reconciled": 0,
        "claimed": 0,
        "smtp_accepted": 0,
        "retried": 0,
        "failed": 0,
        "ambiguous": 0,
    }

    # A `sending` row can only be a crash leftover: there is one worker,
    # and every live send finalizes its delivery before returning. The
    # server may have accepted, so mark it ambiguous rather than resend.
    with sessions() as session:
        stale = session.scalars(
            select(Delivery).where(Delivery.status == "sending")
        ).all()
        for delivery in stale:
            delivery.status = "ambiguous"
            open_attempt = session.scalar(
                select(DeliveryAttempt).where(
                    DeliveryAttempt.delivery_id == delivery.id,
                    DeliveryAttempt.outcome == "started",
                )
            )
            if open_attempt is not None:
                open_attempt.outcome = "ambiguous"
                open_attempt.finished_at = now
                open_attempt.error_code = "reconciled_after_crash"
        result["reconciled"] = len(stale)
        session.commit()

    if config is None:
        result["status"] = "skipped"
        result["reason"] = "smtp_not_configured"
        return result

    while True:
        with sessions() as session:
            delivery = session.scalar(
                select(Delivery)
                .where(
                    Delivery.status == "pending",
                    Delivery.available_at <= now,
                )
                .order_by(Delivery.available_at)
                .limit(1)
            )
            if delivery is None:
                break
            attempt_number = (
                session.scalar(
                    select(func.count(DeliveryAttempt.id)).where(
                        DeliveryAttempt.delivery_id == delivery.id
                    )
                )
                + 1
            )
            attempt = DeliveryAttempt(
                delivery_id=delivery.id, attempt_number=attempt_number
            )
            session.add(attempt)
            delivery.status = "sending"
            session.commit()
            delivery_id = delivery.id
        result["claimed"] += 1

        with sessions() as session:
            delivery = session.get(Delivery, delivery_id)
            edition = session.get(Edition, delivery.edition_id)
            outcome, error, message_id = _send(config, factory, delivery, edition)
            attempt = session.scalar(
                select(DeliveryAttempt).where(
                    DeliveryAttempt.delivery_id == delivery.id,
                    DeliveryAttempt.attempt_number == attempt_number,
                )
            )
            attempt.finished_at = datetime.now(UTC)
            attempt.error_code = error
            attempt.smtp_message_id = message_id
            if outcome == "smtp_accepted":
                attempt.outcome = "smtp_accepted"
                delivery.status = "smtp_accepted"
                result["smtp_accepted"] += 1
            elif outcome == "ambiguous":
                attempt.outcome = "ambiguous"
                delivery.status = "ambiguous"
                result["ambiguous"] += 1
            elif outcome == "failed" or attempt_number >= MAX_ATTEMPTS:
                attempt.outcome = "failed"
                delivery.status = "failed"
                result["failed"] += 1
            else:
                attempt.outcome = "failed"
                delivery.status = "pending"
                delivery.available_at = now + _backoff(attempt_number)
                result["retried"] += 1
            session.commit()

    result["status"] = "drained"
    return result


def drain_safely(engine=None) -> dict:
    """Outbox drain that can never take the worker loop down."""
    from app.database import database_engine

    own = engine is None
    if own:
        engine = database_engine()
    try:
        return drain_outbox(engine)
    except Exception as error:
        return {"status": "error", "error": type(error).__name__}
    finally:
        if own:
            engine.dispose()
