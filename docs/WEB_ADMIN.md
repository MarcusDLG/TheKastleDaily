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
requires it to move — either onto the `/data` volume (seeded from the
baked default on first boot, minimal diff) or into a `settings` table
(the clean end-state). The volume move is the recommended first step.

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
- Localhost binding on the NAS; cloud deployments put it behind a
  tailnet or a basic-auth token — never bare-public.
- SQLite WAL + busy timeout are already set; rare, small admin writes
  alongside the worker are safe — no row-level locking needed.

## Phases

**Phase 1 — read-only dashboard.** Editions with status/SHA, drafting
runs with `error_detail` block reasons, feed health (last ingest status
per source, failure streaks), delivery state per edition. Zero write
risk; the `stories_blocked` mystery of 2026-11-25 becomes a page view.

**Phase 2 — feed management.** `sources` CRUD: add a feed (endpoint +
publisher + category), flip approval state (`pending`/`approved`/
`disabled`), retire dead endpoints. Writes are small, auditable rows.

**Phase 3 — editorial tuning.** Weights, target article count,
timezone and edition time against the relocated config; a restart-free
read path so the next edition picks it up.

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
