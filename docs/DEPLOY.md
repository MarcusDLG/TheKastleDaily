# Deploy your own Kastle Daily

Self-hosted install for anyone without the repo checkout — two files,
one image pull, one Kindle address. The worker is outbound-only (RSS +
OpenAI + SMTP): nothing listens, nothing needs a public port.

Target: any Docker host with outbound internet (a $5 Lightsail VM, a
home server, a Raspberry Pi 4+). Daily cost beyond the host: roughly
$0.02–0.05 of OpenAI usage per edition.

## 1. `compose.yaml`

Create an empty directory and save this as `compose.yaml`:

```yaml
name: kastle-daily
services:
  worker:
    image: ghcr.io/marcusdlg/kastle-daily:latest
    command: [python, -m, app.schedule]
    volumes:
      - kastle-data:/data
    environment:
      KASTLE_DB: /data/kastle.db
      SMTP_HOST: ${SMTP_HOST:-}
      SMTP_PORT: ${SMTP_PORT:-465}
      SMTP_USERNAME: ${SMTP_USERNAME:-}
      SMTP_PASSWORD: ${SMTP_PASSWORD:-}
      KINDLE_ADDRESS: ${KINDLE_ADDRESS:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_MODEL: ${OPENAI_MODEL:-gpt-5-mini}
      OPENAI_REASONING_EFFORT: ${OPENAI_REASONING_EFFORT:-low}
      OPENAI_MAX_COST_USD: ${OPENAI_MAX_COST_USD:-0.50}
      SECRETS_BACKEND: ${SECRETS_BACKEND:-env}
      SECRETS_PREFIX: ${SECRETS_PREFIX:-kastle-daily/}
    restart: unless-stopped
volumes:
  kastle-data: {}
```

## 2. `.env`

Save this as `.env` in the same directory and fill in the three
secrets:

```dotenv
# Send to Kindle — an app password, not your normal login.
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your-sender@gmail.com
SMTP_PASSWORD=your-app-password
KINDLE_ADDRESS=you@kindle.com

# Drafting model — leave empty to fall back to the local template.
OPENAI_API_KEY=sk-...
```

The sender address must be on your Amazon account's approved personal
documents list (Amazon → Preferences → Personal Document Settings).
An app password, never your main Gmail password.

## 3. Run

```sh
docker compose pull        # pulls the right arch automatically
docker compose up -d
docker compose ps          # worker should be Up
```

The first edition fires at the next 07:00 America/New_York. To produce
one immediately:

```sh
docker compose exec worker python -m app.schedule --once
```

Watch a pass: `docker compose logs -f worker` — the final JSON reports
selection, drafting, edition, delivery and retention results.

## Optional: operations dashboard

A read-only page at `http://localhost:8080` — editions, block reasons,
feed health, deliveries. Add to the same `compose.yaml`:

```yaml
  admin:
    image: ghcr.io/marcusdlg/kastle-daily:latest
    command: [python, -m, app.admin]
    volumes:
      - kastle-data:/data
    environment:
      KASTLE_DB: /data/kastle.db
    ports:
      - "127.0.0.1:8080:8080"
    restart: unless-stopped
```

On a remote host, reach it without opening any port:
`ssh -L 8080:localhost:8080 you@host`.

## Updating

```sh
docker compose pull && docker compose up -d
```

All state lives in the `kastle-data` volume (`/data/kastle.db` plus
`editions/`); the image carries no state. 30-day retention prunes old
rows and artifacts automatically on every run.

## Optional: AWS Secrets Manager

On an AWS host you can keep the app secrets out of the `.env` file
entirely — only an AWS credential lives on the box.

1. Create one secret per name in Secrets Manager (type **Other →
   Plaintext**, the raw value — not the key/value JSON editor):

   | Secret name | Value |
   |---|---|
   | `kastle-daily/SMTP_PASSWORD` | your app password |
   | `kastle-daily/KINDLE_ADDRESS` | you@kindle.com |
   | `kastle-daily/OPENAI_API_KEY` | sk-... |

2. Give the host read access. On **EC2/Fargate**: attach an IAM
   role with `secretsmanager:GetSecretValue` on
   `arn:aws:secretsmanager:*:<acct>:secret:kastle-daily/*` — boto3
   picks it up automatically. On **Lightsail** (no instance roles):
   create a scoped-down IAM user, and put its credentials in `.env`
   as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — the worker env
   passes them through, so add those lines to the compose
   `environment:` block too.

3. In `.env`: `SECRETS_BACKEND=aws` and drop the three secrets. Env
   values still win when both are set, so you can override per-host.

## Cheaper shapes

An always-on VM is the simplest shape, not the only one — the
scheduler daemon is optional. `python -m app.schedule --once` is a
complete pipeline run, so any cron (systemd timer, EventBridge +
Fargate, fly.io scheduled machines) can own "daily at 07:00 ET" and the
host can sleep or run nothing the rest of the day. See
CLOUD_DEPLOY.md for the shape table.
