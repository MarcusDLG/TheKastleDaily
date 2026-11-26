# Secrets management (milestone spec)

Pluggable secret resolution so the same code runs on a `.env` file
(NAS/dev) or a managed backend (AWS deployments) — with values never
entering the repo, logs or the container image.

## Current state

All configuration arrives as environment variables:

| Variable | Sensitivity |
|---|---|
| `SMTP_PASSWORD` | Secret — Gmail app password |
| `OPENAI_API_KEY` | Secret — billed credential |
| `KINDLE_ADDRESS` | Personal address — treat as private |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `OPENAI_*` tunables | Configuration, not secret |

Consumers read them through `app/secrets.py`'s resolver
(`OpenAIGenerator.from_env`, the delivery transport) — env first,
then the configured backend.

## Design

`app/secrets.py` — a resolver with a backend chain:

```python
def secret(name: str) -> str | None:
    """Resolve by chain: process env → backend. None when unset."""
```

- `SECRETS_BACKEND` selects the backend: `env` (default, today's
  behavior — zero migration) or `aws`.
- `env` backend: `os.environ` passthrough, nothing else changes.
- `aws` backend: AWS Secrets Manager lookup by
  `SECRETS_PREFIX + name` (default prefix `kastle-daily/`), fetched
  once per process and cached — no per-call latency, no repeated API
  cost.
- AWS adds one dependency (`boto3`); hand-rolled SigV4 was considered
  and rejected — not worth the correctness risk.
- Call sites swap `os.environ.get(X)` for `secret(X)` — mechanical,
  testable via backend injection like `transport` today.

## Contract

- Values never logged, never printed, never in the image layers —
  `.env` stays 600-perms on hosts, gitignored always.
- Resolution failure for a *required* secret behaves like today's
  missing-env behavior (delivery skipped / template generator), not a
  crash.
- AWS backend fails closed: lookup errors fall back to unset, never
  to a default value.

## Rollout

1. ✅ `secrets.py` + `env` backend — no behavior change, full suite green.
2. ✅ `aws` backend + boto3 (pinned, hashed) + unit tests with injected
   client.
3. ✅ Documented in `.env.example` and DEPLOY.md; friend AWS deploys
   point `SECRETS_BACKEND=aws` and hold no plaintext secrets on disk.
