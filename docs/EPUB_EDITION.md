# Local EPUB edition build

The build consumes the JSON plan from `select-stories` and a reviewed draft
file. It matches entries by article ID, follows the plan's reading order, and
requires the reserved Sim Racing or Maker story before it can build an issue.
It embeds local images, makes every story a separate EPUB reading-order
entry, and generates a linked contents page and coverage page.

## Validate the build with fixtures

Run `bash scripts/epub/acceptance.sh` with Python 3, Java and unzip available.
CI uses the same command. The script downloads EPUBCheck 5.4.0 and verifies
its SHA-256. To reuse an existing installation, set `EPUBCHECK_JAR` to its
JAR path. The fixture contains invented stories and makes no publisher or
model calls.

## Build a reviewed issue

```sh
bash scripts/epub/build.sh plan.json drafts.json issue.epub /path/to/epubcheck.jar
```

See [fixture plan](../tests/fixtures/edition/plan.json) and
[fixture drafts](../tests/fixtures/edition/drafts.json) for the input shapes.
Provide an original headline and at least two paragraphs per story.
The plan's publisher and URL appear as attribution. The optional
`sources` array adds other evidence links with `url` and `label` fields.
An optional cover is a local JPEG or PNG path relative to the draft file.
A story photo takes `file`, `alt`, and `credit`. Image paths must stay within
the drafts directory, and each image must be at most 4 MiB.

The build writes the final path only after EPUBCheck passes with no
warnings. Identical plan and draft inputs generate identical output.
The reviewed drafts and story photos remain local inputs.

## Automated edition build

After drafting, the worker builds the edition from the latest succeeded
editorial run for the New York edition date. The run's stored selection
plan is restricted to the stories that actually drafted; if the original
reserve pick was blocked, the newest surviving reserve-category story
carries the flag, and if no reserve-category story remains the build
fails. The rendered bytes are hashed with SHA-256 and moved into
`editions/<edition-date>.epub` beside the database atomically, so a
failed build never disturbs a previous artifact.

The `editions` row records the artifact path as `epub_key`, the hex
digest as `epub_sha256`, and status `validated`; `edition_stories` map
the renderer's order back to the run's stories so later selections
exclude articles already published in a validated edition. Rebuilding a
date with a validated artifact in place is a no-op, and a failed build
is recorded as `failed` so the scheduler's bounded attempts can retry.

The pipeline `validated` status means the renderer's contract checks
passed; EPUBCheck 5.4.0 remains a CI and acceptance gate on the same
deterministic renderer rather than a per-edition worker step, because
the worker image carries no Java runtime. Validated editions feed the
delivery outbox; see [DELIVERY.md](DELIVERY.md).
