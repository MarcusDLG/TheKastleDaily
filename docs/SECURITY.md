# The Kastle Daily | Security Architecture

## Document control

- Milestone: M00-A
- Assessment date: 2026-11-24
- Status: Local security acceptance passed
- Remote CI acceptance: Pending
- Production deployment: Not authorized

## 1. Security principles

- Treat the Synology NAS as internet-connected infrastructure.
- Do not modify existing NAS services.
- Keep PostgreSQL inaccessible from external networks.
- Bind the initial application API to loopback only.
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

PostgreSQL uses:

- Digest-pinned PostgreSQL 17 image.
- Isolated internal Docker network.
- No published database port.
- SCRAM-SHA-256 local and host authentication.
- Data checksums enabled during initialization.
- Authenticated SQL health checks.
- Persistent database storage.
- Explicit CPU and memory limits.

Database initialization settings apply to newly initialized
volumes. Existing volumes must be assessed separately.

The bootstrap database role must not be used as the application
runtime role. Least-privilege application roles will be created
before database access is introduced.

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
- Scans exported AMD64 application and PostgreSQL image archives.
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
| Approved PostgreSQL findings matched | 27/27 |
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
| M00-SEC-004 | Scanner configuration bypass | Local mitigation validated; CI pending |
| M00-SEC-005 | Application high findings without fixes | Monitor |
| M00-SEC-006 | PostgreSQL OS vulnerabilities | Temporary exception and monitoring |
| M00-SEC-007 | Embedded gosu vulnerabilities | Temporary exception |
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

Local scanner and policy acceptance does not establish successful
execution in GitHub Actions.

Publisher cryptographic attestations have not been independently
verified.

Security exception acceptance does not establish that vulnerable
code is unreachable or that vulnerabilities have been patched.

Existing database volumes have not been retroactively hardened.

The synthetic AWS credential discrepancy remains unresolved.

The integrated scanner scripts require remote CI verification.
The release workflow and GHCR access require a separately
authorized publication exercise.

No production image has been published or deployed as part of
this assessment.
