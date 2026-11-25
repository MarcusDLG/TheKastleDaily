#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 4 || "$3" != *.epub ]]; then
    echo "Usage: bash scripts/epub/build.sh PLAN.json DRAFTS.json OUTPUT.epub EPUBCHECK.jar" >&2
    exit 2
fi
plan=$1
drafts=$2
output=$3
validator=$4
mkdir -p -- "$(dirname -- "$output")"
scratch=$(mktemp -d "$(dirname -- "$output")/.kastle-epub.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
"${KASTLE_PYTHON:-python3}" -m app.edition --plan "$plan" --drafts "$drafts" --out "$scratch/edition.epub"
java -jar "$validator" "$scratch/edition.epub" --failonwarnings
mv -- "$scratch/edition.epub" "$output"
echo "Validated EPUB: $output"
