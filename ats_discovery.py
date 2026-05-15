"""
ATS Discovery Module
Queries Greenhouse, Lever, Ashby, Amazon, Workday, and Pinpoint public APIs.
No API key required — these are open public endpoints.
Filters to US-based jobs only.
"""

import re
import html
import json
import time
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

from discovery import (
    load_json, save_json, is_blacklisted, score_job,
    already_applied, SCORE_THRESHOLD, QUEUE_PATH, LOG_PATH, BLACKLIST_PATH,
)

COMPANIES_PATH = Path("companies.json")
FRESHNESS_DAYS = 1

SKIP_TITLE_KEYWORDS = [
    "senior", "staff", "principal", "lead ", "director", "manager",
    "head of", "vp ", "vice president", "distinguished", "fellow",
    "sales", "marketing", "recruiting", "recruiter", "legal", "finance",
    "accountant", "designer", "product designer", "ux ", "researcher",
    "data center", "facilities", "operations", "sourcing", "procurement",
    "hr ", "people partner", "program manager",
]

US_LOCATION_KEYWORDS = [
    "united states", "usa", "us", "remote",
    "new york", "san francisco", "seattle", "austin", "boston",
    "chicago", "los angeles", "denver", "atlanta", "dallas",
    "houston", "portland", "phoenix", "miami", "philadelphia",
    "washington", "dc", "california", "texas", "virginia",
    "massachusetts", "colorado", "georgia", "illinois", "oregon",
    "pennsylvania", "florida", "north carolina", "minnesota",
    "utah", "arizona", "maryland", "ohio", "michigan", "indiana",
    "mountain view", "palo alto", "sunnyvale", "cupertino",
    "san jose", "redmond", "brooklyn", "manhattan",
    ", ca", ", ny", ", wa", ", tx", ", ma", ", co", ", ga",
    ", il", ", or", ", pa", ", fl", ", nc", ", mn", ", ut",
    ", az", ", md", ", oh", ", mi", ", in", ", va",
]


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(cleaned).strip()


def _is_fresh(dt: datetime, days: int = FRESHNESS_DAYS, hours: int | None = None) -> bool:
    if hours is not None:
        return (datetime.now(timezone.utc) - dt) <= timedelta(hours=hours)
    return (datetime.now(timezone.utc) - dt) <= timedelta(days=days)


def _workday_posted_to_iso(posted_str: str) -> str:
    """Convert Workday 'Posted 3 Days Ago' to an approximate ISO date."""
    if not posted_str:
        return ""
    days_match = re.search(r"(\d+)\+?\s*days?\s*ago", posted_str, re.IGNORECASE)
    if days_match:
        days_ago = int(days_match.group(1))
        dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return dt.isoformat()
    if "today" in posted_str.lower():
        return datetime.now(timezone.utc).isoformat()
    if "yesterday" in posted_str.lower():
        return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    # Try ISO as-is
    try:
        datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
        return posted_str
    except (ValueError, TypeError):
        return ""


def _job_id(company: str, title: str, url: str) -> str:
    key = f"{company}{title}{url}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _is_us_location(location: str) -> bool:
    if not location:
        return True
    loc_lower = location.lower()
    return any(kw in loc_lower for kw in US_LOCATION_KEYWORDS)


# ---------------------------------------------------------------------------
# Greenhouse — use absolute_url (JD page)
# ---------------------------------------------------------------------------

def fetch_greenhouse(slug: str, company_name: str) -> list:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            print(f"[ats] Greenhouse '{slug}' not found — check the slug")
            return []
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[ats] Greenhouse {slug} failed: {e}")
        return []

    results = []
    for j in jobs:
        updated_str = j.get("updated_at", "")
        try:
            dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            if not _is_fresh(dt):
                continue
        except (ValueError, TypeError):
            pass

        loc = (j.get("location") or {}).get("name", "")
        if not _is_us_location(loc):
            continue

        description = _strip_html(j.get("content", ""))
        jd_url = j.get("absolute_url", "")

        results.append({
            "employer_name": company_name,
            "job_title": j.get("title", ""),
            "job_description": description,
            "job_apply_link": jd_url,
            "job_city": loc,
            "job_country": "US",
            "job_apply_is_direct": True,
            "job_posted_at_datetime_utc": updated_str,
            "_ats": "greenhouse",
        })
    return results


