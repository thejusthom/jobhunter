"""On-demand JobHunter database backup with switchable targets.

The continuous Litestream -> B2 replication ships many small WAL transactions,
which burns Backblaze's free-tier *transaction* cap (not storage — the DB is ~18MB).
This script instead makes ONE compact, consistent snapshot and pushes it wherever
you want, so a backup costs ~1 operation instead of thousands.

Pick targets with the BACKUP_TARGETS env var (comma-separated). Any combination of:

  local   Rotating copies under ./backups/            (no extra deps)
  git     Commit the snapshot into a SEPARATE PRIVATE repo (your main repo is public!)
  s3      Upload a single snapshot to an S3-compatible bucket: Cloudflare R2 or Backblaze B2

Usage:
  python backup_db.py                      # uses BACKUP_TARGETS (default: local)
  python backup_db.py --targets s3         # override for this run (e.g. when B2 limits reset)
  python backup_db.py --targets local,git,s3

Configure via .env (see BACKUP.md for the full list). Nothing here prints secrets.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("BACKUP_SOURCE_DB", "jobhunter.db"))


def _log(msg: str) -> None:
    print(f"[backup] {msg}", flush=True)


def make_snapshot(dst: Path) -> Path:
    """Write a compact, consistent copy of the live DB to `dst` via VACUUM INTO.

    VACUUM INTO takes a read snapshot, so it is safe to run while the server is
    using the database (WAL mode), and the result has no -wal/-shm sidecars.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Source DB not found: {DB_PATH.resolve()}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    con = sqlite3.connect(str(DB_PATH))
    try:
        con.execute("VACUUM INTO ?", (str(dst),))
    finally:
        con.close()
    size_mb = dst.stat().st_size / 1_048_576
    _log(f"snapshot created: {dst.name} ({size_mb:.1f} MB)")
    return dst


# --------------------------------------------------------------------------- #
# Targets
# --------------------------------------------------------------------------- #

def target_local(snapshot: Path, stamp: str) -> None:
    out_dir = Path(os.getenv("BACKUP_LOCAL_DIR", "backups"))
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"jobhunter-{stamp}.db"
    shutil.copy2(snapshot, dest)
    _log(f"local -> {dest}")

    keep = int(os.getenv("BACKUP_LOCAL_KEEP", "10"))
    snaps = sorted(out_dir.glob("jobhunter-*.db"))
    for old in snaps[:-keep] if keep > 0 else []:
        old.unlink()
        _log(f"local rotated out {old.name}")


def target_git(snapshot: Path, stamp: str) -> None:
    repo = os.getenv("BACKUP_GIT_DIR")
    if not repo:
        raise RuntimeError(
            "git target needs BACKUP_GIT_DIR pointing at a local clone of a PRIVATE backup repo. "
            "Your main repo is public — do NOT point this at it."
        )
    repo_dir = Path(repo)
    if not (repo_dir / ".git").exists():
        raise RuntimeError(f"BACKUP_GIT_DIR is not a git repo: {repo_dir}")

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo_dir, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # Catch up to whatever another device pushed last, so we don't diverge.
    if os.getenv("BACKUP_GIT_PUSH", "true").lower() != "false":
        try:
            git("pull", "--ff-only")
        except subprocess.CalledProcessError:
            _log("git -> pull skipped (no upstream yet or histories diverged)")

    filename = os.getenv("BACKUP_GIT_FILENAME", "jobhunter.db")
    dest = repo_dir / filename
    shutil.copy2(snapshot, dest)

    git("add", filename)
    # Nothing changed? then skip the commit/push quietly.
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir,
                            capture_output=True, text=True).stdout.strip()
    if not status:
        _log("git -> no changes since last backup, skipping")
        return
    git("commit", "-m", f"DB backup {stamp}")
    if os.getenv("BACKUP_GIT_PUSH", "true").lower() != "false":
        try:
            git("push")
        except subprocess.CalledProcessError:
            # First push / no upstream yet — set it. Requires the remote repo to exist.
            branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                    cwd=repo_dir, capture_output=True, text=True).stdout.strip() or "main"
            git("push", "-u", "origin", branch)
        _log(f"git -> committed & pushed to {repo_dir}")
    else:
        _log(f"git -> committed (push disabled) in {repo_dir}")


