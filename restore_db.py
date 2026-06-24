"""Restore jobhunter.db from the private git backup repo (cross-device).

On a second device: clone both repos, then run this to pull the latest snapshot
into place. It safely sidelines your current DB first.

  python restore_db.py            # pull latest from BACKUP_GIT_DIR and install it
  python restore_db.py --no-pull  # use whatever snapshot is already in the backup repo

Stop the server before restoring.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("BACKUP_SOURCE_DB", "jobhunter.db"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore the DB from the git backup repo.")
    parser.add_argument("--no-pull", action="store_true", help="Skip git pull in the backup repo")
    args = parser.parse_args()

    repo = os.getenv("BACKUP_GIT_DIR")
    if not repo:
        print("[restore] BACKUP_GIT_DIR is not set in .env"); return 2
    repo_dir = Path(repo)
    filename = os.getenv("BACKUP_GIT_FILENAME", "jobhunter.db")
    src = repo_dir / filename

    if not args.no_pull:
        try:
            subprocess.run(["git", "pull", "--ff-only"], cwd=repo_dir, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print("[restore] pulled latest from backup remote")
        except subprocess.CalledProcessError as e:
            print(f"[restore] git pull failed ({e}); using local copy")

    if not src.exists():
        print(f"[restore] no snapshot found at {src}"); return 1

    # Sideline the current DB (and its WAL sidecars) before overwriting.
    if DB_PATH.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        side = DB_PATH.with_name(f"{DB_PATH.stem}.pre-restore-{stamp}.db")
        shutil.move(str(DB_PATH), side)
        print(f"[restore] current DB moved aside -> {side.name}")
    for sidecar in (DB_PATH.with_name(DB_PATH.name + "-wal"), DB_PATH.with_name(DB_PATH.name + "-shm")):
        if sidecar.exists():
            sidecar.unlink()

    shutil.copy2(src, DB_PATH)
    size_mb = DB_PATH.stat().st_size / 1_048_576
    print(f"[restore] installed {src} -> {DB_PATH} ({size_mb:.1f} MB). Start the server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
