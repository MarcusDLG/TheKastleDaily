#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

APP_IMAGE="${1:?Application image required}"

TRIVY="ghcr.io/aquasecurity/trivy@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"

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

echo "=== SCANNING application ==="

docker image save \
  --platform linux/amd64 \
  -o "$WORK/images/application.tar" \
  "$APP_IMAGE"

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
  --input "/images/application.tar" \
  > "artifacts/security/trivy-application.json"

APP_DIGEST="$(
  docker image inspect \
    --platform linux/amd64 \
    --format '{{.Id}}' "$APP_IMAGE"
)"

python3 scripts/security/evaluate.py \
  --report "artifacts/security/trivy-application.json" \
  --exceptions config/security/exceptions.json \
  --image application \
  --digest "$APP_DIGEST" \
  --output "artifacts/security/policy-application.json"
