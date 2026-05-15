import json
import os
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from config import QUEUE_PATH, LOG_PATH


def _load(path: str) -> list:
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return []


def _save_atomic(path: str, data: list) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _print_job(job: dict, index: int, total: int) -> None:
    sep = "─" * 45
    ats = job.get("ats", "other").upper()
    posted = job.get("posted_at", "")[:10] or "N/A"
    print(f"\n{sep}")
    print(f"  [{index}/{total}]")
    print(f"  Company   : {job.get('company', 'Unknown')}")
    print(f"  Title     : {job.get('title', 'Unknown')}")
    print(f"  Score     : {job.get('score', 0)}")
    print(f"  Location  : {job.get('location', 'N/A')}")
    print(f"  ATS       : {ats}")
    print(f"  Posted    : {posted}")
    print(f"  Link      : {job.get('apply_link', 'N/A')}")
    print(sep)


def run_queue(queue_path: str = None, log_path: str = None) -> None:
    queue_path = queue_path or QUEUE_PATH
    log_path = log_path or LOG_PATH

    queue = _load(queue_path)
    log = _load(log_path)

    pending = [j for j in queue if j.get("status") == "pending"]
    total = len(pending)

    if total == 0:
        print("[queue] No pending jobs. Run with discovery first or check queue.json.")
        return

    print(f"[queue] {total} pending jobs to review.")

    for i, job in enumerate(pending, 1):
        _print_job(job, i, total)

        while True:
            try:
                choice = input("  Apply? [y / n / skip / quit] > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n[queue] Interrupted. Saving and exiting.")
                _save_atomic(queue_path, queue)
                return

            if choice == "y":
                link = job.get("apply_link")
                if link:
                    webbrowser.open(link)
                    print(f"  [queue] Opened in browser.")
                else:
                    print(f"  [queue] No link available.")

                job["status"] = "opened"
                job["acted_at"] = datetime.now(timezone.utc).isoformat()
                log.append({
                    "id": job.get("id"),
                    "title": job.get("title"),
                    "company": job.get("company"),
                    "apply_link": job.get("apply_link"),
                    "opened_at": job["acted_at"],
                })
                _save_atomic(queue_path, queue)
                _save_atomic(log_path, log)
                break

            elif choice == "n":
                job["status"] = "skipped"
                job["acted_at"] = datetime.now(timezone.utc).isoformat()
                _save_atomic(queue_path, queue)
                break

            elif choice == "skip":
                break

            elif choice == "quit":
                print("[queue] Saving and exiting.")
                _save_atomic(queue_path, queue)
                return

            else:
                print("  Please enter y, n, skip, or quit.")

    print(f"\n[queue] Done reviewing all {total} jobs.")
