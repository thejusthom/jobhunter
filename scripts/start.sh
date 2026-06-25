#!/usr/bin/env bash
# Start the server. Backblaze/Litestream disabled - GitHub backup repo only.

set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

# Fresh device with no local DB: pull the latest snapshot from the GitHub backup repo.
if [ ! -f jobhunter.db ]; then
  echo "[backup] No local DB — restoring latest from GitHub backup repo..."
  python restore_db.py || echo "[backup] restore failed, starting fresh"
fi

echo "[backend] Starting server (GitHub backup only; Backblaze disabled)..."
exec python -m uvicorn server:app --host 0.0.0.0 --port 8000
