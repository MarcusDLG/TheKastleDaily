# Editorial selection

The selector produces a local JSON plan from approved RSS articles.
It reads the existing editorial configuration, ranks candidates by
recency, and deduplicates canonical article IDs across sections.
Largest-remainder rounding converts the configured weights into
15 article slots. Equal remainders are resolved by category key.

At least one slot is reserved for Sim Racing or Maker and Radio. If
there is no eligible item from either category in the last two days,
the selector can use an unpublished candidate from the preceding
30 days and marks it as archived. Articles used in prior validated
editions are excluded. If neither category has an eligible candidate,
the plan reports the missing coverage and the command exits with status
2. Remaining categories retain their allocation and report shortfalls
explicitly. Drafting, pagination, EPUB rendering and delivery are
separate steps.

The personal pilot registration command additionally offers the public
iRacing and Raspberry Pi feeds. It preserves existing approval decisions.
Reddit is outside this pipeline.

## Run a local edition plan

After setting up the [database](M02.md), run:

```sh
docker compose build api
docker compose run --rm migrate python -m app.pilot
docker compose run --rm ingest
docker compose run --rm -T select-stories
```

The default edition date is the current date in America/New_York.
Use `docker compose run --rm -T select-stories python -m app.selection --date YYYY-MM-DD`
to inspect an earlier date using observations stored by that date.
The plan contains source attribution and flags any missed category
targets or use of the archive.
