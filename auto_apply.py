"""
Auto-Apply: Real browser automation for job applications.
Connects to your Chrome (with extensions) via remote debugging,
then clicks through application forms automatically.

Setup: Close Chrome, then run this script. It will:
1. Launch YOUR Chrome with your profile + extensions + remote debugging
2. Connect Playwright to control it
3. Open each job's apply page
4. Wait for your extension to fill fields
5. Auto-click Next/Continue/Submit through each step
6. Pause when it needs your attention (CAPTCHA, custom questions)

Usage:
  python auto_apply.py                    # All scored jobs >= 60%
  python auto_apply.py --min-score 70     # Only 70%+ matches
  python auto_apply.py --limit 5          # Apply to 5 jobs max
  python auto_apply.py --job-id abc123    # One specific job
"""

import argparse
import json
import time
import sys
import os
import subprocess
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("Install playwright: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

DB_PATH = Path(__file__).parent / "jobhunter.db"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not Path(CHROME_PATH).exists():
    CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data")
DEBUG_PORT = 9222


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_jobs(min_score=0, limit=50, job_id=None):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if job_id:
        cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    else:
        cur.execute(
            "SELECT * FROM jobs WHERE status = 'pending' AND match_pct IS NOT NULL AND match_pct >= ? AND apply_link IS NOT NULL AND apply_link != '' ORDER BY match_pct DESC LIMIT ?",
            (min_score, limit),
        )
    jobs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jobs


def mark_applied(job):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("UPDATE jobs SET status = 'applied' WHERE id = ?", (job["id"],))
    cur.execute(
        """INSERT OR IGNORE INTO applications (job_id, title, company, location, apply_link, source, resume_used, status, applied_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'applied', ?)""",
        (job["id"], job.get("title", ""), job.get("company", ""), job.get("location", ""),
         job.get("apply_link", ""), "auto_apply", job.get("recommended_resume", ""), now),
    )
    conn.commit()
    conn.close()


def mark_skipped(job, reason="auto_apply_skip"):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("UPDATE jobs SET status = 'skipped', notes = ? WHERE id = ?", (reason, job["id"]))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Chrome launcher
# ---------------------------------------------------------------------------

def launch_chrome():
    """Launch Chrome with remote debugging enabled using the user's profile."""
    print(f"Launching Chrome with remote debugging on port {DEBUG_PORT}...")
    print(f"  Profile: {USER_DATA_DIR}")
    print(f"  Chrome: {CHROME_PATH}\n")

    proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--profile-directory=Default",
        "--no-first-run",
        "--restore-last-session",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for Chrome to start
    time.sleep(3)
    return proc


# ---------------------------------------------------------------------------
# ATS detection + button selectors
# ---------------------------------------------------------------------------

def detect_ats(url):
    url = url.lower()
    if "myworkdayjobs.com" in url:
        return "workday"
    if "greenhouse.io" in url or "boards.greenhouse" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "ashbyhq.com" in url:
        return "ashby"
    if "smartrecruiters.com" in url:
        return "smartrecruiters"
    return "unknown"


def find_and_click(page, selectors, timeout=3000):
    """Try each selector, click the first visible+enabled one."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout) and loc.is_enabled():
                loc.scroll_into_view_if_needed()
                time.sleep(0.3)
                loc.click()
                return True
        except Exception:
            continue
    return False


def check_success(page):
    """Check if application was submitted."""
    success_texts = [
        "application submitted", "thank you for applying", "thanks for applying",
        "application received", "your application has been submitted",
        "successfully submitted", "we have received your application",
        "application has been received", "thank you for your interest",
        "application complete",
    ]
    try:
        body = page.locator("body").inner_text(timeout=2000).lower()
        return any(t in body for t in success_texts)
    except:
        return False


def has_errors(page):
    """Check for form validation errors."""
    error_selectors = [
        '[data-automation-id="errorMessage"]',
        '.css-1lyuypv',  # Workday inline error
        '.field-error',
        '.error-message',
        '[role="alert"]',
    ]
    for sel in error_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=500):
                return True
        except:
            pass
    return False


def has_captcha(page):
    """Check for CAPTCHA."""
    for sel in ['iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]', '.g-recaptcha', '#captcha']:
        try:
            if page.locator(sel).count() > 0:
                return True
        except:
            pass
    return False


def has_file_upload(page):
    """Check for visible file upload fields."""
    try:
        uploads = page.locator('input[type="file"]').all()
        for u in uploads:
            if u.is_visible():
                return True
    except:
        pass
    return False


# ---------------------------------------------------------------------------
# Workday automation (the big one — multi-step wizard)
# ---------------------------------------------------------------------------

WORKDAY_APPLY = [
    'a[data-automation-id="jobApply"]',
    'button[data-automation-id="jobApply"]',
    'a:has-text("Apply")',
]

WORKDAY_USE_WITHOUT_ACCOUNT = [
    'button:has-text("Use Without an Account")',
    'button:has-text("Use My Last Application")',
    'a:has-text("Use Without an Account")',
]

WORKDAY_NEXT = [
    'button[data-automation-id="bottom-navigation-next-button"]',
]

WORKDAY_SUBMIT = [
    'button[data-automation-id="bottom-navigation-next-button"]:has-text("Submit")',
]


def apply_workday(page, ext_wait):
    """Automate Workday multi-step application."""
    print("    [workday] Starting Workday flow")

    # Step 1: Click Apply
    time.sleep(2)
    if not find_and_click(page, WORKDAY_APPLY):
        print("    [workday] No Apply button found, might already be on the form")

    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass
    time.sleep(2)

    # Step 2: "Use Without an Account" if shown
    find_and_click(page, WORKDAY_USE_WITHOUT_ACCOUNT, timeout=3000)
    time.sleep(2)

    # Step 3: Click through form steps
    for step in range(10):
        print(f"    [workday] Step {step + 1}")

        # Wait for extension to fill
        print(f"    [workday] Waiting {ext_wait}s for extension to fill...")
        time.sleep(ext_wait)

        # Check if done
        if check_success(page):
            return "success"

        # Check blockers
        if has_captcha(page):
            print("    [workday] CAPTCHA detected!")
            return "needs_attention"

        # Check for errors (extension might not have filled everything)
        if has_errors(page):
            print("    [workday] Form errors detected, waiting more...")
            time.sleep(ext_wait)
            if has_errors(page):
                return "needs_attention"

        # Try Submit first (if we're on the last page)
        if find_and_click(page, WORKDAY_SUBMIT, timeout=1000):
            print("    [workday] Clicked Submit!")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeout:
                pass
            time.sleep(3)
            if check_success(page):
                return "success"
            continue

        # Try Next
        if find_and_click(page, WORKDAY_NEXT, timeout=2000):
            print("    [workday] Clicked Next")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PWTimeout:
                pass
            time.sleep(2)
            continue

        # No buttons found
        print("    [workday] No Next/Submit button found")
        return "needs_attention"

    return "needs_attention"


# ---------------------------------------------------------------------------
# Greenhouse / Lever / Ashby (single-page forms)
# ---------------------------------------------------------------------------

SINGLE_PAGE_SUBMIT = [
    '#submit_app',
    'button:has-text("Submit Application")',
    'button:has-text("Submit application")',
    'button.postings-btn[type="submit"]',
    'button:has-text("Submit your application")',
    'button[type="submit"]:has-text("Submit")',
    'input[type="submit"][value*="Submit"]',
    'button:has-text("Submit")',
    'button:has-text("Apply")',
    'input[type="submit"]',
]

LEVER_APPLY = [
    'a.postings-btn:has-text("Apply")',
    'a.postings-btn:has-text("Apply for this job")',
]


def apply_single_page(page, ats, ext_wait):
    """Automate single-page application forms (Greenhouse, Lever, Ashby)."""
    print(f"    [{ats}] Single-page form")

    # Lever has an intermediate "Apply" button
    if ats == "lever":
        find_and_click(page, LEVER_APPLY, timeout=3000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PWTimeout:
            pass
        time.sleep(2)

    # Wait for extension
    print(f"    [{ats}] Waiting {ext_wait}s for extension to fill...")
    time.sleep(ext_wait)

    if check_success(page):
        return "success"

    if has_captcha(page):
        return "needs_attention"

    if has_file_upload(page):
        print(f"    [{ats}] File upload detected, needs attention")
        return "needs_attention"

    # Try to submit
    if find_and_click(page, SINGLE_PAGE_SUBMIT, timeout=3000):
        print(f"    [{ats}] Clicked Submit")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass
        time.sleep(3)
        if check_success(page):
            return "success"
        # Might have errors
        if has_errors(page):
            return "needs_attention"
        return "submitted"

    print(f"    [{ats}] No submit button found")
    return "needs_attention"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args):
    jobs = get_jobs(min_score=args.min_score, limit=args.limit, job_id=args.job_id)
    if not jobs:
        print("No scored pending jobs found. Score jobs first (Match % button in the UI).")
        return

    print(f"\n{'='*60}")
    print(f"  Auto-Apply: {len(jobs)} jobs")
    print(f"  Min score: {args.min_score}%  |  Extension wait: {args.ext_wait}s")
    print(f"{'='*60}\n")

    for i, j in enumerate(jobs):
        print(f"  {i+1}. [{j.get('match_pct', '?')}%] {j['title']} @ {j['company']}")

    print()
    confirm = input("Close Chrome first, then type 'go' to start: ").strip().lower()
    if confirm != "go":
        print("Aborted.")
        return

    # Launch Chrome with debugging
    chrome_proc = launch_chrome()

    applied = 0
    skipped = 0

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            print("Connected to Chrome!\n")
        except Exception as e:
            print(f"Failed to connect. Make sure Chrome is closed first.\nError: {e}")
            chrome_proc.terminate()
            return

        context = browser.contexts[0] if browser.contexts else browser.new_context()

        for i, job in enumerate(jobs):
            link = job.get("apply_link", "")
            if not link:
                continue

            print(f"\n{'='*60}")
            print(f"[{i+1}/{len(jobs)}] {job['title']} @ {job['company']} ({job.get('match_pct', '?')}%)")
            print(f"  {link}")

            page = context.new_page()
            try:
                page.goto(link, wait_until="domcontentloaded", timeout=30000)
            except PWTimeout:
                pass
            time.sleep(2)

            ats = detect_ats(page.url)
            print(f"  ATS: {ats}")

            if ats == "workday":
                result = apply_workday(page, args.ext_wait)
            elif ats in ("greenhouse", "lever", "ashby", "smartrecruiters"):
                result = apply_single_page(page, ats, args.ext_wait)
            else:
                print("  Unknown ATS, waiting for extension then trying submit...")
                time.sleep(args.ext_wait)
                result = "needs_attention"
                if find_and_click(page, SINGLE_PAGE_SUBMIT, timeout=3000):
                    time.sleep(3)
                    if check_success(page):
                        result = "success"

            if result in ("success", "submitted"):
                print(f"  >>> Application submitted!")
                mark_applied(job)
                applied += 1
                time.sleep(2)
                page.close()
            else:
                print(f"  >>> Needs your attention. Complete manually.")
                input("  Press Enter when done (a=applied, s=skip, q=quit): ")
                action = input("  Result? (a/s/q): ").strip().lower()
                if action == "a":
                    mark_applied(job)
                    applied += 1
                    page.close()
                elif action == "q":
                    print("\nStopping. Chrome stays open.")
                    break
                else:
                    mark_skipped(job, "manual_skip")
                    skipped += 1
                    page.close()

            if i < len(jobs) - 1:
                time.sleep(args.delay)

        print(f"\n{'='*60}")
        print(f"  Done! Applied: {applied} | Skipped: {skipped}")
        print(f"{'='*60}")
        print("Chrome stays open. Close it when you're done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-apply to jobs")
    parser.add_argument("--min-score", type=int, default=60, help="Min match %% (default: 60)")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs (default: 10)")
    parser.add_argument("--job-id", type=str, default=None, help="Specific job ID")
    parser.add_argument("--ext-wait", type=int, default=8, help="Seconds to wait for extension to fill (default: 8)")
    parser.add_argument("--delay", type=int, default=3, help="Seconds between applications (default: 3)")
    run(parser.parse_args())
