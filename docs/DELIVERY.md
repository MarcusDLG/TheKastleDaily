# Delivery worker

The delivery stage submits validated editions to the configured Kindle
address over SMTP. It runs inside the worker: editions enqueue a
persistent outbox row, and due deliveries are drained on every scheduler
wake, so retries continue between edition runs.

## Outbox

`deliveries` holds one row per edition/destination pair — a unique key
that prevents duplicate submissions — carrying the validated EPUB's
SHA-256. Before every send the artifact file is rehashed and compared
against the outbox checksum; a mismatch or a missing file fails the
delivery without touching the network.

Enqueueing is get-or-create, so rerunning a pipeline pass never
duplicates a row. Only the edition the pass just built enqueues — the
outbox does not backfill historical editions.

## Attempt lifecycle

`delivery_attempts` records numbered attempts. Claiming moves a due
`pending` delivery to `sending` and records a `started` attempt; the
outcome then lands on the same row:

| Outcome | Delivery status | Retry |
|---|---|---|
| Server accepts the message | `smtp_accepted` | Never resubmitted |
| Refusal or disconnect before DATA | `pending` | Backoff 5/10/20/40/60 min, five attempts max, then `failed` |
| Explicit permanent refusal (5xx) | `failed` | None |
| Transport lost during or after DATA | `ambiguous` | Held for owner reconciliation — the server may have accepted |
| Crash leaving a `sending` row | `ambiguous` | Reconciled on the next drain, never silently resent |

The `ambiguous` state exists because an SMTP disconnect has an unknowable
result: the message may already be queued at the provider. Automatic
retries would risk a duplicate library item, so the row waits for a
manual decision instead.

Message bodies carry the EPUB as `application/epub+zip` with a
deterministic `Message-ID` (`<delivery-id>@kastle-daily`) recorded on the
attempt for provider-side reconciliation. Error codes store the SMTP
status class and exception type only — recipient addresses and server
banners stay out of logs and diagnostics.

## Configuration

Delivery is inert until SMTP is configured; with no `SMTP_HOST` the drain
is a logged no-op and pending rows simply wait.

| Variable | Purpose |
|---|---|
| `SMTP_HOST`, `SMTP_PORT` | Submission endpoint; implicit TLS on 465, STARTTLS otherwise |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Auth and envelope sender — a dedicated account with an app-specific password |
| `KINDLE_ADDRESS` | The `@kindle.com` receive address(es) — one, or a comma-separated list; each becomes an outbox `destination_key` with its own delivery row |

The sender address must be on each Amazon account's *Approved Personal
Document E-mail List* before the first live send — every recipient
account maintains its own list. `smtp_accepted` proves
provider submission only; Kindle library sync and device receipt are
separate acceptance evidence, and Amazon applies its own conversion and
attachment limits (~50 MB — editions run a few MB).
