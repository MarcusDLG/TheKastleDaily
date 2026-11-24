#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

APP_IMAGE="${1:?Application image required}"

TRIVY="ghcr.io/aquasecurity/trivy@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"

POSTGRES_IMAGE="$(
  python3 - <<'PY'
import re
from pathlib import Path

import yaml

data = yaml.safe_load(Path("compose.yaml").read_text())
image = data["services"]["db"]["image"]

if not re.fullmatch(
    r"postgres:[^\s]+@sha256:[0-9a-f]{64}", image
):
    raise SystemExit("PostgreSQL image must be digest pinned")

print(image)
PY
)"

WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT

mkdir -p "$WORK/cache" "$WORK/images"
mkdir -p "$ROOT/artifacts/security"

docker pull "$TRIVY"

echo "=== UPDATE TRIVY DATABASE ==="

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=512m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --mount "type=bind,source=$WORK/cache,target=/cache" \
  "$TRIVY" image \
  --config="" \
  --cache-dir /cache \
  --disable-telemetry \
  --skip-version-check \
  --download-db-only \
  --no-progress \
  --timeout 10m

docker pull --platform linux/amd64 "$POSTGRES_IMAGE"

scan() {
  local NAME="$1"
  local IMAGE="$2"
  local DIGEST="$3"

  echo "=== SCANNING $NAME ==="

  docker image save \
    --platform linux/amd64 \
    -o "$WORK/images/$NAME.tar" \
    "$IMAGE" || return 1

  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --network none \
    --read-only \
    --tmpfs /tmp:rw,nosuid,size=512m \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --mount "type=bind,source=$WORK/cache,target=/cache" \
    --mount "type=bind,source=$WORK/images,target=/images,readonly" \
    "$TRIVY" image \
    --config="" \
    --ignorefile="" \
    --cache-dir /cache \
    --disable-telemetry \
    --skip-version-check \
    --skip-db-update \
    --skip-java-db-update \
    --offline-scan \
    --scanners vuln \
    --format json \
    --exit-code 0 \
    --timeout 10m \
    --input "/images/$NAME.tar" \
    > "artifacts/security/trivy-$NAME.json" || return 1

  rm "$WORK/images/$NAME.tar" || return 1

  python3 scripts/security/evaluate.py \
    --report "artifacts/security/trivy-$NAME.json" \
    --exceptions config/security/exceptions.json \
    --image "$NAME" \
    --digest "$DIGEST" \
    --output "artifacts/security/policy-$NAME.json"
}

APP_DIGEST="$(
  docker image inspect \
    --platform linux/amd64 \
    --format '{{.Id}}' "$APP_IMAGE"
)"

POSTGRES_DIGEST="${POSTGRES_IMAGE##*@}"

docker image inspect \
  --platform linux/amd64 \
  --format '{{json .RepoDigests}}' "$POSTGRES_IMAGE" |
python3 -c '
import json
import sys

expected = sys.argv[1]
digests = json.load(sys.stdin) or []

if not any(d.endswith("@" + expected) for d in digests):
    raise SystemExit("PostgreSQL image digest verification failed")
' "$POSTGRES_DIGEST"

STATUS=0

scan application "$APP_IMAGE" "$APP_DIGEST" || STATUS=1
scan postgres "$POSTGRES_IMAGE" "$POSTGRES_DIGEST" || STATUS=1

exit "$STATUS"