# ---------------------------------------------------------------------------
# Lever — use hostedUrl (JD page, not apply form)
# ---------------------------------------------------------------------------

def fetch_lever(slug: str, company_name: str) -> list:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            print(f"[ats] Lever '{slug}' not found — check the slug")
            return []
        resp.raise_for_status()
        postings = resp.json()
    except Exception as e:
        print(f"[ats] Lever {slug} failed: {e}")
        return []

    results = []
    for j in postings:
        created_ms = j.get("createdAt", 0)
        try:
            dt = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
            if not _is_fresh(dt):
                continue
        except (ValueError, TypeError):
            pass

        cats = j.get("categories") or {}
        loc = cats.get("location", "")
        if not _is_us_location(loc):
            continue

        description = _strip_html(j.get("descriptionPlain") or j.get("description", ""))
        jd_url = j.get("hostedUrl", "") or j.get("applyUrl", "")
        posted_iso = datetime.fromtimestamp(
            created_ms / 1000, tz=timezone.utc
        ).isoformat() if created_ms else ""

        results.append({
            "employer_name": company_name,
            "job_title": j.get("text", ""),
            "job_description": description,
            "job_apply_link": jd_url,
            "job_city": loc,
            "job_country": "US",
            "job_apply_is_direct": True,
            "job_posted_at_datetime_utc": posted_iso,
            "_ats": "lever",
        })
    return results


# ---------------------------------------------------------------------------
# Ashby — US filter
# ---------------------------------------------------------------------------

def fetch_ashby(slug: str, company_name: str) -> list:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            print(f"[ats] Ashby '{slug}' not found — check the slug")
            return []
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[ats] Ashby {slug} failed: {e}")
        return []

    results = []
    for j in jobs:
        updated_str = j.get("updatedAt", "") or j.get("publishedAt", "")
        try:
            dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            if not _is_fresh(dt):
                continue
        except (ValueError, TypeError):
            pass

        loc = j.get("location", "") or ""
        if isinstance(loc, dict):
            loc = loc.get("name", "")
        if not _is_us_location(loc):
            continue

        description = _strip_html(j.get("descriptionHtml", "") or j.get("descriptionPlain", ""))
        apply_url = j.get("jobUrl", "") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id', '')}"

        results.append({
            "employer_name": company_name,
            "job_title": j.get("title", ""),
            "job_description": description,
            "job_apply_link": apply_url,
            "job_city": loc,
            "job_country": "US",
            "job_apply_is_direct": True,
            "job_posted_at_datetime_utc": updated_str,
            "_ats": "ashby",
        })
    return results


# ---------------------------------------------------------------------------
# Amazon — use job_path (JD page, not url_next_step)
# ---------------------------------------------------------------------------

