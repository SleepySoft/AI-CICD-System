#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <version> [output-dir] [--bundle-only]" >&2
  exit 2
fi
version="$1"
output="${2:-$repo/dist}"
extra=()
[[ "${3:-}" == "--bundle-only" ]] && extra+=("--bundle-only")
python="${CHRONICLER_BUILD_PYTHON:-$repo/build/chronicler/venv311/bin/python}"
[[ -x "$python" ]] || { echo "missing CPython 3.11 build venv: $python" >&2; exit 1; }
"$python" "$repo/scripts/build-chronicler.py" --version "$version" --output "$output" "${extra[@]}"