#!/usr/bin/env bash
# macOS / Linux equivalent of share_demo.bat.
#
#   ./share_demo.sh
#
# Starts the server, opens a free Cloudflare quick tunnel, then prints the
# public link on its own and copies it to the clipboard. The link works only
# while this script is running, and you get a different one each time.

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

if ! command -v cloudflared >/dev/null 2>&1; then
    echo "cloudflared is not installed. It is what creates the public link."
    echo ""
    echo "  macOS:  brew install cloudflared"
    echo "  Linux:  see https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
fi

if [ ! -f procurement.db ]; then
    echo "No database found. Creating demo data, this takes a few seconds..."
    "$PY" seed.py
    echo ""
fi

PORT=5000
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:5000 -sTCP:LISTEN >/dev/null 2>&1; then
    PORT=5001
fi
export PORT
LOCAL_URL="http://localhost:$PORT"

SERVER_PID=""
TUNNEL_PID=""
LOG="$(mktemp -t procurement_tunnel.XXXXXX)"

cleanup() {
    echo ""
    echo "Shutting down..."
    [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
    rm -f "$LOG"
    echo "Link is down and the server has stopped."
}
trap cleanup EXIT INT TERM

# Reuse an already-running server rather than starting a second one.
if curl -s -o /dev/null "$LOCAL_URL" 2>/dev/null; then
    echo "A portal server is already running on port $PORT - reusing it."
else
    echo "Starting the portal server..."
    "$PY" app.py >/dev/null 2>&1 &
    SERVER_PID=$!
    ready=""
    for _ in $(seq 1 30); do
        sleep 0.5
        if curl -s -o /dev/null "$LOCAL_URL" 2>/dev/null; then ready=1; break; fi
    done
    if [ -z "$ready" ]; then
        echo "The server did not start. Run ./start_demo.sh on its own to see the error."
        exit 1
    fi
    echo "  Server is up on $LOCAL_URL"
fi

echo "Opening the public tunnel, this usually takes about 10 seconds..."
cloudflared tunnel --url "$LOCAL_URL" --logfile "$LOG" >/dev/null 2>&1 &
TUNNEL_PID=$!

URL=""
for _ in $(seq 1 60); do
    sleep 1
    URL="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" 2>/dev/null | head -1 || true)"
    [ -n "$URL" ] && break
    kill -0 "$TUNNEL_PID" 2>/dev/null || break
done

if [ -z "$URL" ]; then
    echo ""
    echo "Could not get a tunnel link. Check your internet connection, then look at: $LOG"
    exit 1
fi

echo "$URL" > LAST_SHARE_LINK.txt
if command -v pbcopy >/dev/null 2>&1; then printf '%s' "$URL" | pbcopy
elif command -v xclip >/dev/null 2>&1; then printf '%s' "$URL" | xclip -selection clipboard
fi

echo ""
echo "=================================================================="
echo ""
echo "  SEND THIS LINK TO YOUR TEAMMATES:"
echo ""
echo "    $URL"
echo ""
echo "  Copied to your clipboard. Also saved in LAST_SHARE_LINK.txt"
echo ""
echo "=================================================================="
echo ""
echo "  Send these logins with it:"
echo "    Farmer   9000000001   (clean record)"
echo "    Farmer   9000000002   (has data mismatches)"
echo "    OTP      123456"
echo "    Staff    ADMIN / demo123"
echo ""
echo "=================================================================="
echo ""
echo "  Press Ctrl+C to stop sharing."
echo ""

wait "$TUNNEL_PID"
