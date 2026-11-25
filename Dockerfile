FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .

# CVE-2026-124851: libzstd1 fix (deb13u1) predates the pinned base rebuild.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade libzstd1 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install \
    --no-cache-dir \
    --require-hashes \
    --only-binary=:all: \
    -r requirements.txt \
    && python -m pip check \
    && useradd --system --uid 10001 appuser

COPY app ./app
COPY config/editorial.yaml ./config/editorial.yaml
COPY alembic.ini .
COPY migrations ./migrations

USER 10001

CMD ["python", "-m", "app.schedule"]
