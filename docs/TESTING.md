# Quality gates
M00 regression: health contract, disabled admin/docs endpoints, exact editorial configuration and static network isolation. Run `python -m pytest`. CI lints, audits dependencies, validates Compose and builds amd64 image. Remote results pending.

Future gates: fresh PostgreSQL migrations and upgrades, source timeout/malformed payload/duplicate/quota tests, attribution and injection resistance, ranking distribution, DST and concurrent-run idempotency, EPUB validation and Kindle receipt, SMTP uncertainty, authentication/authorization and CSRF, MCP scopes, backup restoration and NAS performance. Use fixtures and mocks, never production secrets in PR CI. Record results in PROJECT_STATUS. No merge without explicit approval.
