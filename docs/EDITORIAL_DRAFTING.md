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

When the page declares an `og:image`, the photo is fetched under the
same transport rules at the renderer's 4 MiB cap, checked for JPEG or
PNG magic bytes, and written content-addressed to `editions/photos/`
beside the database. The record keeps the resolved `photo_url`, the
render-relative `photo_file` name and any `og:image:alt` text. A
missing, oversized or non-image photo never blocks the story; the
renderer simply omits the figure.

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

## OpenAI provider

Setting `OPENAI_API_KEY` switches drafting to `OpenAIGenerator`
(`app/openai.py`), which issues one chat completion per story against a
strict JSON schema matching the draft contract. The prompt carries the
evidence excerpt as quoted data and the observed URL list the output's
sources must trace to; `validate_draft` still enforces the contract, so
unsupported or malformed output only blocks that story's slot.

Guardrails: the evidence is never instructions, the model name lands on
`editorial_runs.model` for provenance, token usage and estimated cost
accumulate per call, `OPENAI_MAX_COST_USD` caps estimated spend per run
(declining remaining stories once reached), and two consecutive
transport failures degrade the adapter for the rest of the pass.
`OPENAI_MODEL` selects the model and the per-million pricing in
`app/openai.py` (or `OPENAI_INPUT/OUTPUT_COST_PER_MTOK` overrides)
estimates cost. No call is made without a configured key, and tests
inject the transport.

gpt-5-family models spend completion tokens on reasoning before
content, so `OPENAI_REASONING_EFFORT` (default `low`, gpt-5-family
only) bounds that spend and the completion cap leaves headroom for
both reasoning and output — an undersized cap makes the model return
empty content. A reply that is not valid JSON — or that parses but
violates the draft contract — gets one repair attempt feeding the
rejected reply and the reason back before the story is blocked.
Blocked stories record a per-story reason on
`editorial_runs.error_detail` (a capped JSON list) alongside the
`stories_blocked` error code.

## Provenance

Every produced story is linked to all of its article's source
observations through `editorial_evidence` rows carrying an acquisition
note (retrieval time, URL, extracted length). `to_render_drafts` converts
a run's stories into the EPUB renderer's drafts contract, mapping
evidence links to `{url, label}` sources. When the story's acquisition
holds a photo, the draft gains `photo` — `file` relative to the editions
directory, `alt` (the declared `og:image:alt` or the story headline),
and `credit` attributing the image to its publisher.

## Run locally

The run record also stores the selection plan JSON, so the edition
build is a pure function of the run: plan plus persisted drafts.

`python -m app.schedule --once` now runs migrations, registration,
ingestion, selection, drafting and the edition build. Per-story fetch or
validation failures never fail the pass; they surface in the drafting
summary and the run record. Inspect `editorial_runs`, `editorial_stories`,
`editorial_evidence` and `evidence_acquisitions` for outcomes.
