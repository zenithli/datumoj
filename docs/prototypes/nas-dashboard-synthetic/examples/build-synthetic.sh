#!/bin/sh
# Local synthetic build only. Output must not already exist.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 "$base/tools/build.py" --mode synthetic --input "$base/examples/synthetic-status.json" --output "${1:-$base/synthetic-dist}"
