#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="$ROOT/docs"
V2="$ROOT/demo/v2"
mkdir -p "$DOCS"
cp "$V2/index.html" "$DOCS/index.html"
cp "$V2/config.js" "$DOCS/config.js"
cp "$V2/app.js" "$DOCS/app.js"
cp "$V2/sheets.js" "$DOCS/sheets.js"
cp "$V2/styles.css" "$DOCS/styles.css"
cp "$V2/favicon.svg" "$DOCS/favicon.svg" 2>/dev/null || true
cp "$ROOT/fixtures/hearing_salon.json" "$DOCS/hearing_salon.json"
touch "$DOCS/.nojekyll"
echo "Prepared $DOCS for GitHub Pages (from demo/v2)"