def _s3_settings() -> dict:
    """Resolve S3 settings for the chosen provider (r2 or b2)."""
    provider = os.getenv("BACKUP_S3_PROVIDER", "b2").lower()
    if provider == "r2":
        endpoint = os.getenv("R2_ENDPOINT", "")
        cfg = {
            "endpoint": endpoint,
            "bucket": os.getenv("R2_BUCKET", ""),
            "key_id": os.getenv("R2_ACCESS_KEY_ID", ""),
            "secret": os.getenv("R2_SECRET_ACCESS_KEY", ""),
            "region": os.getenv("R2_REGION", "auto"),
        }
    else:  # b2 — reuse the existing Litestream credentials
        cfg = {
            "endpoint": os.getenv("LITESTREAM_REPLICA_ENDPOINT", ""),
            "bucket": os.getenv("LITESTREAM_REPLICA_BUCKET", ""),
            "key_id": os.getenv("LITESTREAM_ACCESS_KEY_ID", ""),
            "secret": os.getenv("LITESTREAM_SECRET_ACCESS_KEY", ""),
            "region": os.getenv("LITESTREAM_REGION", "us-west-000"),
        }
    cfg["provider"] = provider
    missing = [k for k in ("endpoint", "bucket", "key_id", "secret") if not cfg[k]]
    if missing:
        raise RuntimeError(f"s3 target ({provider}) missing env: {', '.join(missing)}")
    if not cfg["endpoint"].startswith("http"):
        cfg["endpoint"] = "https://" + cfg["endpoint"]
    return cfg


def target_s3(snapshot: Path, stamp: str) -> None:
    try:
        import boto3  # lazy: only needed for the cloud target
    except ImportError:
        raise RuntimeError(
            "s3 target needs boto3. Install once with:  pip install boto3"
        )
    cfg = _s3_settings()
    prefix = os.getenv("BACKUP_S3_PREFIX", "snapshots/").strip("/")
    key = f"{prefix}/jobhunter-{stamp}.db" if prefix else f"jobhunter-{stamp}.db"

    client = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["key_id"],
        aws_secret_access_key=cfg["secret"],
        region_name=cfg["region"],
    )
    client.upload_file(str(snapshot), cfg["bucket"], key)
    _log(f"s3 ({cfg['provider']}) -> {cfg['bucket']}/{key}")


TARGETS = {
    "local": target_local,
    "git": target_git,
    "s3": target_s3,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the JobHunter SQLite DB.")
    parser.add_argument("--targets", help="Comma list overriding BACKUP_TARGETS (local,git,s3)")
    parser.add_argument("--keep-temp", action="store_true", help="Don't delete the temp snapshot")
    args = parser.parse_args()

    targets_raw = args.targets or os.getenv("BACKUP_TARGETS", "local")
    targets = [t.strip() for t in targets_raw.split(",") if t.strip()]
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        _log(f"unknown target(s): {', '.join(unknown)} (valid: local, git, s3)")
        return 2
    if not targets:
        _log("no targets selected")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tmp_dir = Path(tempfile.mkdtemp(prefix="jobhunter-backup-"))
    snapshot = tmp_dir / "snapshot.db"

    failures = 0
    try:
        make_snapshot(snapshot)
        for t in targets:
            try:
                TARGETS[t](snapshot, stamp)
            except Exception as e:  # one target failing shouldn't abort the others
                failures += 1
                _log(f"{t} FAILED: {e}")
    finally:
        if not args.keep_temp:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if failures:
        _log(f"done with {failures} failed target(s)")
        return 1
    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
