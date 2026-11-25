# Editorial drafting

The drafting stage turns one edition's selection plan into reviewable
stories. It runs inside the daily worker pipeline, after selection, when
the coverage floor is met. Each pass records one `editorial_runs` row per
edition date; a later pass for the same date is suppressed once a run has
succeeded.

## Evidence acquisition

For every selected article the stage fetches the canonical URL and stores
one `evidence_acquisitions` row: the fetched URL, retrieval time, status
(`extracted` or `failed`), a detail string, the extracted text and the
fetched page's SHA-256. Successful records are reused across passes; a
`failed` record is retried next pass. The fetch reuses the feed
transport rules (HTTPS only, public addresses, no redirects, bounded
reads, five-second budget) and `trafilatura` reduces the page to article
text. Evidence bytes are data only — they never steer control flow.

## Generation contract

A generator receives one plan story plus its extracted text and returns a
`DraftOutput` (headline, paragraphs, sources) or declines with `None`.
Before anything is recorded, `validate_draft` enforces:

- a non-empty headline bounded to 200 characters;
- at least two substantive paragraphs (80–2000 characters each);
- at least one source, and every source URL must belong to the
  article's observed URLs — unsupported claims cannot be recorded.

The default `TemplateGenerator` keeps the pipeline useful before a model
provider is enabled: it reuses the feed headline and quotes the first
substantive evidence paragraphs with publisher attribution. Usage fields
(tokens and estimated cost) land on the run record; the template reports
zero. A story that fails evidence or validation is blocked: it produces
no `editorial_stories` row, the blocked count is reported, and the run is
flagged `stories_blocked` for review.

## Provenance

Every produced story is linked to all of its article's source
observations through `editorial_evidence` rows carrying an acquisition
note (retrieval time, URL, extracted length). `to_render_drafts` converts
a run's stories into the EPUB renderer's drafts contract, mapping
evidence links to `{url, label}` sources.

## Run locally

The run record also stores the selection plan JSON, so the edition
build is a pure function of the run: plan plus persisted drafts.

`python -m app.schedule --once` now runs migrations, registration,
ingestion, selection, drafting and the edition build. Per-story fetch or
validation failures never fail the pass; they surface in the drafting
summary and the run record. Inspect `editorial_runs`, `editorial_stories`,
`editorial_evidence` and `evidence_acquisitions` for outcomes.
