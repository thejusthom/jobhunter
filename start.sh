#!/usr/bin/env bash
# Start the server with Litestream replication.
# Always pulls the latest DB from B2, keeps whichever copy has more data.

set -euo pipefail
cd "$(dirname "$0")"
set -a; source .env; set +a

count_jobs() {
  python -c "import sqlite3;c=sqlite3.connect('$1');print(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])" 2>/dev/null || echo "0"
}

if [ -f jobhunter.db ]; then
  echo "[litestream] Pulling latest DB from B2..."
  cp jobhunter.db jobhunter.db.local-backup
  ./litestream.exe restore -config litestream.yml -o jobhunter.db.b2 jobhunter.db 2>/dev/null || true
  if [ -f jobhunter.db.b2 ]; then
    LOCAL_JOBS=$(count_jobs jobhunter.db)
    B2_JOBS=$(count_jobs jobhunter.db.b2)
    echo "[litestream] Local: $LOCAL_JOBS jobs, B2: $B2_JOBS jobs"
    if [ "$B2_JOBS" -ge "$LOCAL_JOBS" ]; then
      echo "[litestream] Using B2 version (newer or equal)"
      mv jobhunter.db.b2 jobhunter.db
    else
      echo "[litestream] Keeping local version (has more data)"
      rm -f jobhunter.db.b2
    fi
  else
    echo "[litestream] No B2 backup found, using local DB"
  fi
else
  echo "[litestream] No local DB — restoring from B2..."
  ./litestream.exe restore -config litestream.yml jobhunter.db || echo "[litestream] No backup found, starting fresh"
fi

JOB_COUNT=$(count_jobs jobhunter.db)
if [ "$JOB_COUNT" = "0" ]; then
  echo "[WARNING] DB has 0 jobs — starting WITHOUT replication to protect B2 backup."
  exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
fi

echo "[litestream] Starting replication + server ($JOB_COUNT jobs)..."
exec ./litestream.exe replicate -config litestream.yml -exec "python -m uvicorn server:app --host 0.0.0.0 --port 8000"
