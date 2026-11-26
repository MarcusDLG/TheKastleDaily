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

Message bodies carry the EPUB as `application/epub+zip` with an
attempt-scoped `Message-ID` (`<delivery-id>.<attempt>@kastle-daily`)
recorded on the attempt for provider-side reconciliation — resubmits
never reuse a header downstream relays could deduplicate on. Error
codes store the SMTP status class and exception type only — recipient
addresses and server banners stay out of logs and diagnostics.

## Recipients

`delivery_recipients` is the recipient registry — one enabled row per
Kindle address. `KINDLE_ADDRESS` syncs additively into it on every
pipeline pass: env entries join automatically, but nothing is ever
deleted or re-enabled from env, so the admin surface is the single
path for removal. Each recipient gets an independent
(edition, destination) outbox row with its own attempt budget.

The admin dashboard's Recipients section adds addresses, toggles
enabled state, and requeues the newest delivery per address
("resend latest" flips the row to `pending`; the worker drain picks
it up on the next wake).

## Configuration

Delivery is inert until SMTP is configured; with no `SMTP_HOST` the drain
is a logged no-op and pending rows simply wait.

| Variable | Purpose |
|---|---|
| `SMTP_HOST`, `SMTP_PORT` | Submission endpoint; implicit TLS on 465, STARTTLS otherwise |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Auth and envelope sender — a dedicated account with an app-specific password |
| `KINDLE_ADDRESS` | Bootstrap list of `@kindle.com` receive address(es) — one, or comma-separated; additively synced into `delivery_recipients` each pass (removal is admin-owned) |

The sender address must be on each Amazon account's *Approved Personal
Document E-mail List* before the first live send — every recipient
account maintains its own list. `smtp_accepted` proves
provider submission only; Kindle library sync and device receipt are
separate acceptance evidence, and Amazon applies its own conversion and
attachment limits (~50 MB — editions run a few MB).
