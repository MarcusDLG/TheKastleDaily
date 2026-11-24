# The Kastle Daily
M00 provisional initialization. Master Execution Plan Revision 4.0 reconciliation remains pending.

Python 3.12: `pip install -r requirements-dev.txt`, then `python -m pytest`. Copy `.env.example` to `.env`, set a strong password, and use `docker compose up --build -d` for local smoke testing only. Check `http://127.0.0.1:8765/healthz`. No NAS deployment authorized.

See [status](docs/PROJECT_STATUS.md), [architecture](docs/ARCHITECTURE.md), [security](docs/SECURITY.md), [integrations](docs/INTEGRATIONS.md), and [testing](docs/TESTING.md).
