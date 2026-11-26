# Web administration (milestone spec)

A browser surface over the paper's existing state: run health,
blocked-story reasons, feed management, and editorial tuning. The
worker's security posture — no published ports, no listeners — is
preserved by making admin a separate, opt-in compose service.

## What the knobs actually are

| Control | Backing store | Mutable today? |
|---|---|---|
| Feed registry (endpoint, publisher, category, approval) | `sources` table | Yes — plain DB writes |
| Genres/splits, target count, timezone, edition time | `config/editorial.yaml` | No — baked into the image |
| Model/reasoning/cost caps, delivery, SMTP | `.env` | No — restart-scoped by design |
| Observability (runs, drafts, blocks, deliveries) | all tables | Read-only by nature |

Editorial config is the one structural gap: `schedule.py` and
`selection.py` read `config/editorial.yaml` from the image. Phase 3
requires it to move.

**Decision: volume-first.** `/data/editorial.yaml` — seeded from the
baked default on first boot, edited live by the admin surface, read on
every edition run. A `settings` table remains available as a later
normalization, not a prerequisite.

## Architecture

A second service in the same compose project:

```yaml
admin:
  image: ${KASTLE_APP_IMAGE:-kastle-daily:dev}
  command: [python, -m, app.admin]
  volumes: [kastle-data:/data]
  ports: ["127.0.0.1:${ADMIN_PORT:-8080}:8080"]
  profiles: [admin]
```

- Same image, different entrypoint — no second codebase.
- `profiles: [admin]` keeps the service off unless explicitly raised
  (`docker compose --profile admin up -d`), so the hardened default
  deployment is untouched.
- **Access policy — LAN/loopback only.** On the NAS the browser is on
  the same LAN; on a cloud host an SSH tunnel
  (`ssh -L 8080:localhost:8080`) reaches it with zero ingress change.
  An authenticated HTTPS portal is the optional step-up for
  AWS-deployed instances that want a stable URL — it is the only shape
  that opens inbound traffic, so it is never the default.
- SQLite WAL + busy timeout are already set; rare, small admin writes
  alongside the worker are safe — no row-level locking needed.

## Phases

**Phase 1 — read-only dashboard. Implemented.** Editions with
status/SHA, drafting runs with `error_detail` block reasons decoded,
feed health (last ingest status per source, failure streaks), delivery
state per edition, and 24h article stats. stdlib `http.server` — zero
new dependencies. The service binds the container's own interface
(narrower than a wildcard bind) and `docker compose config` publishes
`127.0.0.1:8080` only; raise it with
`docker compose --profile admin up -d admin`.

**Phase 2 — feed management. Implemented.** `sources` writes: add a
feed (endpoint + publisher + category + kind) and flip approval state
(`pending`/`approved`/`disabled`). HTTP Basic auth gates every route
except `/healthz` when `ADMIN_PASSWORD` is set; when unset the service
is read-only and every POST fails closed with 403. A per-process form
token protects writes against CSRF; categories validate against the
editorial weights; redirect-after-POST carries a flash line.

**Phase 3 — editorial tuning. Implemented.** `app/config.py` is the
volume-first layer: `<db dir>/editorial.yaml` seeds from the baked
default on first load; `schedule.py`/`selection.py` read it live —
saves take effect on the next edition, no restart. The admin form
edits target count, edition time, timezone and per-genre weights (sum
enforced at 100, non-negative integers, valid IANA zone, HH:MM time);
new genres are a name+weight row. `KASTLE_EDITORIAL_CONFIG` overrides
the path outright. Writes are validated before landing and saved
atomically (tmp + replace).

**Phase 4 — recipient management. Implemented.** `delivery_recipients`
is the recipient registry: `KINDLE_ADDRESS` syncs additively each
pipeline pass (new env entries join; nothing is removed or re-enabled
from env — disables are admin-owned). The admin Recipients section
lists addresses with each row's newest delivery state, adds
validated addresses, toggles enabled, and "resend latest" requeues a
recipient's newest delivery for the next drain. Bundled fix:
Message-IDs are now attempt-scoped (`<id>.<attempt>@kastle-daily`) so
resubmits can't be dropped by downstream deduplication.

## Framework decision point

Phase 1 is viable on stdlib `http.server` — zero new dependencies,
matching the codebase's posture (the OpenAI adapter uses raw
`http.client`). Once phases 2–3 need forms, CSRF tokens and auth, one
small dependency is the honest answer: starlette+uvicorn. Decide at
the phase-2 gate, not before.

## Security contract

- Never render `.env` values — admin displays "configured / unset",
  not contents.
- Write endpoints carry a form token from phase 2 onward.
- No admin write ever blocks the pipeline; a failed save surfaces on
  the page, the worker is unaffected.

## Test contract

Handlers are thin views over session queries — the same sessions
fixture pattern as the pipeline tests, plus HTTP-level tests over an
in-process server. Read-only phase asserts page contents from seeded
rows; write phases assert row transitions and that bad input never
reaches the DB.
