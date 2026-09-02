#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 <release-dir> <install-dir> [components-dir]" >&2
  exit 2
fi
release="$1"
install="$2"
[[ -f "$release/manifest.json" ]] || { echo "not a Chronicler release: $release" >&2; exit 1; }
python3 - "$release/manifest.json" <<'PY'
import json, sys
if json.load(open(sys.argv[1], encoding="utf-8")).get("bundle_only"):
  raise SystemExit("bundle-only directory cannot be installed")
PY
[[ -x "$release/chronicler" ]] || { echo "release is missing executable: $release/chronicler" >&2; exit 1; }
mkdir -p "$install"
cp -a "$release/." "$install/"
[[ -f "$install/.env" ]] || cp "$install/.env.example" "$install/.env"
mkdir -p "$install/components"
if [[ -n "${3:-}" ]]; then
  [[ -d "$3" ]] || { echo "external components directory not found: $3" >&2; exit 1; }
  cp -a "$3/." "$install/components/"
fi
echo "Installed: $install"
echo "Next: edit .env, provision external components/, then run ./chronicler serve"