"""
Auto-Apply Engine: Browser automation controlled via API.
Runs in a background thread, exposes state for the frontend to poll.
"""

import time
import shutil
import socket
import threading
import subprocess
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

DB_PATH = Path(__file__).parent / "jobhunter.db"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not Path(CHROME_PATH).exists():
    CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
DEBUG_PROFILE_DIR = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "AutoApplyProfile"
DEBUG_PORT = 9222


# ---------------------------------------------------------------------------
# ATS detection
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


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

def find_and_click(page, selectors, timeout=3000):
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
    error_selectors = [
        '[data-automation-id="errorMessage"]',
        '.css-1lyuypv',
        '.field-error', '.error-message',
        '[role="alert"]',
    ]
    for sel in error_selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=500):
                return True
        except:
            pass
    return False


def has_captcha(page):
    for sel in ['iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]', '.g-recaptcha', '#captcha']:
        try:
            if page.locator(sel).count() > 0:
                return True
        except:
            pass
    return False


def has_file_upload(page):
    try:
        for u in page.locator('input[type="file"]').all():
            if u.is_visible():
                return True
    except:
        pass
    return False


# ---------------------------------------------------------------------------
# ATS-specific selectors
# ---------------------------------------------------------------------------

WORKDAY_APPLY = [
    'a[data-automation-id="jobApply"]',
    'button[data-automation-id="jobApply"]',
    'a:has-text("Apply")',
]
WORKDAY_USE_WITHOUT = [
    'button:has-text("Use Without an Account")',
    'button:has-text("Use My Last Application")',
    'a:has-text("Use Without an Account")',
]
WORKDAY_NEXT = ['button[data-automation-id="bottom-navigation-next-button"]']
WORKDAY_SUBMIT = ['button[data-automation-id="bottom-navigation-next-button"]:has-text("Submit")']

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


# ---------------------------------------------------------------------------
# Simplify extension helpers
# ---------------------------------------------------------------------------

SIMPLIFY_AUTOFILL = [
    # The main "Autofill this page" button in the Simplify popup/overlay
    'button:has-text("Autofill this page")',
    'button:has-text("Autofill")',
    '[class*="simplify"] button:has-text("Autofill")',
    # Simplify injects buttons near form fields too
    'button[data-simplify-autofill]',
]


