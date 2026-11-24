# External integration feasibility
M00-D feasibility assessment complete. No live API credentials were created. M00-C separately validated manual EPUB delivery and physical Kindle rendering.

- YouTube public metadata via API key: https://developers.google.com/youtube/data/guides/authentication ; quotas https://developers.google.com/youtube/data/determine_quota_cost . Prefer upload playlists. Captions require authorization: https://developers.google.com/youtube/data/reference/rest/v3/captions/download . Do not depend on unauthorized transcripts or downloads. Instagram excluded.
- RSS: verify licensing, attribution, access and limits per source. Never bypass paywalls.
- OpenAI: dedicated project key, usage cap, mock adapter, structured output and evidence checks. https://platform.openai.com/pricing/ . API billing separate; validate model access and cost.
- Kindle: EPUB via Send to Kindle; test EPUBCheck, TOC, font scaling, links, approved sender, size limits, device receipt and duplicates. SMTP success is not device delivery confirmation.
- MCP: validate account eligibility, secure tunnel amd64 compatibility, OAuth and read-only calls before writes.

## M00-D feasibility disposition

Assessment date: 2026-11-24.

The planned integration architecture is feasible for one
daily edition of approximately 15 articles.

Feasibility is not equivalent to production integration
qualification.

### RSS

Recommended role: primary ingestion source.

Implementation requirements:

- Maintain an approved source registry.
- Record feed URL, publisher, licensing disposition and category.
- Use conditional requests when supported.
- Apply bounded timeouts, response sizes and retry policies.
- Normalize timestamps, canonical URLs and source identifiers.
- Deduplicate repeated entries.
- Preserve attribution and source provenance.
- Reject unsafe redirects and private-network destinations.
- Do not bypass paywalls or assume feed access grants republication rights.

Source-specific access and licensing approval remain required.

### YouTube Data API

Recommended role: supplemental metadata ingestion.

Use approved channels and upload playlists where practical.

Implementation requirements:

- Store API credentials outside source control.
- Restrict credentials to required APIs.
- Track quota consumption and enforce request budgets.
- Handle pagination, quota exhaustion and unavailable videos.
- Preserve source attribution and canonical video links.
- Follow applicable API data retention and refresh requirements.
- Do not depend on unauthorized transcripts or video downloads.

Live quota allocation and credential validation remain pending.

### OpenAI API

Recommended role: structured editorial generation.

Implementation requirements:

- Use a dedicated API project and restricted credentials.
- Maintain configurable model selection.
- Enforce application-level request and spending limits.
- Track usage, latency, errors and estimated cost per edition.
- Validate structured output before publication.
- Preserve evidence and source references.
- Treat retrieved content as untrusted input.
- Prevent source content from controlling tools or instructions.
- Use mocks and fixtures in automated regression tests.

API billing is separate from ChatGPT subscriptions.

Exact model selection, current pricing, account limits and
live cost qualification remain implementation tasks.

### Amazon Send to Kindle

Recommended role: EPUB delivery through an approved sender.

M00-C validated manual delivery and physical Kindle rendering
on an 11th-generation Kindle Paperwhite.

Manual device acceptance: 31/31 passed.

Implementation requirements:

- Generate valid EPUB publications.
- Run formal EPUBCheck validation.
- Validate approved sender and destination configuration.
- Verify current attachment and delivery restrictions.
- Maintain a persistent delivery outbox.
- Record edition identifiers, checksums and delivery attempts.
- Prevent duplicate submissions.
- Treat ambiguous SMTP outcomes as requiring reconciliation.

SMTP acceptance does not prove Kindle library synchronization
or physical-device receipt.

Automated email delivery remains unqualified.

### MCP and ChatGPT

Recommended role: later administrative integration.

MCP is not a dependency of the newspaper MVP.

Implementation requirements:

- Verify ChatGPT account and workspace eligibility.
- Validate supported transport and authentication requirements.
- Evaluate secure connectivity and AMD64 compatibility.
- Begin with read-only status and diagnostic tools.
- Apply explicit authorization to later write operations.
- Reuse the application service layer.
- Never expose unrestricted database queries or shell commands.

Live connectivity, authentication and account eligibility
remain unverified.

## Cross-integration requirements

- Explicit connection and execution timeouts.
- Bounded retries with backoff.
- Idempotent processing where applicable.
- Persistent operational state.
- Redacted logs and credential isolation.
- Per-integration failure handling.
- Source licensing and attribution review.
- Current official documentation verification before live activation.

No external service purchases, credential creation or live
production integration deployment occurred during M00-D.
