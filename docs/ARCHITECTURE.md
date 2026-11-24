# Architecture
Target Synology DS220+, J4025, 18 GB RAM, Docker, Homebridge and Channels DVR. Linux amd64; verify DSM and Compose versions. Python 3.12/FastAPI, PostgreSQL 17, Alembic, GitHub Actions and GHCR. No shared MuralBook database or credentials. Borrow clean migrations, secret-free CI, regression artifacts and concurrency cancellation.

Pipeline: approved sources -> normalization/deduplication -> evidence-backed ranking -> edition generation -> EPUB validation -> delivery outbox -> SMTP -> Kindle. Store run IDs, provenance, UTC timestamps, edition local date, delivery attempts and checksums. Unique edition/outbox keys; ambiguous SMTP acceptance requires review. Single worker, bounded retries and daily cost caps. America/New_York DST-safe edition key. DB 1 GiB/0.5 CPU, API 512 MiB/0.25 CPU, future worker 1 GiB/0.75 CPU. Benchmark with DVR active. No local LLM. Backups separate. Production consumes approved GHCR digest; no automatic deploy.

Dashboard: authenticated run status, sources, weights, previews, logs, retry, cost and delivery history. MCP: read-only status first, later scoped writes requiring confirmation; shared service layer, no unrestricted SQL or shell. Evaluate secure tunnel before public reverse proxy. No admin endpoints in M00.

## M02 database architecture

PostgreSQL runs on the internal Compose network. The API connects to it
as `kastle_app`. One-shot provisioning uses `kastle_bootstrap`, and Alembic
uses `kastle_migrator` to own and version the `newspaper` schema. See the
[M02 runbook](M02.md) for role permissions and upgrade steps.

The schema separates canonical articles from their source observations,
editorial runs from ranked stories and evidence, and editions from
delivery attempts. An edition date is unique and derived by the future
scheduler in America/New_York. Operational timestamps use PostgreSQL
`timestamptz` with UTC sessions. The outbox records a destination key and
EPUB checksum, with a unique edition/destination pair and numbered
attempts. An ambiguous submission is recorded separately for later
reconciliation.

## M00 validated infrastructure baseline

The target host readiness assessment confirmed DSM 7.3.2,
Docker 24.0.2, Docker Compose 2.20.1, Btrfs and approximately
3 TiB of available storage.

The host is suitable for MVP implementation with conditions.

The existing PostgreSQL host port 5432 is occupied. The
application database must remain isolated on its internal
Docker network without publishing that port.

The host timezone is America/Bogota. Editorial scheduling
must explicitly use America/New_York rather than inheriting
the host timezone. Store operational timestamps in UTC.

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
- SCRAM-SHA-256 database authentication for fresh volumes.
- PostgreSQL data checksums for fresh volumes.
- Authenticated database health checks.
- Automated Gitleaks, Bandit, pip-audit and Trivy gates.
- Explicit, expiring container vulnerability exceptions.
- Protected main branch and manual publication workflow.

See SECURITY.md for implementation details and residual risks.

## Editorial configuration

Target: one daily edition containing approximately 15 articles.

| Category | Weight |
|---|---:|
| Formula 1 | 19% |
| NASCAR | 19% |
| Technology and AI | 24% |
| Software engineering | 14% |
| Sim racing | 14% |
| Maker and radio technology | 10% |
| Other interests | 0% |

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