def fetch_amazon(company_name: str = "Amazon") -> list:
    url = "https://www.amazon.jobs/en/search.json"
    results = []
    for offset in range(0, 50, 25):
        try:
            resp = requests.get(
                url,
                params={
                    "base_query": "software engineer",
                    "loc_query": "United States",
                    "result_limit": "25",
                    "offset": str(offset),
                    "sort": "recent",
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            resp.raise_for_status()
            jobs = resp.json().get("jobs", [])
            if not jobs:
                break
        except Exception as e:
            print(f"[ats] Amazon page {offset} failed: {e}")
            break

        for j in jobs:
            if j.get("country_code", "") != "USA":
                continue

            posted_str = j.get("posted_date", "")
            try:
                dt = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
                if not _is_fresh(dt):
                    continue
            except (ValueError, TypeError):
                pass

            jd_url = f"https://www.amazon.jobs{j.get('job_path', '')}"
            description = " ".join(filter(None, [
                j.get("description", ""),
                j.get("basic_qualifications", ""),
                j.get("preferred_qualifications", ""),
            ]))
            results.append({
                "employer_name": company_name,
                "job_title": j.get("title", ""),
                "job_description": description,
                "job_apply_link": jd_url,
                "job_city": j.get("normalized_location", "") or j.get("city", ""),
                "job_country": "US",
                "job_apply_is_direct": True,
                "job_posted_at_datetime_utc": posted_str,
                "_ats": "amazon",
            })
        time.sleep(0.3)
    return results


# ---------------------------------------------------------------------------
# Workday — fixed URL: use /en-US/{site}/job/ path
# ---------------------------------------------------------------------------

def fetch_workday(slug: str, company_name: str, wd_num: int = 5, site: str = "") -> list:
    url = f"https://{slug}.wd{wd_num}.myworkdayjobs.com/wday/cxs/{slug}/{site}/jobs"
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "software engineer"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[ats] Workday {company_name} failed: HTTP {resp.status_code}")
            return []
        data = resp.json()
        postings = data.get("jobPostings", [])
    except Exception as e:
        print(f"[ats] Workday {company_name} failed: {e}")
        return []

    results = []
    base_url = f"https://{slug}.wd{wd_num}.myworkdayjobs.com/en-US/{site}"
    for j in postings:
        posted_str = j.get("postedOn", "")
        # Workday returns human-readable strings like "Posted 30+ Days Ago"
        # Parse the number of days to filter stale postings
        is_fresh_job = True
        if posted_str:
            days_match = re.search(r"(\d+)\+?\s*days?\s*ago", posted_str, re.IGNORECASE)
            if days_match:
                days_ago = int(days_match.group(1))
                if days_ago > FRESHNESS_DAYS:
                    is_fresh_job = False
            elif "today" in posted_str.lower():
                is_fresh_job = True
            else:
                # Try ISO format as fallback
                try:
                    dt = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
                    is_fresh_job = _is_fresh(dt)
                except (ValueError, TypeError):
                    is_fresh_job = False
        if not is_fresh_job:
            continue

        ext_path = j.get("externalPath", "")
        if ext_path:
            jd_url = f"{base_url}{ext_path}"
        else:
            title_slug = j.get("title", "").replace(" ", "-").replace("/", "-")
            jd_url = f"{base_url}/job/{title_slug}/{j.get('bulletFields', [''])[0] if j.get('bulletFields') else ''}"

        loc_text = j.get("locationsText", "")
        if not _is_us_location(loc_text):
            continue

        bullets = " ".join(j.get("bulletFields", []) or [])
        results.append({
            "employer_name": company_name,
            "job_title": j.get("title", ""),
            "job_description": bullets,
            "job_apply_link": jd_url,
            "job_city": loc_text,
            "job_country": "US",
            "job_apply_is_direct": True,
            "job_posted_at_datetime_utc": _workday_posted_to_iso(posted_str),
            "_ats": "workday",
        })
    return results


# ---------------------------------------------------------------------------
# Pinpoint
# ---------------------------------------------------------------------------

def fetch_pinpoint(slug: str, company_name: str) -> list:
    url = f"https://{slug}.pinpointhq.com/postings.json"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            print(f"[ats] Pinpoint '{slug}' not found — check the slug")
            return []
        resp.raise_for_status()
        data = resp.json()
        postings = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(postings, list):
            postings = []
    except Exception as e:
        print(f"[ats] Pinpoint {slug} failed: {e}")
        return []

    results = []
    for j in postings:
        loc = j.get("location", {})
        if isinstance(loc, dict):
            loc_name = loc.get("name", "") or loc.get("city", "")
            country = loc.get("country", "")
        else:
            loc_name = str(loc)
            country = ""

        if country and country.lower() not in ("us", "usa", "united states", ""):
            continue
        if not _is_us_location(loc_name) and country == "":
            continue

        published = j.get("published_at", "") or j.get("created_at", "")
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if not _is_fresh(dt):
                continue
        except (ValueError, TypeError):
            pass

        description = _strip_html(j.get("description", ""))
        jd_url = j.get("url", "") or f"https://{slug}.pinpointhq.com/en/postings/{j.get('id', '')}"

        results.append({
            "employer_name": company_name,
            "job_title": j.get("title", ""),
            "job_description": description,
            "job_apply_link": jd_url,
            "job_city": loc_name,
            "job_country": "US",
            "job_apply_is_direct": True,
            "job_posted_at_datetime_utc": published,
            "_ats": "pinpoint",
        })
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def discover_from_ats(companies_path: str = None) -> list:
    companies = load_json(Path(companies_path or COMPANIES_PATH))
    if not companies:
        print("[ats] companies.json is empty — add companies to enable ATS discovery")
        return []

    blacklist = load_json(BLACKLIST_PATH)
    applied_log = load_json(LOG_PATH)
    queue = load_json(QUEUE_PATH)
    existing_ids = {entry.get("id") for entry in queue}

    new_entries = []

    for company in companies:
        name = company.get("name", "")
        ats = company.get("ats", "").lower()
        slug = company.get("slug", "")

        if not (name and ats and slug):
            continue

        print(f"[ats] {name} ({ats})")

        if ats == "greenhouse":
            raw_jobs = fetch_greenhouse(slug, name)
        elif ats == "lever":
            raw_jobs = fetch_lever(slug, name)
        elif ats == "ashby":
            raw_jobs = fetch_ashby(slug, name)
        elif ats == "amazon":
            raw_jobs = fetch_amazon(name)
        elif ats == "workday":
            wd_num = company.get("wd_num", 5)
            site = company.get("site", "")
            raw_jobs = fetch_workday(slug, name, wd_num, site)
        elif ats == "pinpoint":
            raw_jobs = fetch_pinpoint(slug, name)
        else:
            print(f"[ats] Unknown ATS type '{ats}' for {name} — skipping")
            continue

        fresh = len(raw_jobs)
        if fresh == 0:
            time.sleep(0.2)
            continue

        print(f"[ats] {name}: {fresh} fresh US postings")

        for job in raw_jobs:
            jid = _job_id(
                job.get("employer_name", ""),
                job.get("job_title", ""),
                job.get("job_apply_link", ""),
            )

            if jid in existing_ids:
                continue
            if already_applied(jid, applied_log):
                continue
            title_lower = (job.get("job_title") or "").lower()
            if any(kw in title_lower for kw in SKIP_TITLE_KEYWORDS):
                continue

            if is_blacklisted(job, blacklist):
                continue

            score = score_job(job)
            threshold = 0.25 if ats == "workday" else SCORE_THRESHOLD
            if score < threshold:
                continue

            entry = {
                "id": jid,
                "score": score,
                "title": job.get("job_title"),
                "company": name,
                "location": job.get("job_city", ""),
                "apply_link": job.get("job_apply_link"),
                "ats": ats,
                "posted_at": job.get("job_posted_at_datetime_utc", ""),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "description": job.get("job_description", "")[:1000],
                "source": ats,
                "status": "pending",
            }

            new_entries.append(entry)
            existing_ids.add(jid)
            print(f"[ats] Queued ({score}) [{ats}]: {name} — {entry['title']}")

        time.sleep(0.3)

    queue.extend(new_entries)
    save_json(QUEUE_PATH, queue)
    print(f"[ats] Done. {len(new_entries)} new jobs from ATS APIs.")
    return new_entries
