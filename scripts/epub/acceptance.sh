#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
version=5.4.0
digest=33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c
archive="epubcheck-$version.zip"

if [[ -z "${EPUBCHECK_JAR:-}" ]]; then
    curl --fail --silent --show-error --location --max-time 60 \
        --output "$scratch/$archive" \
        "https://github.com/w3c/epubcheck/releases/download/v$version/$archive"
    (cd "$scratch" && printf '%s  %s\n' "$digest" "$archive" | shasum -a 256 -c -)
    unzip -q "$scratch/$archive" -d "$scratch"
    EPUBCHECK_JAR="$scratch/epubcheck-$version/epubcheck.jar"
fi
bash scripts/epub/build.sh tests/fixtures/edition/plan.json tests/fixtures/edition/drafts.json \
    "$scratch/fixture.epub" "$EPUBCHECK_JAR"
