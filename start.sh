#!/usr/bin/env bash
# Start the server with Litestream replication.
# Usage: bash start.sh
#   Litestream replicates jobhunter.db to Backblaze B2 in the background
#   and runs the FastAPI server as a child process.

set -euo pipefail
cd "$(dirname "$0")"

# Load env vars
set -a; source .env; set +a

# Restore DB from B2 if it doesn't exist locally (fresh device)
if [ ! -f jobhunter.db ]; then
  echo "[litestream] No local DB found — restoring from B2..."
  ./litestream.exe restore -config litestream.yml jobhunter.db || echo "[litestream] No backup found, starting fresh"
fi

echo "[litestream] Starting replication + server..."
exec ./litestream.exe replicate -config litestream.yml -exec "python -m uvicorn server:app --host 0.0.0.0 --port 8000"