def trigger_simplify(page, log, timeout=3000):
    """Try to click Simplify's Autofill button if present."""
    for sel in SIMPLIFY_AUTOFILL:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout) and loc.is_enabled():
                loc.scroll_into_view_if_needed()
                time.sleep(0.3)
                loc.click()
                log("Clicked Simplify Autofill")
                return True
        except Exception:
            continue

    # Fallback: Simplify might be in a shadow DOM or iframe — try via JS
    try:
        clicked = page.evaluate("""() => {
            // Check for Simplify's injected elements
            const btns = document.querySelectorAll('button, a, div[role="button"]');
            for (const b of btns) {
                const text = (b.textContent || '').trim().toLowerCase();
                if (text.includes('autofill') && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked:
            log("Clicked Simplify Autofill (via JS)")
            return True
    except Exception:
        pass

    log("Simplify Autofill not found — extension will fill on its own")
    return False


# ---------------------------------------------------------------------------
# ATS flows
# ---------------------------------------------------------------------------

def apply_workday(page, ext_wait, log):
    log("Starting Workday flow")
    time.sleep(2)
    if not find_and_click(page, WORKDAY_APPLY):
        log("No Apply button — might already be on form")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass
    time.sleep(2)

    find_and_click(page, WORKDAY_USE_WITHOUT, timeout=3000)
    time.sleep(2)

    for step in range(10):
        # Trigger Simplify autofill on each step
        trigger_simplify(page, log, timeout=2000)
        log(f"Step {step + 1} — waiting {ext_wait}s for fields to fill...")
        time.sleep(ext_wait)

        if check_success(page):
            return "success"
        if has_captcha(page):
            log("CAPTCHA detected")
            return "needs_attention"
        if has_errors(page):
            log("Form errors — waiting more...")
            time.sleep(ext_wait)
            if has_errors(page):
                return "needs_attention"

        if find_and_click(page, WORKDAY_SUBMIT, timeout=1000):
            log("Clicked Submit!")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeout:
                pass
            time.sleep(3)
            if check_success(page):
                return "success"
            continue

        if find_and_click(page, WORKDAY_NEXT, timeout=2000):
            log(f"Clicked Next (step {step + 1})")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PWTimeout:
                pass
            time.sleep(2)
            continue

        log("No Next/Submit button found")
        return "needs_attention"

    return "needs_attention"


def apply_single_page(page, ats, ext_wait, log):
    log(f"Single-page form ({ats})")
    if ats == "lever":
        find_and_click(page, LEVER_APPLY, timeout=3000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PWTimeout:
            pass
        time.sleep(2)

    # Trigger Simplify autofill
    trigger_simplify(page, log, timeout=2000)
    log(f"Waiting {ext_wait}s for fields to fill...")
    time.sleep(ext_wait)

    if check_success(page):
        return "success"
    if has_captcha(page):
        return "needs_attention"
    if has_file_upload(page):
        log("File upload detected")
        return "needs_attention"

    if find_and_click(page, SINGLE_PAGE_SUBMIT, timeout=3000):
        log("Clicked Submit")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass
        time.sleep(3)
        if check_success(page):
            return "success"
        if has_errors(page):
            return "needs_attention"
        return "submitted"

    log("No submit button found")
    return "needs_attention"


# ---------------------------------------------------------------------------
# Engine (singleton, runs in background thread)
# ---------------------------------------------------------------------------

class AutoApplyEngine:
    """Stateful engine that the server controls via start/stop/action methods."""

    def __init__(self):
        self._lock = threading.Lock()
        self._action_event = threading.Event()
        self._action_value = None
        self._thread = None
        self.reset_state()

    def reset_state(self):
        self.status = "idle"          # idle | running | paused | done | error
        self.jobs = []
        self.current_idx = 0
        self.current_job = None
        self.applied = 0
        self.skipped = 0
        self.logs = []
        self.pause_reason = ""
        self.error_msg = ""

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        with self._lock:
            self.logs.append(entry)
            if len(self.logs) > 200:
                self.logs = self.logs[-100:]
        print(f"  [auto-apply] {entry}")

    def get_status(self):
        with self._lock:
            return {
                "status": self.status,
                "current_job": self.current_job,
                "current_idx": self.current_idx,
                "total": len(self.jobs),
                "applied": self.applied,
                "skipped": self.skipped,
                "pause_reason": self.pause_reason,
                "error": self.error_msg,
                "logs": list(self.logs[-30:]),
            }

    def start(self, min_score=60, limit=50, ext_wait=8, delay=3):
        if not HAS_PLAYWRIGHT:
            self.error_msg = "Playwright not installed"
            self.status = "error"
            return False

        if self.status == "running":
            return False

        self.reset_state()
        self._action_event.clear()
        self._action_value = None

        # Fetch jobs from DB
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM jobs
               WHERE status = 'pending'
               AND match_pct IS NOT NULL AND match_pct >= ?
               AND apply_link IS NOT NULL AND apply_link != ''
               ORDER BY match_pct DESC LIMIT ?""",
            (min_score, limit),
        )
        self.jobs = [dict(row) for row in cur.fetchall()]
        conn.close()

        if not self.jobs:
            self.error_msg = "No scored pending jobs found"
            self.status = "error"
            return False

        self.status = "running"
        self._thread = threading.Thread(
            target=self._run,
            args=(ext_wait, delay),
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self):
        self.status = "done"
        self._action_event.set()  # unblock if waiting

    def send_action(self, action):
        """User sends: applied, applied_recruiter, skip, stop"""
        self._action_value = action
        self._action_event.set()

    def _wait_for_user(self, reason):
        self.pause_reason = reason
        self.status = "paused"
        self.log(f"Paused: {reason}")
        self._action_event.clear()
        self._action_event.wait(timeout=600)  # 10 min max
        val = self._action_value
        self._action_value = None
        self.status = "running"
        self.pause_reason = ""
        return val or "skip"

    def _mark_applied(self, job):
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cur.execute("UPDATE jobs SET status = 'applied' WHERE id = ?", (job["id"],))
        cur.execute(
            """INSERT OR IGNORE INTO applications
               (job_id, title, company, location, apply_link, source, resume_used, status, applied_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'applied', ?)""",
            (job["id"], job.get("title", ""), job.get("company", ""),
             job.get("location", ""), job.get("apply_link", ""),
             "auto_apply", job.get("recommended_resume", ""), now),
        )
        conn.commit()
        conn.close()

    def _mark_skipped(self, job, reason="auto_apply_skip"):
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("UPDATE jobs SET status = 'skipped', notes = ? WHERE id = ?",
                     (reason, job["id"]))
        conn.commit()
        conn.close()

    # -----------------------------------------------------------------------
    # Main loop (runs in thread)
    # -----------------------------------------------------------------------

    def _is_chrome_running(self):
        """Check if any Chrome process is running."""
        try:
            result = subprocess.run(
                ["tasklist"], capture_output=True, text=True, timeout=10,
            )
            return "chrome.exe" in result.stdout.lower()
        except Exception:
            return False

    def _is_debug_port_open(self):
        """Check if Chrome debug port is already listening."""
        try:
            with socket.create_connection(("127.0.0.1", DEBUG_PORT), timeout=2):
                return True
        except Exception:
            return False

    def _prepare_debug_profile(self):
        """Copy original Chrome profile to a debug-safe directory.

        Chrome refuses to open the debug port on a profile that was
        previously force-killed. Using a copy of the profile in a
        separate directory works reliably AND keeps all extensions,
        cookies, autofill data, and Simplify login state.
        """
        self.log("Preparing debug profile (copying from original)...")
        src = USER_DATA_DIR
        dst = DEBUG_PROFILE_DIR

        # Clean previous debug profile
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True, exist_ok=True)

        # Copy Local State (extension crypto keys, etc.)
        ls = src / "Local State"
        if ls.exists():
            shutil.copy2(ls, dst / "Local State")

        # Copy Default profile — skip large cache dirs
        shutil.copytree(
            src / "Default",
            dst / "Default",
            ignore=shutil.ignore_patterns(
                "Cache", "Code Cache", "GPUCache",
                "Service Worker", "blob_storage", "File System",
                "GCM Store", "BudgetDatabase",
            ),
            dirs_exist_ok=True,
        )
        self.log("Debug profile ready")

    def _run(self, ext_wait, delay):
        chrome_proc = None
        try:
            with sync_playwright() as p:
                browser = None

                # Step 1: Try connecting to existing debug port
                if self._is_debug_port_open():
                    self.log("Debug port already open — connecting...")
                    try:
                        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
                        self.log("Connected to existing Chrome!")
                    except Exception:
                        self.log("Port open but connection failed, will relaunch")

                # Step 2: Kill existing Chrome, copy profile, launch with debug port
                if not browser:
                    if self._is_chrome_running():
                        self.log("Closing Chrome...")
                        subprocess.run(
                            ["taskkill", "/F", "/IM", "chrome.exe"],
                            capture_output=True, timeout=10,
                        )
                        for _ in range(15):
                            time.sleep(0.5)
                            if not self._is_chrome_running():
                                break
                        time.sleep(1)

                    # Copy profile to debug directory (avoids lock/crash issues)
                    try:
                        self._prepare_debug_profile()
                    except Exception as e:
                        self.error_msg = f"Failed to copy Chrome profile: {e}"
                        self.status = "error"
                        self.log(self.error_msg)
                        return

                    # Launch Chrome with copied profile + debug port
                    self.log("Launching Chrome with remote debugging...")
                    chrome_proc = subprocess.Popen([
                        CHROME_PATH,
                        f"--remote-debugging-port={DEBUG_PORT}",
                        "--remote-allow-origins=*",
                        f"--user-data-dir={DEBUG_PROFILE_DIR}",
                        "--profile-directory=Default",
                        "--no-first-run",
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    # Wait for debug port
                    for attempt in range(15):
                        time.sleep(1)
                        if self._is_debug_port_open():
                            self.log(f"Chrome ready ({attempt + 1}s)")
                            break
                    else:
                        self.error_msg = "Chrome launched but debug port never opened"
                        self.status = "error"
                        self.log(self.error_msg)
                        return

                    # Let extensions initialize
                    time.sleep(3)

                    try:
                        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
                        self.log("Connected to Chrome!")
                    except Exception as e:
                        self.error_msg = f"Failed to connect to Chrome: {e}"
                        self.status = "error"
                        self.log(self.error_msg)
                        return

                context = browser.contexts[0] if browser.contexts else browser.new_context()

                for i, job in enumerate(self.jobs):
                    if self.status == "done":
                        break

                    self.current_idx = i
                    self.current_job = {
                        "id": job["id"],
                        "title": job.get("title", ""),
                        "company": job.get("company", ""),
                        "location": job.get("location", ""),
                        "match_pct": job.get("match_pct"),
                        "match_summary": job.get("match_summary", ""),
                        "recommended_resume": job.get("recommended_resume", ""),
                        "apply_link": job.get("apply_link", ""),
                    }

                    link = job.get("apply_link", "")
                    if not link:
                        continue

                    self.log(f"[{i+1}/{len(self.jobs)}] {job['title']} @ {job['company']} ({job.get('match_pct', '?')}%)")

                    page = context.new_page()
                    try:
                        page.goto(link, wait_until="domcontentloaded", timeout=30000)
                    except PWTimeout:
                        pass
                    time.sleep(2)

                    ats = detect_ats(page.url)
                    self.log(f"ATS: {ats}")

                    # Run ATS-specific flow
                    if ats == "workday":
                        result = apply_workday(page, ext_wait, self.log)
                    elif ats in ("greenhouse", "lever", "ashby", "smartrecruiters"):
                        result = apply_single_page(page, ats, ext_wait, self.log)
                    else:
                        self.log("Unknown ATS — triggering Simplify, then trying submit...")
                        trigger_simplify(page, self.log, timeout=2000)
                        time.sleep(ext_wait)
                        result = "needs_attention"
                        if find_and_click(page, SINGLE_PAGE_SUBMIT, timeout=3000):
                            time.sleep(3)
                            if check_success(page):
                                result = "success"

                    # Handle result
                    if result in ("success", "submitted"):
                        self.log("Application submitted!")
                        self._mark_applied(job)
                        self.applied += 1
                        time.sleep(2)
                        page.close()
                    else:
                        # Pause for user
                        action = self._wait_for_user(
                            f"Needs attention: {result} — {job['title']} @ {job['company']}"
                        )
                        if action == "stop":
                            page.close()
                            break
                        elif action in ("applied", "applied_recruiter"):
                            self._mark_applied(job)
                            self.applied += 1
                            page.close()
                        else:
                            reason = action if action not in ("skip",) else "manual_skip"
                            self._mark_skipped(job, reason)
                            self.skipped += 1
                            page.close()

                    if i < len(self.jobs) - 1 and self.status != "done":
                        time.sleep(delay)

            self.log(f"Done! Applied: {self.applied} | Skipped: {self.skipped}")

        except Exception as e:
            self.error_msg = str(e)
            self.status = "error"
            self.log(f"Error: {e}")

        finally:
            if self.status != "error":
                self.status = "done"
            self.current_job = None


# Singleton instance
engine = AutoApplyEngine()
