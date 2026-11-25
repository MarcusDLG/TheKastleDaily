# Cloud / friend deployment (milestone spec)

The paper for someone without a NAS: one container, one volume,
outbound-only traffic. `python -m app.schedule --once` is a complete
pipeline run, which makes the 24/7 daemon optional — any platform with
cron can drive it.

## Invariants (unchanged everywhere)

- `KASTLE_DB` points at durable storage; the whole state is one SQLite
  file plus the `editions/` directory.
- No ingress: the worker publishes no ports, so there is no TLS,
  auth or attack surface to manage on any platform.
- Hardened compose: read-only root, dropped caps, mem_limit, restart
  policy, healthcheck.
- Secrets arrive as environment variables (see SECRETS.md for managed
  backends).

## Distribution

Friend deploys pull rather than build, which requires a published
image — GHCR is the gate (tracker M00-GOV-003: first authorized
publication). `compose.yaml` already supports it:

```yaml
image: ${KASTLE_APP_IMAGE:-kastle-daily:dev}
```

A friend's `.env` sets `KASTLE_APP_IMAGE=ghcr.io/<owner>/kastle-daily:<tag>`.
Until publication is authorized, the friend path is `git clone` +
`docker compose build` — works, just slower.

## Compute shapes

| Shape | ~Cost/mo | Scheduling | Storage | Fit |
|---|---|---|---|---|
| **Lightsail nano VM** | $5 | in-container daemon | instance disk | Simplest: clone + `compose up`, identical to NAS |
| **ECS Fargate + EventBridge** | ~$0.15 compute | platform cron runs `--once` | EFS `/data` | Cheapest run; most AWS machinery (task def, IAM, EFS, rule) |
| Fly.io / Railway machine | ~$1–3 | in-container daemon | fly/railway volume | Middle path, deploys from the Dockerfile |
| ~~Lambda~~ | — | — | — | Rejected: EFS requires VPC, VPC egress requires NAT (~$30/mo) |

The daemon-versus-cron insight: the loop in `app/schedule.py` is a
convenience for hosts that lack schedulers. Under EventBridge, a
systemd timer or a fly.io scheduled machine, `--once` is the whole
pipeline and the platform owns "daily at 07:00 ET".

## Deploy walkthrough (Lightsail path)

1. Provision a nano instance; install Docker.
2. Copy `compose.yaml` + `.env` (three secrets) to the instance.
3. `docker compose up -d` — first edition at the next edition time,
   or `docker compose exec worker python -m app.schedule --once`.
4. Verify `docker compose ps` → healthy; check the Kindle.

Fargate path adds: ECR push, EFS access point for `/data`, task
definition (0.5 vCPU / 1 GB fits the workload), EventBridge schedule
`cron(0 12 * * ? *)` for 07:00 ET.

## Milestone checklist

- [ ] GHCR publication authorized + first push (M00-GOV-003)
- [ ] `docs/DEPLOY.md` — friend-facing install (compose + env only)
- [ ] `.env.example` annotated for cloud secrets backends
- [ ] Optional: `deploy/` directory with a bootstrap script per shape
- [ ] Evidence: one edition produced + delivered from a cloud host
