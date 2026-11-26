# The Kastle Daily | Project Status

## M00 consolidated acceptance

Assessment date: 2026-11-24.

Status: Accepted and squash merged through PR #1 at b0acc98.

Repository: MarcusDLG/TheKastleDaily
Pull request: #1

## Initialization workstreams

| Workstream | Disposition |
|---|---|
| M00 initialization | Scaffold implemented and validated |
| M00-A Security hardening | Complete with documented residual risks |
| M00-B Synology readiness | Passed with conditions |
| M00-C EPUB proof of concept | Physical-device acceptance passed |
| M00-D External integration feasibility | Feasibility assessment complete |
| Consolidated M00 acceptance | Accepted and squash merged |

## M00-A Security hardening

- Automated regression: 73/73 passed after the SQLite simplification.
- Initial application acceptance: 10/10 passed.
- Database hardening acceptance: 11/11 passed.
- Gitleaks credential findings: zero.
- Bandit application findings: zero.
- Python dependency audit findings: zero.
- Unaccepted container blockers: zero at assessment.
- Approved container vulnerability exceptions: 27 at M00; register now empty (PostgreSQL image removed).
- Security reports: 6/6 validated locally.
- Remote CI runs #9 and #10 passed.
- Validated implementation commit: 21698b2.
- Security acceptance documentation commit: 21b40a6.

See SECURITY.md for detailed controls, exceptions and residual risks.

## M00-B Synology readiness

Host: DigisaurNAS, Synology DS220+.

- DSM 7.3.2 build 86009.
- Intel Celeron J4025, two cores.
- 18 GB installed RAM.
- Docker 24.0.2.
- Docker Compose 2.20.1.
- Btrfs filesystem.
- Approximately 3 TiB available storage at assessment.
- Existing Homebridge and Channels DVR services.
- Existing RAID 0 storage configuration.
- Healthy time synchronization.
- Host PostgreSQL port 5432 already occupied.

Readiness disposition: suitable for MVP implementation with
documented conditions.

No independent backup capability exists.

The project owner approved deferring backup and disaster recovery
remediation until after MVP stand-up under POST-MVP-001.

Production workload benchmarking remains outstanding.

## M00-C EPUB proof of concept

- Sample edition containing 15 fictional articles.
- Kindle Paperwhite, 11th generation.
- Firmware: 5.19.2.
- Physical-device acceptance: 31/31 passed.
- Failed or blocked manual tests: zero.
- EPUB upload and Kindle synchronization validated.
- Typography, navigation, images, grayscale contrast,
  offline reading and reading experience validated.

Formal EPUBCheck validation remains outstanding.

Automated email delivery was not validated by the manual
Send to Kindle proof of concept.

## M00-D External integration feasibility

Feasibility conclusions:

- RSS is the primary source ingestion mechanism.
- YouTube Data API provides supplemental video metadata.
- Unauthorized transcript retrieval is not a dependency.
- OpenAI API supports structured editorial generation.
- EPUB delivery through approved-sender email is conditional
  on live integration validation.
- MCP is feasible as a later administrative integration.
- Instagram is excluded.

No API credentials were created, services purchased or
production integrations deployed during the assessment.

See INTEGRATIONS.md for implementation constraints.

## Outstanding work

| ID | Requirement | Required disposition |
|---|---|---|
| POST-MVP-001 | NAS backup and disaster recovery | Owner-approved post-MVP remediation |
| NAS-SEC-TLS | TLS or tailnet for admin service | Open — Basic auth is cleartext on LAN |
| NAS-SEC-DIGEST | Digest-pinned image pulls on NAS | Open — `:latest` is a mutable tag |
| M00-EXC-001 | PostgreSQL libxml2 exception | Closed: PostgreSQL image removed |
| M00-EXC-002 | PostgreSQL gosu exceptions | Closed: PostgreSQL image removed |
| M00-GOV-003 | GHCR access verification | First authorized publication |
| M00-C-OPEN | Formal EPUBCheck validation | Before production EPUB delivery |
| M00-D-OPEN | Live integration qualification | During relevant implementation milestones |
| NAS-PERF | Concurrent workload benchmarking | Before production acceptance |
| NAS-DB | Existing database volume hardening | Obsolete: no database volume is reused |
| PLAN-REV4 | Full Master Execution Plan reconciliation | Outstanding |

Additional security findings are maintained in SECURITY.md.

## Live integration qualification

2026-11-25: first automated end-to-end delivery. A live pipeline run
selected 13 stories (coverage floor met), drafted via the template
generator, rendered and validated the edition (sha256 `c63246dc…`), and
submitted it through the dedicated Gmail sender — `smtp_accepted` on
attempt 1. Amazon converted and synced the document, and it arrived on
the Kindle Paperwhite navigable end to end. Provider submission,
library sync and device receipt are evidenced separately as required.
OpenAI generation and NAS deployment remain unqualified.

## Development roadmap

| Workstream | Status |
|---|---|
| M00 initialization and feasibility | Accepted |
| M02 persistence and migrations | Superseded by the SQLite worker runtime |
| Source ingestion | Implemented (RSS and Atom, expanded registry) |
| Editorial engine | In progress (selection, evidence drafting with story photo acquisition, OpenAI provider adapter and edition build implemented; model generation exercised in preview runs — adapter bounds reasoning spend and repair-retries malformed output) |
| EPUB generation and delivery | Implemented (renderer, generated masthead cover, validation, pipeline build and SMTP outbox; live Send-to-Kindle qualified end to end) |
| Scheduling and observability | Implemented (worker loop and health heartbeat; 30-day retention prunes rows and artifacts each pass) |
| Web administration | Implemented (dashboard, feed management, editorial tuning on volume-first config) — [WEB_ADMIN.md](WEB_ADMIN.md) |
| Cloud deployment | Specced ([CLOUD_DEPLOY.md](CLOUD_DEPLOY.md)) — friend/AWS paths; GHCR image public, DEPLOY.md published, acceptance matrix pending |
| Secrets management | Implemented — env backend default, AWS Secrets Manager backend ([SECRETS.md](SECRETS.md)) |
| MCP integration | Planned |
| NAS deployment and recovery | Deployed (worker live on DS220+, first unattended edition delivered); backup/DR pending POST-MVP-001 |

Milestone numbering beyond M02 remains provisional until the
full Master Execution Plan Revision 4.0 is reconciled.

## Authorization

No merge, GHCR publication or NAS deployment has been authorized.

Explicit project owner approval is required.

MuralBook was inspected read-only for reusable architectural
patterns. No MuralBook resources or credentials are shared.

Devin implements the core loop in reviewable milestone PRs; the project owner reviews and merges.
