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

**Decision: GHCR public.** The image carries no secrets — everything
sensitive arrives via environment at runtime — so anonymous pulls
remove real friction for friends at zero exposure cost. No
`docker login`, no PAT: `KASTLE_APP_IMAGE=ghcr.io/<owner>/kastle-daily:<tag>`
in `.env` is the entire install surface beyond the three secrets.

Zero-infra fallback: a `docker save` tarball shipped directly — the
same path that staged the NAS image — needs no registry at all.

## Compute shapes (easiest first)

| Shape | ~Cost/mo | Scheduling | Storage | Fit |
|---|---|---|---|---|
| **Lightsail nano VM** | $5 | in-container daemon | instance disk | **Easiest** — clone + `compose up`, identical to the NAS runbook |
| Fly.io / Railway machine | ~$1–3 | in-container daemon | platform volume | Middle path, deploys from the Dockerfile |
| **ECS Fargate + EventBridge** | ~$0.15 compute | platform cron runs `--once` | EFS `/data` | **Cheapest** run; most AWS machinery (task def, IAM, EFS, rule) |
| ~~Lambda~~ | — | — | — | Rejected: EFS requires VPC, VPC egress requires NAT (~$30/mo) |

The daemon-versus-cron insight: the loop in `app/schedule.py` is a
convenience for hosts that lack schedulers. Under EventBridge, a
systemd timer or a fly.io scheduled machine, `--once` is the whole
pipeline and the platform owns "daily at 07:00 ET".

Recommended default: **Lightsail** — the friend path is the NAS
runbook verbatim, and $5/mo buys the simplest possible mental model.
Fargate is the optimization for a cost-sensitive second deployment,
not the first.

## Admin surface on a cloud host

The `admin` service binds `127.0.0.1` — correct on a LAN NAS, and on a
cloud VM it stays reachable without any ingress change:

- **SSH tunnel** (`ssh -L 8080:localhost:8080 friend@host`) — the
  zero-configuration answer; reuse the SSH access the host already has.
- **Authenticated portal** — when a stable URL is wanted instead:
  HTTPS endpoint with basic auth or a tailnet join. This is the only
  shape that introduces inbound traffic, so it stays optional.

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

- [x] GHCR publication authorized + first push (M00-GOV-003) —
      `ghcr.io/marcusdlg/kastle-daily:latest` public, anonymous
      amd64/arm64 pull verified
- [x] `docs/DEPLOY.md` — friend-facing install (compose + env only)
- [ ] `.env.example` annotated for cloud secrets backends
- [ ] Optional: `deploy/` directory with a bootstrap script per shape
- [ ] Evidence: one edition produced + delivered from a cloud host

### Acceptance matrix

The DEPLOY.md runbook executed end-to-end on each target before the
friend path is called qualified:

| Target | What it proves |
|---|---|
| AWS Lightsail (amd64) | The documented cloud shape; scheduled cron + durable volume |
| macOS desktop (arm64) | Multi-arch manifest arm64 leg; Docker Desktop compose |
| Windows desktop | Docker Desktop/WSL2 path — the sharpest edge: CRLF `.env` endings, file sharing, named volumes |

Each pass = pull → `up -d` → `--once` → Kindle receipt → admin page →
one scheduled edition firing unattended.
