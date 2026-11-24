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
The reviewed drafts and story photos remain local inputs. Automatic evidence
gathering, drafting, delivery and scheduling are separate integration work.
