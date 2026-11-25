# Architecture
Target Synology DS220+, J4025, 18 GB RAM, Docker, Homebridge and Channels DVR. Linux amd64; verify DSM and Compose versions. Python 3.12, SQLite, Alembic, GitHub Actions and GHCR. No shared MuralBook database or credentials. Borrow clean migrations, secret-free CI, regression artifacts and concurrency cancellation.

Pipeline: approved sources -> normalization/deduplication -> evidence-backed ranking -> edition generation -> EPUB validation -> delivery outbox -> SMTP -> Kindle. Store run IDs, provenance, UTC timestamps, edition local date, delivery attempts and checksums. Unique edition/outbox keys; ambiguous SMTP acceptance requires review. Single worker, bounded retries and daily cost caps. America/New_York DST-safe edition key. Worker 1 GiB/0.75 CPU. Benchmark with DVR active. No local LLM. Backups are a copy of one database file. Production consumes approved GHCR digest; no automatic deploy.

## Simplified runtime

One long-running `worker` container runs the whole pipeline. It
sleeps most of the day, wakes every fifteen minutes, and once the
local edition time passes in America/New_York it executes the
pipeline for that calendar day: Alembic migrations, source
registration, RSS ingestion, editorial selection, and (as later
milestones land) drafting, EPUB rendering and delivery. One edition
per calendar day is guaranteed by the edition-date key and by the
worker's run-state file, with at most three attempts per edition.
`python -m app.schedule --once` runs the same pipeline immediately
for manual operation.

SQLite replaces PostgreSQL. The single database file lives on a
named volume at `/data/kastle.db`; backup is a file copy. WAL mode,
foreign keys, a busy timeout and normal synchronous mode are set on
every connection. There is one writer (the worker), so no row-level
locking is needed. Operational timestamps are stored as UTC.
There is no listening network service: the container publishes no
ports and the host port 5432 conflict is no longer relevant.

## Database model

The schema separates canonical articles from their source
observations, editorial runs from ranked stories and evidence, and
editions from delivery attempts. An edition date is unique and
derived by the scheduler in America/New_York. The outbox records a
destination key and EPUB checksum, with a unique edition/destination
pair and numbered attempts. An ambiguous submission is recorded
separately for later reconciliation.

Dashboard: deferred. The first milestones ship no web UI; run status
is visible in container logs and the run-state file. MCP: read-only
status first, later scoped writes requiring confirmation; shared
service layer, no unrestricted SQL or shell.

## M00 validated infrastructure baseline

The target host readiness assessment confirmed DSM 7.3.2,
Docker 24.0.2, Docker Compose 2.20.1, Btrfs and approximately
3 TiB of available storage.

The host is suitable for MVP implementation with conditions.

The host timezone is America/Bogota. Editorial scheduling
explicitly uses America/New_York rather than inheriting
the host timezone. Operational timestamps are stored in UTC.

Existing Homebridge and Channels DVR workloads must remain
unaffected. Production resource benchmarking remains required.

The host uses RAID 0 and has no independent backup capability.
Backup and disaster recovery remediation is tracked separately
under POST-MVP-001 with project owner approval.

## Validated security baseline

- Digest-pinned production container images.
- Hash-locked Python dependencies.
- Non-root application runtime.
- Read-only application root filesystem.
- No published ports and no network listeners.
- Automated Gitleaks, Bandit, pip-audit and Trivy gates.
- Explicit, expiring container vulnerability exceptions.
- Protected main branch and manual publication workflow.

See SECURITY.md for implementation details and residual risks.

## Editorial configuration

Target: one daily edition containing approximately 15 articles.

| Section | Weight | Covers |
|---|---:|---|
| Motorsport culture and strategy | 18% | NASCAR, F1, endurance (WEC/IMSA) |
| Sim racing | 10% | iRacing, leagues, hardware |
| Technology and AI | 16% | AI, automation, emerging tech |
| Software engineering | 10% | architecture, QE, security, release |
| Maker and fabrication | 12% | 3D printing, electronics, DIY/home |
| Radio and off-grid comms | 6% | Meshtastic/MeshCore, LoRa, amateur |
| Space exploration | 8% | SpaceX/Starship, aerospace |
| Culinary arts | 6% | Japanese cuisine, smoking/grilling |
| Visual craft | 4% | photography, drones, design/liveries |
| Home lab and self-hosting | 6% | NAS, Docker, automation, networking |
| Life systems | 4% | gardening, aquariums, running, learning |

Weights are editorial allocation targets, not a requirement
to achieve fractional article counts within each edition.

The implementation must define deterministic allocation and
rounding behavior while preserving the configured priorities.

## Integration architecture decisions

RSS is the primary ingestion mechanism.

YouTube metadata supplements RSS. Unauthorized video
transcripts and downloads are not required.

OpenAI API provides structured editorial generation through
an independently testable adapter.

The physical Kindle proof of concept validated EPUB as a
viable reading format. Automated delivery remains a separate
integration qualification task.

MCP is not required for the initial newspaper MVP. The
administrative service layer should support later MCP access
without introducing direct database or shell access.

Instagram is excluded.
