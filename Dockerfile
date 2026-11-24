FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN python -m pip install \
    --no-cache-dir \
    --require-hashes \
    --only-binary=:all: \
    -r requirements.txt \
    && python -m pip check \
    && useradd --system --uid 10001 appuser

COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations

USER 10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
