#!/usr/bin/env bash
# Start the server with Litestream replication.
# Safety: refuses to replicate an empty DB to protect the B2 backup.

set -euo pipefail
cd "$(dirname "$0")"

# Load env vars
set -a; source .env; set +a

# Restore DB from B2 if it doesn't exist locally (fresh device)
if [ ! -f jobhunter.db ]; then
  echo "[litestream] No local DB found — restoring from B2..."
  ./litestream.exe restore -config litestream.yml jobhunter.db || echo "[litestream] No backup found, starting fresh"
fi

# Safety check: don't replicate an empty DB
JOB_COUNT=$(python -c "import sqlite3;c=sqlite3.connect('jobhunter.db');print(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])" 2>/dev/null || echo "0")

if [ "$JOB_COUNT" = "0" ]; then
  echo "[WARNING] DB has 0 jobs — starting WITHOUT replication to protect B2 backup."
  echo "[WARNING] If this is expected, delete jobhunter.db and restart to restore from B2."
  exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
fi

echo "[litestream] Starting replication + server ($JOB_COUNT jobs in DB)..."
exec ./litestream.exe replicate -config litestream.yml -exec "python -m uvicorn server:app --host 0.0.0.0 --port 8000"
