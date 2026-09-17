#!/usr/bin/env bash

set -e

ROOT="$HOME/sona-assistive-glasses"
PI_DIR="$ROOT/pi"
G2_DIR="$ROOT/g2"

BACKEND_PID=""
VITE_PID=""

# ==========================================
# Get Raspberry Pi IPv4 address
# ==========================================
PI_IP=$(hostname -I | tr ' ' '\n' | grep -m1 -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$')

if [ -z "$PI_IP" ]; then
    echo "ERROR: Could not find Raspberry Pi IP address."
    exit 1
fi

echo
echo "=========================================="
echo "             SONA STARTING"
echo "=========================================="
echo "Pi IP     : $PI_IP"
echo "Backend   : ws://$PI_IP:8765/ws"
echo "G2 Server : http://$PI_IP:5173"
echo "=========================================="
echo


# ==========================================
# Update G2 app.json WebSocket whitelist
# ==========================================
python3 - "$G2_DIR/app.json" "$PI_IP" <<'PY'
import json
import sys

path = sys.argv[1]
ip = sys.argv[2]

with open(path, "r") as f:
    data = json.load(f)

for permission in data.get("permissions", []):
    if permission.get("name") == "network":
        permission["whitelist"] = [
            f"ws://{ip}:8765"
        ]

with open(path, "w") as f:
    json.dump(data, f, indent=2)

print(f"✓ G2 WebSocket whitelist → ws://{ip}:8765")
PY


# ==========================================
# Stop everything on Ctrl+C
# ==========================================
cleanup() {

    echo
    echo "Stopping SONA..."

    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi

    if [ -n "$VITE_PID" ]; then
        kill "$VITE_PID" 2>/dev/null || true
    fi

    echo "SONA stopped."
}

trap cleanup EXIT INT TERM


# ==========================================
# Start SONA backend
# ==========================================
echo
echo "Starting SONA backend..."

cd "$PI_DIR"

.venv/bin/python -m sona.app &

BACKEND_PID=$!

sleep 3


# ==========================================
# Start G2 Vite server
# ==========================================
echo
echo "Starting G2 server..."

cd "$G2_DIR"

if [ ! -d node_modules ]; then
    echo "Installing npm dependencies..."
    npm install
fi

VITE_PI_WS="ws://$PI_IP:8765/ws" \
VITE_HMR_HOST="$PI_IP" \
npm run dev -- --host 0.0.0.0 &

VITE_PID=$!


# ==========================================
# Wait for Vite
# ==========================================
echo
echo "Waiting for G2 server..."

for i in $(seq 1 20); do

    if curl -s \
        "http://127.0.0.1:5173" \
        >/dev/null 2>&1; then

        echo "✓ G2 server is ready."
        break
    fi

    sleep 1

done


echo
echo "=========================================="
echo "              SONA READY"
echo "=========================================="
echo
echo "Backend:"
echo "ws://$PI_IP:8765/ws"
echo
echo "G2:"
echo "http://$PI_IP:5173"
echo
echo "=========================================="
echo


# ==========================================
# Generate Even Hub QR
# ==========================================
echo "Generating Even Hub QR..."
echo

cd "$G2_DIR"

npx evenhub qr \
    --url "http://$PI_IP:5173"

echo
echo "Scan the QR in Even Hub Prototype Mode."
echo
echo "Press Ctrl+C to stop everything."
echo


# ==========================================
# Keep servers alive
# ==========================================
wait
