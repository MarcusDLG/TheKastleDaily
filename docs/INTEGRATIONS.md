# Early integration spikes
No live credentials or device tests performed.

- YouTube public metadata via API key: https://developers.google.com/youtube/data/guides/authentication ; quotas https://developers.google.com/youtube/data/determine_quota_cost . Prefer upload playlists. Captions require authorization: https://developers.google.com/youtube/data/reference/rest/v3/captions/download . Do not depend on unauthorized transcripts or downloads. Instagram excluded.
- RSS: verify licensing, attribution, access and limits per source. Never bypass paywalls.
- OpenAI: dedicated project key, usage cap, mock adapter, structured output and evidence checks. https://platform.openai.com/pricing/ . API billing separate; validate model access and cost.
- Kindle: EPUB via Send to Kindle; test EPUBCheck, TOC, font scaling, links, approved sender, size limits, device receipt and duplicates. SMTP success is not device delivery confirmation.
- MCP: validate account eligibility, secure tunnel amd64 compatibility, OAuth and read-only calls before writes.
