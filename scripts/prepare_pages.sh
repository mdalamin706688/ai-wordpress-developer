#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="$ROOT/docs"
mkdir -p "$DOCS"
cp "$ROOT/demo/index.html" "$DOCS/index.html"
cp "$ROOT/demo/config.js" "$DOCS/config.js"
cp "$ROOT/fixtures/hearing_salon.json" "$DOCS/hearing_salon.json"
cp "$ROOT/demo/hearing-sheet.csv" "$DOCS/hearing-sheet.csv"
cp "$ROOT/demo/hearing-sheet.csv" "$DOCS/hearing.csv"
touch "$DOCS/.nojekyll"
echo "Prepared $DOCS for GitHub Pages"
