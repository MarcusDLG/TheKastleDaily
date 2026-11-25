# The Kastle Daily | Security Architecture

## Document control

- Milestone: M00-A
- Assessment date: 2026-11-24
- Status: Local and remote CI security acceptance passed
- Remote CI acceptance: Passed (CI #9 and #10)
- Production deployment: Not authorized

## 1. Security principles

- Treat the Synology NAS as internet-connected infrastructure.
- Do not modify existing NAS services.
- Run no listening network service; publish no ports.
- Keep the database file on local volume storage only.
- Require authenticated access before exposing administrative interfaces.
- Apply least privilege to containers, database roles and credentials.
- Keep secrets outside source control.
- Treat external content as untrusted.
- Require explicit authorization before publication or deployment.

## 2. Container security

The application container uses:

- Digest-pinned Python 3.12 base image.
- Non-root runtime UID 10001.
- Read-only root filesystem.
- Dropped Linux capabilities.
- No-new-privileges enforcement.
- Explicit CPU and memory limits.
- Hash-verified, wheel-only Python dependency installation.
- No development dependencies in the production image.

Persistence uses:

- SQLite in a single file on a named volume (`/data/kastle.db`).
- WAL journal mode, foreign keys enforced, bounded busy timeout.
- One writer (the worker container); no network listener of any kind.
- No database credentials exist: file-system permissions are the
  access boundary, and the container runs non-root with a read-only
  root filesystem.

The PostgreSQL role model (bootstrap/migrator/runtime logins) was
removed with the database engine. See [Architecture](ARCHITECTURE.md).

## 3. Software supply chain

- Production and development dependency inputs are maintained
  separately.
- Transitive dependencies are locked with SHA-256 hashes.
- Installation requires matching hashes and binary wheels.
- Production and development dependencies are audited separately.
- GitHub Actions are pinned to full commit SHAs.
- Checkout credentials are not persisted.
- Dependabot configuration covers Python, Docker and GitHub Actions.
- Production container images are built for Linux AMD64.

## 4. Automated security controls

### Gitleaks

- Version: 8.30.1.
- Digest-pinned scanner container.
- Scans locally available Git history and eligible working-tree files.
- Excludes ignored local files from the working-tree snapshot.
- Includes tracked files even when their names match ignore rules.
- Uses an isolated history clone.
- Uses an externally generated trusted scanner configuration.
- Rejects unauthorized Gitleaks configuration and ignore files.
- Disables inline finding suppressions.
- Redacts detected credentials.
- Produces JSON reports.
- Findings, execution failures and invalid reports block acceptance.

### Bandit

- Version: 1.9.4.
- Installed through the hash-locked development dependencies.
- Scans application Python source.
- All finding severities are blocking.
- Inline nosec suppressions are ignored.
- Produces JSON reports in CI.

### pip-audit

- Audits production and development dependency locks.
- Known dependency vulnerabilities block acceptance.
- Scanner execution failures block acceptance.

### Trivy

- Version: 0.76.2.
- Digest-pinned scanner container.
- Downloads vulnerability data before offline image scanning.
- Scans the exported AMD64 application image archive.
- Does not require access to the Docker socket.
- Evaluates findings using the repository security policy.
- Produces raw vulnerability and evaluated policy JSON reports.

## 5. Vulnerability acceptance policy

| Finding | Required disposition |
|---|---|
| Exposed credential | Block |
| Insecure application code | Block |
| Vulnerable Python dependency | Block |
| Critical container vulnerability | Block unless explicitly accepted |
| High container vulnerability with available fix | Block unless explicitly accepted |
| High container vulnerability without available fix | Report and track |
| Medium, low or unknown severity | Report |
| Scanner execution failure | Block |
| Expired security exception | Block |

Security exceptions require explicit project owner approval,
documented justification, compensating controls and expiration.

The machine-readable exception register is maintained at:

config/security/exceptions.json

Exceptions are scoped by image identity, vulnerability identifier,
package, installed version, severity and scanner target.

Exception dates use UTC. The expiration date is the first date
on which an exception is invalid.

No blanket vulnerability suppression is permitted.

## 6. Approved security exceptions

**Closed.** Both exceptions below applied only to the PostgreSQL image,
which is no longer part of the deployment. The exception register is
empty; the evaluator policy is regression-tested with synthetic entries.
The original text is retained for the record.

Approved by the project owner on 2026-11-24.

Expiration: 2026-12-24 UTC.

### M00-EXC-001

- Component: PostgreSQL container, libxml2.
- Vulnerability: CVE-2026-6653.
- Severity: Critical.
- Fixed version: None listed in the assessed scan.
- Disposition: Temporary risk acceptance.
- Controls: Database network isolation, least privilege and
  prohibition on passing untrusted XML to PostgreSQL XML functions.

### M00-EXC-002

- Component: PostgreSQL container, embedded gosu Go standard library.
- Findings: One critical and 25 high.
- Disposition: Temporary risk acceptance.
- Controls: Official digest-pinned image, database network isolation
  and no network service exposure for gosu.
- Individual vulnerable code reachability has not been established.
- Exact vulnerability identifiers and versions are recorded in
  the exception register.

Both exceptions apply only to the approved PostgreSQL image.
They do not authorize new vulnerabilities or future image versions.

Review upstream remediation before expiration. Remove exceptions
when remediation is available and validated. Renewal requires
explicit approval.

## 7. CI/CD enforcement

The CI workflow performs:

- Credential scanning.
- Hash-verified dependency installation.
- Linting.
- Application security scanning.
- Automated regression testing.
- Production and development dependency auditing.
- Docker Compose validation.
- AMD64 production image building.
- Container vulnerability scanning and policy evaluation.

The release workflow:

- Requires manual workflow dispatch.
- Restricts execution to main.
- Requires successful release validation.
- Uses the approved-release environment.
- Scans the actual release build before registry authentication.
- Grants package write permission only to the publishing job.
- Publishes commit-specific image tags.

Security and regression reports are configured for 14-day
GitHub Actions artifact retention.

No automatic production deployment is configured.

## 8. Repository governance

Configured controls include:

- Protected main branch ruleset.
- Pull request requirement.
- Required CI checks.
- Conversation resolution.
- Up-to-date branch requirement.
- Squash-only merging.
- Linear history.
- Force-push and branch-deletion restrictions.
- Restricted GitHub Actions allowlist.
- Full-length Action SHA enforcement.
- Read-only default workflow permissions.

Independent approval is limited by the solo-maintainer configuration.

Native secret scanning and required environment reviewers were
not available in the assessed repository configuration.

Gitleaks provides compensating credential detection, but does
not prevent the initial push of a credential.

Manual release authorization remains mandatory.

## 9. Local acceptance evidence

Assessment date: 2026-11-24.

| Validation | Result |
|---|---|
| Initial application acceptance | 10/10 passed |
| Database hardening acceptance | 11/11 passed |
| Consolidated automated regression | 71/71 passed |
| Application security findings | 0 |
| Production dependency vulnerabilities | 0 |
| Development dependency vulnerabilities | 0 |
| Gitleaks history findings | 0 |
| Gitleaks working-tree findings | 0 |
| Approved PostgreSQL findings matched | 27/27 (historical; register now empty) |
| Unaccepted container blockers | 0 |
| Expired exceptions | 0 |
| Security JSON reports | 6/6 valid |
| Repository whitespace validation | Passed |

Container findings at the time of assessment:

| Category | Application | PostgreSQL |
|---|---:|---:|
| Accepted blocking findings | 0 | 27 |
| Unaccepted blocking findings | 0 | 0 |
| High findings without listed fixes | 53 | 72 |
| Other reported findings | 175 | 335 |
| Expired exceptions | 0 | 0 |

Counts represent package-level findings, not necessarily unique CVEs.
Results are time-dependent and must be reassessed by subsequent scans.

## 10. Findings and outstanding risks

| ID | Description | Disposition |
|---|---|---|
| M00-SEC-001 | Database local trust authentication | Remediated for fresh volumes |
| M00-REL-001 | Database checksums disabled | Remediated for fresh volumes |
| M00-SEC-002 | Vulnerable development dependency | Remediated |
| M00-SEC-003 | AWS synthetic credential detection discrepancy | Open; review deferred recommendation |
| M00-SEC-004 | Scanner configuration bypass | Local mitigation and remote CI execution validated |
| M00-SEC-005 | Application high findings without fixes | Monitor |
| M00-SEC-006 | PostgreSQL OS vulnerabilities | Closed: PostgreSQL image removed |
| M00-SEC-007 | Embedded gosu vulnerabilities | Closed: PostgreSQL image removed |
| M00-QA-001 | Synthetic credential fixture regression | Resolved for general acceptance |
| M00-QA-002 | Snapshot scan inconsistency | Mitigated; root cause unconfirmed |
| M00-QA-003 | Invalid Gitleaks JSON report | Corrected and locally validated |
| M00-GOV-001 | Independent release reviewer unavailable | Manual authorization accepted |
| M00-GOV-002 | Native secret scanning unavailable | Compensating controls implemented |
| M00-GOV-003 | GHCR access verification | Deferred until authorized publication |
| M00-TECH-001 | Starlette TestClient deprecation | Nonblocking technical debt |
| M00-TECH-002 | Gitleaks maintenance lifecycle | Monitor |
| M00-ENV-001 | Insufficient local disk space | Resolved |
| POST-MVP-001 | NAS backup and restore capability | Owner-approved post-MVP remediation |

## 11. Future security requirements

Before implementing external integrations or remote administration:

- Protect against SSRF and unsafe redirects.
- Validate resolved network addresses.
- Bound request sizes and execution times.
- Sanitize external HTML and metadata.
- Separate untrusted article content from model instructions.
- Prevent article content from invoking tools.
- Implement authenticated administrative access.
- Establish TLS and appropriate OAuth scopes.
- Implement rate limits, audit logging and CSRF protection
  where applicable.
- Restrict production credentials and rotate them when necessary.

Backup and restore remediation remains a tracked post-MVP task.

## 12. Acceptance limitations

Local and remote CI acceptance have both been demonstrated.

Publisher cryptographic attestations have not been independently
verified.

Security exception acceptance does not establish that vulnerable
code is unreachable or that vulnerabilities have been patched.

Existing database volumes have not been retroactively hardened.

The synthetic AWS credential discrepancy remains unresolved.

The integrated scanner scripts passed remote CI verification.
The release workflow and GHCR access require a separately
authorized publication exercise.

No production image has been published or deployed as part of
this assessment.


## 13. Remote CI acceptance

Acceptance date: 2026-11-24.

Validated implementation commit: 21698b2.

| Workflow | Result | Duration |
|---|---|---|
| CI #9 - Feature branch push | Passed | 1m 26s |
| CI #10 - Pull request synchronization | Passed | 1m 29s |

### Remote execution defects

| ID | Description | Disposition |
|---|---|---|
| M00-QA-004 | Gitleaks report directory permissions | Resolved |
| M00-QA-005 | Trivy vulnerability database cache permissions | Resolved |

Both defects were corrected by aligning scanner container runtime
UID and GID with the executing host user.

No security thresholds were relaxed.

### Acceptance disposition

M00-A security implementation and CI acceptance are complete.

Previously documented residual risks and approved temporary
exceptions remain applicable.

The publication workflow and GHCR access remain unverified.
Production deployment and merge authorization remain separate
project decisions.
