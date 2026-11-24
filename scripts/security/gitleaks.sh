#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

IMAGE="ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"

WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT

mkdir -p "$WORK/snapshot" "$WORK/trusted"
mkdir -p "$ROOT/artifacts/security"

echo "=== PREPARE TRUSTED SCAN INPUT ==="

python3 - "$WORK/snapshot" <<'PY'
import shutil
import subprocess
import sys
from pathlib import Path

root = Path.cwd().resolve()
target = Path(sys.argv[1])

raw = subprocess.check_output([
    "git", "ls-files", "-z",
    "--cached", "--others", "--exclude-standard",
])

paths = sorted(set(raw.decode().split("\0")) - {""})

for name in paths:
    relative = Path(name)

    if any(
        part.casefold() in {".gitleaksignore", ".gitleaks.toml"}
        for part in relative.parts
    ):
        raise SystemExit(
            f"Unauthorized scanner configuration: {name}"
        )

    source = root / relative

    if source.is_symlink() or not source.is_file():
        continue

    if not source.resolve().is_relative_to(root):
        raise SystemExit(f"Unsafe scan path: {name}")

    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)

print("Working-tree snapshot prepared.")
PY

cat > "$WORK/trusted/gitleaks.toml" <<'TOML'
title = "TheKastleDaily trusted scanner configuration"

[extend]
useDefault = true
TOML

touch "$WORK/trusted/.gitleaksignore"

git clone --quiet --no-local --mirror \
  "$ROOT" "$WORK/history.git"

echo "=== CHECK HISTORICAL SCANNER CONFIGURATION ==="

git -C "$WORK/history.git" log \
  --all --full-history --name-only --format= |
python3 -c '
import sys
from pathlib import PurePosixPath

for line in sys.stdin:
    parts = PurePosixPath(line.strip()).parts
    if any(
        p.casefold() in {".gitleaksignore", ".gitleaks.toml"}
        for p in parts
    ):
        raise SystemExit("Unauthorized historical scanner configuration")
'

scan() {
  local MODE="$1"
  local SOURCE="$2"
  local REPORT="$3"
  shift 3

  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --network none \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --memory 512m \
    --cpus 1 \
    --env GIT_CONFIG_COUNT=1 \
    --env GIT_CONFIG_KEY_0=safe.directory \
    --env GIT_CONFIG_VALUE_0=/scan \
    --mount "type=bind,source=$SOURCE,target=/scan,readonly" \
    --mount "type=bind,source=$WORK/trusted,target=/trusted,readonly" \
    --mount "type=bind,source=$ROOT/artifacts/security,target=/reports" \
    "$IMAGE" "$MODE" \
    --config=/trusted/gitleaks.toml \
    --gitleaks-ignore-path=/trusted/.gitleaksignore \
    --ignore-gitleaks-allow \
    --redact=100 \
    --exit-code=10 \
    --no-banner \
    --no-color \
    --timeout=120 \
    --report-format=json \
    --report-path=/reports/$(basename "$REPORT") \
    "$@" /scan
}

docker pull "$IMAGE"

STATUS=0

echo "=== GITLEAKS HISTORY SCAN ==="

scan git "$WORK/history.git" \
  "$ROOT/artifacts/security/gitleaks-history.json" \
  --log-opts="--all --full-history" || STATUS=1

echo "=== GITLEAKS WORKING-TREE SCAN ==="

scan dir "$WORK/snapshot" \
  "$ROOT/artifacts/security/gitleaks-tree.json" || STATUS=1

python3 - <<'REPORT_PY' || STATUS=1
import json
from pathlib import Path

root = Path("artifacts/security")

for name in (
    "gitleaks-history.json",
    "gitleaks-tree.json",
):
    path = root / name

    if not path.is_file():
        raise SystemExit(f"Missing scanner report: {name}")

    data = json.loads(path.read_text())

    if data not in ([], None):
        raise SystemExit(f"Credential findings present: {name}")

    print(f"PASS: Valid clean report: {name}")
REPORT_PY

exit "$STATUS"
