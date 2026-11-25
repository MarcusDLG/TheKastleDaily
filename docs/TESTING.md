# Quality gates
M00 regression: exact editorial configuration, static network isolation, worker hardening, scheduler DST behavior, security exception policy and migration/dedupe persistence. Run `python -m pytest`. CI lints, audits dependencies, validates Compose and builds amd64 image. Remote CI runs #9 and #10 passed.

Future gates: source timeout/malformed payload/duplicate/quota tests, attribution and injection resistance, ranking distribution, DST and concurrent-run idempotency, EPUB validation and Kindle receipt, SMTP uncertainty, authentication/authorization and CSRF, MCP scopes, backup restoration and NAS performance. Use fixtures and mocks, never production secrets in PR CI. Record results in PROJECT_STATUS. No merge without explicit approval.

## M00 acceptance evidence

Assessment date: 2026-11-24.

| Validation | Result |
|---|---|
| Initial application smoke acceptance | 10/10 passed |
| Database hardening acceptance | 11/11 passed |
| Automated regression | 73/73 passed |
| Ruff lint | Passed |
| Bandit application security | Zero findings |
| Production dependency audit | Zero known findings |
| Development dependency audit | Zero known findings |
| Gitleaks history scan | Zero findings |
| Gitleaks working-tree scan | Zero findings |
| Container security policy | Zero unaccepted blockers at assessment |
| Approved vulnerability exceptions | Register empty; policy validated with synthetic fixtures |
| Security JSON reports | 6/6 valid locally |
| Remote CI #9 | Passed |
| Remote CI #10 | Passed |
| Kindle physical-device acceptance | 31/31 passed |

Validated remote implementation commit: 21698b2.

Security regression coverage includes exception scope,
expiration, severity thresholds, malformed report cases,
container hardening and workflow permissions.

See SECURITY.md for security acceptance limitations.

## Future acceptance requirements

Formal EPUBCheck validation remains outstanding.

Live external API authentication, quotas, source licensing,
editorial generation cost and automated Kindle delivery
must be qualified during their implementation milestones.

NAS workload benchmarking must include concurrent existing
services and representative newspaper generation.

Database backup restoration must be tested as part of
POST-MVP-001.

GHCR publication and production deployment remain separately
authorized acceptance activities.

## Evidence management

Record automated test results, implementation commit,
assessment date, observed failures and residual risks.

Use synthetic fixtures and mock integrations in PR CI.

Do not use production credentials in automated PR tests.

Successful local execution does not replace remote CI
acceptance.

Successful SMTP submission does not replace Kindle
delivery acceptance.


## SQLite persistence acceptance

Run `bash scripts/database/acceptance.sh` in a development environment
(no Docker required). Against a temporary SQLite database it tests
repeated `alembic upgrade head`, `alembic check` drift detection, pilot
registration idempotency, cross-publisher deduplication, conditional
(304) re-fetch behavior and persistence across engine restarts.
CI and release validation run the same check alongside the M00 gates.
