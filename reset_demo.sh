#!/usr/bin/env bash
# Wipes the database and regenerates fresh demo data.
# Run this before a presentation so the demo starts from a known state.

set -euo pipefail
cd "$(dirname "$0")"

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            PY="$candidate"
            break
        fi
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.9 or newer is required but was not found."
    exit 1
fi

"$PY" seed.py
