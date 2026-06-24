# Database backups

The live DB is `jobhunter.db` (~18 MB). The old approach — continuous Litestream → Backblaze B2
— ships a constant stream of small WAL transactions, which is what exhausts B2's **free-tier
transaction cap** (storage is never the problem at this size).

`backup_db.py` replaces that with **on-demand, single-file snapshots**: one `VACUUM INTO` copy,
pushed wherever you choose. One backup ≈ one operation instead of thousands. It's safe to run while
the server is using the DB.

## Choose target(s) with one env flag

Set `BACKUP_TARGETS` in `.env` (comma-separated). Mix and match:

| Target | What it does | Extra setup |
|--------|--------------|-------------|
| `local` | Rotating copies in `./backups/` (gitignored) | none |
| `git`   | Commits the snapshot into a **separate private repo** | a private repo + `BACKUP_GIT_DIR` |
| `s3`    | Uploads one snapshot to Cloudflare **R2** or Backblaze **B2** | `pip install boto3` + keys |

```env
# .env
BACKUP_TARGETS=local            # e.g. local   or   local,git   or   s3
```

Run it:

```bash
python backup_db.py                    # uses BACKUP_TARGETS
python backup_db.py --targets s3       # one-off override (e.g. when B2 limits reset)
python backup_db.py --targets local,git,s3
```

## Automatic backup on `git push`

A `pre-push` hook is installed at `.git/hooks/pre-push` (tracked copy in `hooks/pre-push`). Every
push runs `backup_db.py` first; if the backup fails it prints a warning but **never blocks the push**.
Reinstall after a fresh clone:

```bash
cp hooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

## Target configuration

### local
```env
BACKUP_LOCAL_DIR=backups        # default
BACKUP_LOCAL_KEEP=10            # keep newest N, default 10 (0 = keep all)
```

### git  (⚠ your main repo `thejusthom/jobhunter` is PUBLIC — never point this at it)
1. Create a **private** repo, e.g. `jobhunter-backups`, and clone it somewhere.
2. Point the script at that clone:
```env
BACKUP_GIT_DIR=../jobhunter-backups
BACKUP_GIT_FILENAME=jobhunter.db   # default; committed under this stable name each time
BACKUP_GIT_PUSH=true               # set false to commit locally without pushing
```
History grows by ~18 MB per changed push; use this if you want versioned restore points.

### s3 — Cloudflare R2 (recommended cloud option; very high free limits, zero egress)
```env
BACKUP_TARGETS=s3
BACKUP_S3_PROVIDER=r2
R2_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com
R2_BUCKET=jobhunter-db
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
# R2_REGION=auto                 # default
BACKUP_S3_PREFIX=snapshots/      # default
```

### s3 — Backblaze B2 (reuses your existing Litestream credentials)
```env
BACKUP_TARGETS=s3
BACKUP_S3_PROVIDER=b2
# Uses the keys already in .env:
#   LITESTREAM_REPLICA_ENDPOINT, LITESTREAM_REPLICA_BUCKET,
#   LITESTREAM_ACCESS_KEY_ID, LITESTREAM_SECRET_ACCESS_KEY
```
Install the dependency once: `pip install boto3`.

## Cross-device sync via a private git backup repo

The DB is backed up into a **separate private repo** (`jobhunter-backups`), so any device can pull
the latest snapshot. The active config is already set in `.env`:

```env
BACKUP_TARGETS=local,git
BACKUP_GIT_DIR=../jobhunter-backups
```

### One-time: create the private repo (this device)
1. On GitHub: **New repository** → name `jobhunter-backups` → **Private** → create it **empty**
   (no README/.gitignore — the local repo already has commits).
2. Push the local backup repo that's already prepared next to this project:
   ```bash
   git -C ../jobhunter-backups push -u origin main
   ```

### On every other device
```bash
# 1. clone both repos side by side
git clone git@github.com:thejusthom/jobhunter.git
git clone git@github.com:thejusthom/jobhunter-backups.git
# (keep them as siblings so ../jobhunter-backups resolves)

# 2. set up the app (venv, deps) and copy the same backup lines into that device's .env

# 3. pull the latest DB into place
cd jobhunter
python restore_db.py
```

### Day-to-day
- **Before working on a device:** `python restore_db.py` to grab the newest DB.
- **When you `git push` code:** the pre-push hook snapshots the DB and pushes it to the backup repo
  automatically (it `git pull --ff-only`s first to stay in sync).
- **Manual backup anytime:** `python backup_db.py` (targets come from `.env`).

> Work on one device at a time and sync between switches. The DB is a binary file, so if two devices
> both change it without pulling in between, git can't auto-merge — newest push wins and the other
> device must `restore_db.py` to catch up.

## Restoring

- **local / git**: copy the chosen `jobhunter-*.db` (or `jobhunter.db`) over `jobhunter.db` while the
  server is stopped. Delete any stale `jobhunter.db-wal` / `-shm` first.
- **s3**: download the object, then same as above.

## Turning off continuous Litestream

Once you're happy with on-demand snapshots you can stop running `litestream.exe replicate` (remove/skip
it in `launch.bat` / `launch_backend.bat`). `litestream.yml` can stay for reference. This is what
actually stops the B2 transaction drain.
```
