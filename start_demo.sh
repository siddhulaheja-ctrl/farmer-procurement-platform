#!/usr/bin/env bash
# macOS / Linux equivalent of start_demo.bat.
#
#   chmod +x start_demo.sh     (once, if needed)
#   ./start_demo.sh
#
# Installs dependencies if they are missing, seeds the database on first run,
# then starts the server and opens a browser.

set -euo pipefail
cd "$(dirname "$0")"

# --- find a usable Python ---------------------------------------------------
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
    echo "On macOS:  brew install python3     (or install from python.org)"
    exit 1
fi

# --- dependencies -----------------------------------------------------------
if ! "$PY" -c "import flask, faker" >/dev/null 2>&1; then
    echo "Installing dependencies (Flask, Faker, requests)..."
    "$PY" -m pip install --quiet -r requirements.txt || {
        echo ""
        echo "pip install failed. If your Python is externally managed, use a virtualenv:"
        echo "    $PY -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    }
    echo ""
fi

# --- database ---------------------------------------------------------------
if [ ! -f procurement.db ]; then
    echo "No database found. Creating demo data, this takes a few seconds..."
    "$PY" seed.py
    echo ""
fi

# --- pick a port ------------------------------------------------------------
# macOS Monterey and later run AirPlay Receiver on port 5000, so the usual
# Flask default collides. Step aside rather than fail with a confusing error.
PORT=5000
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:5000 -sTCP:LISTEN >/dev/null 2>&1; then
    PORT=5001
    echo "Port 5000 is already in use - on macOS that is usually AirPlay Receiver."
    echo "Using port $PORT instead."
    echo ""
fi
export PORT
URL="http://localhost:$PORT"

echo "=========================================================="
echo "  Smart Farmer Procurement Portal"
echo "=========================================================="
echo ""
echo "  On this computer:   $URL"
echo ""
echo "  Farmer login: 9000000001  or  9000000002    OTP: 123456"
echo "  Staff login:  ADMIN / demo123"
echo ""
echo "  Press Ctrl+C to stop the server."
echo "=========================================================="
echo ""

# Open the browser once the server is actually accepting connections.
(
    for _ in $(seq 1 30); do
        sleep 0.5
        if curl -s -o /dev/null "$URL" 2>/dev/null; then
            if command -v open >/dev/null 2>&1; then open "$URL"
            elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
            fi
            break
        fi
    done
) &

exec "$PY" app.py
