import sys
import argparse
import os
from pathlib import Path

# Windows terminal defaults to cp1252 which can't print em-dashes from job titles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

# Patch discovery.py globals to respect config paths before importing
import config
os.environ.setdefault("JSEARCH_API_KEY", config.JSEARCH_API_KEY)

import discovery
discovery.JSEARCH_KEY = config.JSEARCH_API_KEY
discovery.SCORE_THRESHOLD = config.MIN_RELEVANCE_SCORE
discovery.QUEUE_PATH = Path(config.QUEUE_PATH)
discovery.LOG_PATH = Path(config.LOG_PATH)
discovery.BLACKLIST_PATH = Path(config.BLACKLIST_PATH)

from discovery import discover
from ats_discovery import discover_from_ats
from queue_runner import run_queue


def main():
    parser = argparse.ArgumentParser(description="JobHunter — discover and queue jobs to apply")
    parser.add_argument("--skip-discovery", action="store_true", help="Skip all discovery, go straight to queue")
    parser.add_argument("--skip-jsearch",   action="store_true", help="Skip JSearch, run ATS discovery only")
    parser.add_argument("--skip-ats",       action="store_true", help="Skip ATS discovery, run JSearch only")
    parser.add_argument("--queries", type=str, default=None, help="Comma-separated JSearch queries (overrides .env)")
    parser.add_argument("--location", type=str, default=None, help="JSearch location (overrides .env)")
    args = parser.parse_args()

    total_new = 0

    if not args.skip_discovery:
        # --- JSearch ---
        if not args.skip_jsearch:
            if not config.JSEARCH_API_KEY:
                print("[run] WARNING: JSEARCH_API_KEY not set — skipping JSearch.")
            else:
                queries = (
                    [q.strip() for q in args.queries.split(",") if q.strip()]
                    if args.queries
                    else config.SEARCH_KEYWORDS
                )
                location = args.location or config.SEARCH_LOCATION
                print(f"[run] JSearch: {len(queries)} queries in '{location}'")
                jsearch_jobs = discover(queries=queries, location=location)
                total_new += len(jsearch_jobs)
                print(f"[run] JSearch: {len(jsearch_jobs)} new jobs queued.\n")

        # --- ATS (Greenhouse + Lever) ---
        if not args.skip_ats:
            print("[run] ATS: querying Greenhouse + Lever company boards...")
            ats_jobs = discover_from_ats()
            total_new += len(ats_jobs)
            print(f"[run] ATS: {len(ats_jobs)} new jobs queued.\n")

        print(f"[run] Total new jobs this run: {total_new}\n")

    run_queue(queue_path=config.QUEUE_PATH, log_path=config.LOG_PATH)


if __name__ == "__main__":
    main()
