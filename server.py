"""FastAPI backend for JobHunter dashboard."""

import os
import sys
import re
import json
import html
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import requests as http_requests
import database as db
import llm
from discovery import (
    JSEARCH_KEY, SCORE_THRESHOLD, QUEUE_PATH, LOG_PATH, BLACKLIST_PATH,
    load_json, save_json, score_job, is_blacklisted, already_applied, job_id,
    fetch_jobs, _best_apply_link, _is_fresh, ALLOWED_PUBLISHERS,
)
from ats_discovery import discover_from_ats, SKIP_TITLE_KEYWORDS, _job_id, fetch_simplify_github
from resume_selector import get_resume_type, get_resume_text, RESUME_KEYWORDS
from auto_apply_engine import engine as auto_apply_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.migrate_json_to_db()
    yield

app = FastAPI(title="JobHunter", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class JobUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    description: str | None = None
    match_pct: float | None = None
    match_summary: str | None = None
    team: str | None = None
    project: str | None = None

class ApplicationCreate(BaseModel):
    job_id: str | None = None
    title: str
    company: str
    location: str = ""
    apply_link: str = ""
    status: str = "applied"
    applied_at: str | None = None
    source: str = "manual"
    salary_min: int | None = None
    salary_max: int | None = None
    notes: str = ""
    resume_used: str = ""

class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    resume_used: str | None = None

class RecruiterCreate(BaseModel):
    name: str
    company: str = ""
    linkedin_url: str = ""
    email: str = ""
    application_id: int | None = None
    notes: str = ""

class ReminderCreate(BaseModel):
    application_id: int | None = None
    recruiter_id: int | None = None
    job_id: str | None = None
    title: str
    due_date: str

class DiscoverRequest(BaseModel):
    queries: list[str] | None = None
    location: str = "United States"
    skip_jsearch: bool = False
    skip_ats: bool = False
    skip_adzuna: bool = False
    skip_simplify: bool = False
    freshness_hours: int = 24


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------

def _parse_json_fields(job: dict) -> dict:
    """Parse resume_scores and matched_keywords from JSON strings."""
    for field in ("resume_scores", "matched_keywords"):
        val = job.get(field)
        if isinstance(val, str):
            try:
                job[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                job[field] = None
    return job

@app.get("/api/jobs")
def list_jobs(
    status: str | None = None,
    min_score: float | None = None,
    limit: int = 25,
    offset: int = 0,
    search: str | None = None,
    sort: str | None = None,
):
    jobs = db.get_jobs(status=status, min_score=min_score, limit=limit, offset=offset, search=search, sort=sort)
    jobs = [_parse_json_fields(j) for j in jobs]
    total = db.count_jobs(status=status, min_score=min_score, search=search)
    return {"jobs": jobs, "total": total, "limit": limit, "offset": offset}

@app.get("/api/jobs/stats")
def job_stats():
    return db.get_job_stats()

@app.get("/api/jobs/evaluated")
def evaluated_jobs():
    return db.get_evaluated_jobs()

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _parse_json_fields(job)

@app.patch("/api/jobs/{job_id}")
def update_job(job_id: str, body: JobUpdate):
    db.update_job(job_id, **body.model_dump(exclude_none=True))
    return db.get_job(job_id)


def _fetch_jd_from_url(url: str) -> dict:
    """
    Fetch job description from ATS URL. Returns dict with available fields:
    title, company, location, description, apply_link, ats.
    """
    from ats_discovery import _strip_html

    result = {"title": "", "company": "", "location": "", "description": "", "apply_link": url, "ats": ""}

    try:
        # --- Oracle HCM / Fusion (*.oraclecloud.com) ---
        oracle_match = re.match(
            r"https?://([^/]+\.oraclecloud\.com)/hcmUI/CandidateExperience/\w+/sites/\w+/job/(\d+)",
            url
        )
        if oracle_match:
            oracle_host, oracle_job_id = oracle_match.groups()
            try:
                # Oracle CX REST API — job detail endpoint
                api_url = f"https://{oracle_host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails/{oracle_job_id}?onlyData=true"
                r = http_requests.get(api_url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                })
                if r.status_code == 200:
                    data = r.json()
                    result["title"] = data.get("Title", "")
                    result["location"] = data.get("PrimaryLocation", "")
                    # Combine all description sections
                    desc_parts = []
                    for key in ["ExternalResponsibilitiesStr", "CorporateDescriptionStr", "ExternalQualificationsStr"]:
                        val = data.get(key)
                        if val:
                            desc_parts.append(_strip_html(val))
                    result["description"] = "\n\n".join(desc_parts)
                    result["apply_link"] = url
                    result["ats"] = "oracle_hcm"
                    # Try to get company from OG tags if API doesn't have it
                    if not result.get("company"):
                        try:
                            page_r = http_requests.get(url, timeout=8, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                            })
                            og_site = re.search(r'property="og:site_name"\s+content="([^"]+)"', page_r.text)
                            if og_site:
                                result["company"] = og_site.group(1).strip()
                        except Exception:
                            pass
                    if result["title"]:
                        return result
            except Exception as e:
                _log(f"[fetch-jd] Oracle HCM API error: {e}")
            # Fallback: OG tags from page
            try:
                r = http_requests.get(url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if r.status_code == 200:
                    og_title = re.search(r'property="og:title"\s+content="([^"]+)"', r.text)
                    og_desc = re.search(r'property="og:description"\s+content="([^"]+)"', r.text)
                    og_site = re.search(r'property="og:site_name"\s+content="([^"]+)"', r.text)
                    if og_title:
                        result["title"] = html.unescape(og_title.group(1).strip())
                    if og_desc:
                        result["description"] = html.unescape(og_desc.group(1).strip())
                    if og_site:
                        result["company"] = og_site.group(1).strip()
                    result["apply_link"] = url
                    result["ats"] = "oracle_hcm"
                    if result["title"]:
                        return result
            except Exception as e:
                _log(f"[fetch-jd] Oracle HCM OG fallback error: {e}")

        # --- Workday ---
        wd_match = re.match(
            r"https?://(\w+)\.wd(\d+)\.myworkdayjobs\.com/(?:en-US/)?([^/]+)(/job/.+)",
            url
        )
        if wd_match:
            slug, wd_num, site, ext_path = wd_match.groups()
            detail_url = f"https://{slug}.wd{wd_num}.myworkdayjobs.com/wday/cxs/{slug}/{site}{ext_path}"
            r = http_requests.get(
                detail_url,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if r.status_code == 200:
                info = r.json().get("jobPostingInfo", {})
                result["title"] = info.get("title", "")
                result["description"] = _strip_html(info.get("jobDescription", ""))
                result["location"] = info.get("location", "")
                result["company"] = slug.replace("-", " ").title()
                result["apply_link"] = info.get("externalUrl") or url
                result["ats"] = "workday"
                return result

        # --- Greenhouse ---
        gh_match = re.match(
            r"https?://(?:boards\.greenhouse\.io/(?:embed/)?(?:job_app\?token=|)|[^/]+\.greenhouse\.io/)(\w+)(?:/jobs/(\d+))?",
            url
        )
        # Also try: company.greenhouse.io URL pattern (e.g. https://job-boards.greenhouse.io/company/jobs/123)
        if not gh_match:
            gh_match = re.match(r"https?://job-boards\.greenhouse\.io/(\w+)/jobs/(\d+)", url)

        # Detect gh_jid query parameter on any custom career site (e.g. careers.upstart.com?gh_jid=123)
        if not gh_match:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            gh_jid = (qs.get("gh_jid") or qs.get("gh_jid[]") or [None])[0]
            if gh_jid and gh_jid.isdigit():
                # Try to figure out the board name from the domain (e.g. careers.upstart.com -> upstart)
                domain_parts = parsed.hostname.split(".")
                # Typically: careers.COMPANY.com or jobs.COMPANY.com -> take the second part
                board_guess = None
                if len(domain_parts) >= 2:
                    board_guess = domain_parts[-2]  # e.g. "upstart" from "careers.upstart.com"
                if board_guess:
                    _log(f"[fetch-jd] Detected gh_jid={gh_jid} on {parsed.hostname}, trying Greenhouse API with board={board_guess}")
                    r = http_requests.get(
                        f"https://boards-api.greenhouse.io/v1/boards/{board_guess}/jobs/{gh_jid}",
                        timeout=10,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        result["title"] = data.get("title", "")
                        result["description"] = _strip_html(data.get("content", ""))
                        loc = data.get("location", {})
                        result["location"] = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                        result["company"] = (data.get("company") or {}).get("name", "") or board_guess.replace("-", " ").title()
                        result["apply_link"] = data.get("absolute_url", url)
                        result["ats"] = "greenhouse"
                        return result
                    else:
                        _log(f"[fetch-jd] Greenhouse API returned {r.status_code} for board={board_guess}, gh_jid={gh_jid}")
                        # Board guess failed — scrape the page for the real board token
                        try:
                            page_r = http_requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                            if page_r.status_code == 200:
                                page_text = page_r.text.replace("\\/", "/")
                                board_match = re.search(r'boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?(\w+)/jobs/' + gh_jid, page_text)
                                if board_match:
                                    real_board = board_match.group(1)
                                    _log(f"[fetch-jd] Found real Greenhouse board: {real_board}")
                                    r2 = http_requests.get(
                                        f"https://boards-api.greenhouse.io/v1/boards/{real_board}/jobs/{gh_jid}",
                                        timeout=10,
                                    )
                                    if r2.status_code == 200:
                                        data = r2.json()
                                        result["title"] = data.get("title", "")
                                        result["description"] = _strip_html(data.get("content", ""))
                                        loc = data.get("location", {})
                                        result["location"] = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                                        result["company"] = (data.get("company") or {}).get("name", "") or real_board.replace("-", " ").title()
                                        result["apply_link"] = data.get("absolute_url", url)
                                        result["ats"] = "greenhouse"
                                        return result
                        except Exception as e:
                            _log(f"[fetch-jd] Greenhouse board discovery error: {e}")

        if gh_match:
            board = gh_match.group(1)
            job_num = gh_match.group(2)
            if job_num:
                r = http_requests.get(
                    f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_num}",
                    timeout=10,
                )
                if r.status_code == 200:
                    data = r.json()
                    result["title"] = data.get("title", "")
                    result["description"] = _strip_html(data.get("content", ""))
                    loc = data.get("location", {})
                    result["location"] = loc.get("name", "") if isinstance(loc, dict) else str(loc)
                    result["company"] = (data.get("company") or {}).get("name", "") or board.replace("-", " ").title()
                    result["apply_link"] = data.get("absolute_url", url)
                    result["ats"] = "greenhouse"
                    return result

        # --- Lever ---
        lever_match = re.match(r"https?://jobs\.lever\.co/([^/]+)/([a-f0-9-]+)", url)
        if lever_match:
            board, posting_id = lever_match.groups()
            r = http_requests.get(f"https://api.lever.co/v0/postings/{board}/{posting_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                result["title"] = data.get("text", "")
                result["description"] = _strip_html(data.get("descriptionPlain", "") or data.get("description", ""))
                loc_parts = data.get("categories", {})
                result["location"] = loc_parts.get("location", "") if isinstance(loc_parts, dict) else ""
                result["company"] = board.replace("-", " ").title()
                result["apply_link"] = data.get("applyUrl") or data.get("hostedUrl") or url
                result["ats"] = "lever"
                return result

        # --- Ashby (GraphQL — old /posting-api endpoint is dead) ---
        ashby_match = re.match(r"https?://jobs\.ashbyhq\.com/([^/]+)/([a-f0-9-]+)", url)
        if ashby_match:
            board, posting_id = ashby_match.groups()
            gql_query = (
                "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) { "
                "jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, "
                "jobPostingId: $jobPostingId) { id title descriptionHtml locationName employmentType } }"
            )
            r = http_requests.post(
                "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting",
                json={
                    "operationName": "ApiJobPosting",
                    "variables": {"organizationHostedJobsPageName": board, "jobPostingId": posting_id},
                    "query": gql_query,
                },
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if r.status_code == 200:
                data = (r.json().get("data") or {}).get("jobPosting") or {}
                if data:
                    result["title"] = data.get("title", "")
                    result["description"] = _strip_html(data.get("descriptionHtml", ""))
                    result["location"] = data.get("locationName", "")
                    result["company"] = board.replace("-", " ").title()
                    result["apply_link"] = url
                    result["ats"] = "ashby"
                    return result

        # --- LinkedIn ---
        li_match = re.match(r"https?://(?:www\.)?linkedin\.com/jobs/view/(\d+)", url)
        if li_match:
            li_job_id = li_match.group(1)
            try:
                # Use LinkedIn's guest job posting API — returns full HTML with JD
                guest_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{li_job_id}"
                r = http_requests.get(guest_url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                })
                if r.status_code == 200:
                    page = r.text
                    # Title from h2.top-card-layout__title
                    t_m = re.search(r'<h2[^>]*class="[^"]*top-card-layout__title[^"]*"[^>]*>([^<]+)', page, re.I)
                    if t_m:
                        result["title"] = t_m.group(1).strip()
                    # Company from a.topcard__org-name-link
                    c_m = re.search(r'<a[^>]*class="[^"]*topcard__org-name-link[^"]*"[^>]*>([^<]+)', page, re.I)
                    if c_m:
                        result["company"] = c_m.group(1).strip()
                    # Location from span.topcard__flavor--bullet
                    l_m = re.search(r'<span[^>]*class="[^"]*topcard__flavor--bullet[^"]*"[^>]*>([^<]+)', page, re.I)
                    if l_m:
                        result["location"] = l_m.group(1).strip()
                    # Description from div.description
                    d_m = re.search(r'<div[^>]+class="[^"]*description[^"]*"[^>]*>(.*?)</div>', page, re.S | re.I)
                    if d_m:
                        result["description"] = _strip_html(d_m.group(1))

                    result["apply_link"] = url
                    result["ats"] = "linkedin"
                    if result["title"]:
                        return result
            except Exception as e:
                _log(f"[fetch-jd] LinkedIn guest API error: {e}")

            # Fallback: parse from main page <title>
            try:
                r = http_requests.get(url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }, allow_redirects=True)
                if r.status_code == 200:
                    title_m = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
                    if title_m:
                        raw_title = re.sub(r'\s*\|\s*LinkedIn\s*$', '', title_m.group(1).strip()).strip()
                        # "Company hiring Title in Location"
                        hire_m = re.match(r'^(.+?)\s+hiring\s+(.+?)\s+in\s+(.+)$', raw_title)
                        if hire_m:
                            result["company"] = hire_m.group(1).strip()
                            result["title"] = hire_m.group(2).strip()
                            result["location"] = hire_m.group(3).strip()
                        else:
                            result["title"] = raw_title
                    result["apply_link"] = url
                    result["ats"] = "linkedin"
                    if result["title"]:
                        return result
            except Exception as e:
                _log(f"[fetch-jd] LinkedIn fallback error: {e}")

        # --- Apple jobs (jobs.apple.com) — SSR hydration data ---
        apple_match = re.match(r"https?://jobs\.apple\.com/[\w-]+/details/(\d+(?:-\d+)?)", url)
        if apple_match:
            from ats_discovery import _parse_apple_ssr
            try:
                r = http_requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }, allow_redirects=True)
                if r.status_code == 200:
                    ssr_data = _parse_apple_ssr(r.text)
                    if ssr_data:
                        jd = (ssr_data.get("loaderData", {})
                              .get("jobDetails", {})
                              .get("jobsData", {}))
                        result["title"] = jd.get("postingTitle", "")
                        result["company"] = "Apple"
                        # Location
                        locs = jd.get("locations", [])
                        if locs:
                            result["location"] = locs[0].get("name", "")
                        # Full description — combine all sections
                        sections = []
                        for key, label in [
                            ("jobSummary", "Summary"),
                            ("description", "Description"),
                            ("responsibilities", "Key Responsibilities"),
                            ("minimumQualifications", "Minimum Qualifications"),
                            ("preferredQualifications", "Preferred Qualifications"),
                        ]:
                            val = jd.get(key, "")
                            if val:
                                sections.append(f"{label}\n{_strip_html(val)}")
                        if sections:
                            result["description"] = "\n\n".join(sections)
                        result["ats"] = "apple"
                        result["apply_link"] = url
                        if result["title"]:
                            return result
            except Exception as e:
                _log(f"[fetch-jd] Apple SSR error: {e}")

        # --- Taleo (taleo.net) — JS-rendered, cannot scrape ---
        if "taleo.net" in url:
            _log(f"[fetch-jd] Taleo URL detected — content is JS-rendered, scraping not possible")
            r = http_requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
            if r.status_code == 200:
                og_title = re.search(r'property="og:title"\s+content="([^"]+)"', r.text, re.I)
                og_site = re.search(r'property="og:site_name"\s+content="([^"]+)"', r.text, re.I)
                if og_title:
                    result["title"] = html.unescape(og_title.group(1).strip())
                if og_site:
                    result["company"] = og_site.group(1).strip()
                if not result["title"]:
                    title_m = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
                    if title_m:
                        result["title"] = title_m.group(1).strip()
                result["ats"] = "taleo"
            return result

        # --- Fallback: scrape page for text ---
        r = http_requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        if r.status_code == 200:
            html_content = r.text
            # Remove script tags, style tags, and their content before stripping HTML
            cleaned = re.sub(r'<script[^>]*>.*?</script>', ' ', html_content, flags=re.S | re.I)
            cleaned = re.sub(r'<style[^>]*>.*?</style>', ' ', cleaned, flags=re.S | re.I)
            cleaned = re.sub(r'<noscript[^>]*>.*?</noscript>', ' ', cleaned, flags=re.S | re.I)
            # Remove HTML comments
            cleaned = re.sub(r'<!--.*?-->', ' ', cleaned, flags=re.S)
            # Remove import maps and JSON-LD blocks
            cleaned = re.sub(r'<script\s+type=["\']importmap["\'][^>]*>.*?</script>', ' ', cleaned, flags=re.S | re.I)

            text = _strip_html(cleaned)

            # Filter out lines that look like JS/CSS artifacts
            lines = text.split('\n')
            good_lines = []
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                # Skip lines that look like JS: import statements, variable assignments, URLs, etc.
                if re.match(r'^(import |export |var |let |const |function |window\.|document\.|\{|\}|//|/\*)', line_stripped):
                    continue
                if re.match(r'^https?://', line_stripped):
                    continue
                # Skip lines that are mostly special characters (minified code)
                alnum_count = sum(1 for c in line_stripped if c.isalnum() or c == ' ')
                if len(line_stripped) > 20 and alnum_count / len(line_stripped) < 0.5:
                    continue
                good_lines.append(line_stripped)

            text = '\n'.join(good_lines).strip()
            # Collapse multiple whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r'[ \t]{2,}', ' ', text)

            if len(text) > 200:
                result["description"] = text[:15000]

            # Prefer OG/meta tags over raw <title> for structured data
            og_title = re.search(r'property="og:title"\s+content="([^"]+)"', html_content, re.I)
            og_desc = re.search(r'property="og:description"\s+content="([^"]+)"', html_content, re.I)
            og_site = re.search(r'property="og:site_name"\s+content="([^"]+)"', html_content, re.I)
            if og_title:
                result["title"] = html.unescape(og_title.group(1).strip())
            if og_desc and not result["description"]:
                result["description"] = html.unescape(og_desc.group(1).strip())
            if og_site and not result["company"]:
                result["company"] = og_site.group(1).strip()

            if not result["title"]:
                title_m = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.I)
                if title_m:
                    result["title"] = title_m.group(1).strip()

    except Exception as e:
        _log(f"[fetch-jd] Error fetching {url}: {e}")

    # --- Clean up company name ---
    COMPANY_NAME_MAP = {
        "amazon.jobs": "Amazon",
        "google careers": "Google",
        "microsoft careers": "Microsoft",
        "meta careers": "Meta",
        "apple jobs": "Apple",
        "apple careers at apple": "Apple",
        "netflix jobs": "Netflix",
    }
    if result["company"]:
        cleaned = COMPANY_NAME_MAP.get(result["company"].lower())
        if cleaned:
            result["company"] = cleaned
        # Strip trailing " careers", " jobs", ".jobs" suffixes
        else:
            result["company"] = re.sub(r'\s*(?:careers|jobs)$', '', result["company"], flags=re.I).strip()
            result["company"] = re.sub(r'\.jobs$', '', result["company"], flags=re.I).strip()

    # Also try to extract company from URL domain
    if not result["company"]:
        domain_match = re.search(r'https?://(?:www\.)?([^./]+)', url)
        if domain_match:
            result["company"] = domain_match.group(1).title()

    return result


class AddJobByUrl(BaseModel):
    url: str

@app.post("/api/jobs/add-by-url")
def add_job_by_url(body: AddJobByUrl):
    """Fetch job details from a URL and add to the queue."""
    import hashlib

    url = body.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")

    fetched = _fetch_jd_from_url(url)
    title = fetched["title"]
    company = fetched["company"]
    location = fetched["location"]
    description = fetched["description"]
    apply_link = fetched["apply_link"]
    ats_type = fetched["ats"]

    if not title:
        # Last resort: try to parse from URL
        try:
            r = http_requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                title_match = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
                if title_match:
                    raw_title = title_match.group(1).strip()
                    for sep in [" - ", " | ", " at ", " — ", " – "]:
                        if sep in raw_title:
                            parts = raw_title.split(sep)
                            title = parts[0].strip()
                            company = parts[1].strip() if len(parts) > 1 else ""
                            break
                    else:
                        title = raw_title
        except Exception:
            pass

    if not title:
        raise HTTPException(400, "Could not extract job details from URL")

    jid = hashlib.md5(url.encode()).hexdigest()[:12]

    # Check if a job with matching title+company already exists (e.g. from Simplify/JSearch discovery)
    existing_job = None
    if title and company:
        existing_jobs = db.get_jobs(search=title, limit=50)
        for ej in existing_jobs:
            if (ej.get("title", "").lower().strip() == title.lower().strip()
                    and ej.get("company", "").lower().strip() == company.lower().strip()):
                existing_job = ej
                break

    if existing_job:
        # Update the existing job in-place instead of creating a duplicate
        jid = existing_job["id"]
        overwrite = {"apply_link": apply_link}
        if description:
            overwrite["description"] = description
        if ats_type:
            overwrite["ats"] = ats_type
        if location and not existing_job.get("location"):
            overwrite["location"] = location
        db.update_job(jid, **overwrite)
    else:
        entry = {
            "id": jid,
            "title": title,
            "company": company,
            "location": location,
            "apply_link": apply_link,
            "ats": ats_type,
            "score": 0,
            "description": description,
            "posted_at": "",
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "source": "manual_url",
            "query": "",
        }
        db.upsert_jobs([entry])
        # Force-update key fields in case the job already existed with stale data
        overwrite = {}
        if title: overwrite["title"] = title
        if company: overwrite["company"] = company
        if location: overwrite["location"] = location
        if description: overwrite["description"] = description
        if ats_type: overwrite["ats"] = ats_type
        if overwrite:
            db.update_job(jid, **overwrite)

    return _parse_json_fields(db.get_job(jid))


# ---------------------------------------------------------------------------
# Application endpoints
# ---------------------------------------------------------------------------

@app.get("/api/applications")
def list_applications(status: str | None = None, search: str | None = None, limit: int = 100, offset: int = 0):
    return db.get_applications(status=status, search=search, limit=limit, offset=offset)

@app.get("/api/applications/stats")
def application_stats():
    return db.get_application_stats()

@app.post("/api/applications")
def create_application(body: ApplicationCreate):
    app_id = db.create_application(**body.model_dump())
    if body.job_id:
        db.update_job(body.job_id, status="applied")
    return {"id": app_id}

class ApplicationAddByUrl(BaseModel):
    url: str

@app.post("/api/applications/add-by-url")
def add_application_by_url(body: ApplicationAddByUrl):
    """Fetch job details from a URL and create an application directly."""
    import hashlib

    url = body.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")

    fetched = _fetch_jd_from_url(url)
    title = fetched["title"]
    company = fetched["company"]
    location = fetched["location"]
    description = fetched["description"]
    apply_link = fetched["apply_link"]
    ats_type = fetched["ats"]

    if not title:
        try:
            r = http_requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                title_match = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
                if title_match:
                    raw_title = title_match.group(1).strip()
                    for sep in [" - ", " | ", " at ", " — ", " – "]:
                        if sep in raw_title:
                            parts = raw_title.split(sep)
                            title = parts[0].strip()
                            company = parts[1].strip() if len(parts) > 1 else ""
                            break
                    else:
                        title = raw_title
        except Exception:
            pass

    if not title:
        raise HTTPException(400, "Could not extract job details from URL")

    # Also add to job queue so we have the JD stored
    jid = hashlib.md5(url.encode()).hexdigest()[:12]
    entry = {
        "id": jid,
        "title": title,
        "company": company,
        "location": location,
        "apply_link": apply_link,
        "ats": ats_type,
        "score": 0,
        "description": description,
        "posted_at": "",
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "source": "manual_url",
        "query": "",
    }
    db.upsert_jobs([entry])
    # Force-update key fields in case the job already existed with stale data
    overwrite = {"status": "applied"}
    if title: overwrite["title"] = title
    if company: overwrite["company"] = company
    if location: overwrite["location"] = location
    if description: overwrite["description"] = description
    if ats_type: overwrite["ats"] = ats_type
    db.update_job(jid, **overwrite)

    # Create the application
    app_id = db.create_application(
        job_id=jid,
        title=title,
        company=company,
        location=location,
        apply_link=apply_link,
        source=ats_type or "manual_url",
    )

    return {"id": app_id, "title": title, "company": company, "location": location, "job_id": jid}

@app.patch("/api/applications/{app_id}")
def update_application(app_id: int, body: ApplicationUpdate):
    db.update_application(app_id, **body.model_dump(exclude_none=True))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Recruiter endpoints
# ---------------------------------------------------------------------------

@app.get("/api/recruiters")
def list_recruiters(application_id: int | None = None):
    return db.get_recruiters(application_id=application_id)

@app.post("/api/recruiters")
def create_recruiter(body: RecruiterCreate):
    rid = db.create_recruiter(**body.model_dump())
    return {"id": rid}


# ---------------------------------------------------------------------------
# Reminder endpoints
# ---------------------------------------------------------------------------

@app.get("/api/reminders")
def list_reminders(include_completed: bool = False):
    return db.get_reminders(include_completed=include_completed)

@app.get("/api/reminders/due")
def due_reminders():
    return db.get_due_reminders()

@app.post("/api/reminders")
def create_reminder(body: ReminderCreate):
    rid = db.create_reminder(**body.model_dump())
    return {"id": rid}

@app.patch("/api/reminders/{reminder_id}/complete")
def complete_reminder(reminder_id: int):
    db.complete_reminder(reminder_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Discovery endpoint (runs in background)
# ---------------------------------------------------------------------------

def _load_discovery_status():
    """Restore persisted discovery status from DB (survives server restarts)."""
    return {
        "running": False,
        "last_run": db.kv_get("discovery_last_run"),
        "new_jobs": int(db.kv_get("discovery_new_jobs", "0")),
        "phase": "",
    }

discovery_status = _load_discovery_status()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")


def _fetch_adzuna(query: str, location: str = "us", pages: int = 3, max_days_old: int = 3) -> list:
    """Fetch jobs from Adzuna API. Free tier: 250 req/day."""
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("[adzuna] No API keys configured, skipping")
        return []

    jobs = []
    for page in range(1, pages + 1):
        try:
            resp = http_requests.get(
                f"https://api.adzuna.com/v1/api/jobs/{location}/search/{page}",
                params={
                    "app_id": ADZUNA_APP_ID,
                    "app_key": ADZUNA_APP_KEY,
                    "what": query,
                    "what_exclude": "senior staff principal director intern clearance",
                    "max_days_old": max_days_old,
                    "results_per_page": 20,
                    "full_time": 1,
                    "sort_by": "date",
                    "content-type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                _log(f"[adzuna] Page {page} failed: HTTP {resp.status_code}")
                break
            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            jobs.extend(results)
            import time
            time.sleep(0.3)
        except Exception as e:
            _log(f"[adzuna] Page {page} failed: {e}")
            break
    return jobs


def _run_discovery(queries: list[str], location: str, skip_jsearch: bool, skip_ats: bool, freshness_hours: int = 24, skip_adzuna: bool = False, skip_simplify: bool = False):
    discovery_status["running"] = True
    discovery_status["phase"] = "Starting..."
    total_new = 0

    date_posted_map = {24: "today", 72: "3days", 168: "week", 720: "month"}
    date_posted = min(date_posted_map.items(), key=lambda x: abs(x[0] - freshness_hours))[1]

    try:
        if not skip_jsearch and JSEARCH_KEY:
            discovery_status["phase"] = "Fetching JSearch..."
            from config import SEARCH_KEYWORDS
            qs = queries or SEARCH_KEYWORDS
            blacklist = load_json(BLACKLIST_PATH)

            for query in qs:
                raw = fetch_jobs(query, location=location, date_posted=date_posted)
                for job in raw:
                    country = (job.get("job_country") or "").lower().strip()
                    if country and country not in ("us", "united states", "usa"):
                        continue
                    jid = job_id(job)
                    if not _is_fresh(job, max_age_hours=freshness_hours):
                        continue
                    if db.is_company_blocked(job.get("employer_name", "")):
                        continue
                    link = _best_apply_link(job)
                    if not link:
                        continue
                    if is_blacklisted(job, blacklist):
                        continue
                    sc = score_job(job)
                    if sc < SCORE_THRESHOLD:
                        continue
                    skip, _ = llm.hard_skip_check(
                        job.get("job_title", ""),
                        job.get("job_description", ""),
                        job.get("employer_name", ""),
                    )
                    if skip:
                        continue
                    ats_name = next(
                        (d.split(".")[0] for d in ALLOWED_PUBLISHERS if d in link),
                        "other"
                    )
                    entry = {
                        "id": jid,
                        "title": job.get("job_title"),
                        "company": job.get("employer_name"),
                        "location": (job.get("job_city") or "") + ", " + (job.get("job_country") or ""),
                        "apply_link": link,
                        "ats": ats_name,
                        "score": sc,
                        "description": job.get("job_description", ""),
                        "posted_at": job.get("job_posted_at_datetime_utc", ""),
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        "source": "jsearch",
                        "query": query,
                    }
                    total_new += db.upsert_jobs([entry])

        # --- Adzuna ---
        if not skip_adzuna and ADZUNA_APP_ID:
            discovery_status["phase"] = "Fetching Adzuna..."
            from config import SEARCH_KEYWORDS
            from ats_discovery import _is_us_location
            qs = queries or SEARCH_KEYWORDS
            blacklist = load_json(BLACKLIST_PATH)
            max_days = max(1, int(freshness_hours / 24))

            for query in qs:
                raw = _fetch_adzuna(query, location="us", pages=2, max_days_old=max_days)
                _log(f"[adzuna] '{query}': {len(raw)} results")
                for aj in raw:
                    company_name = (aj.get("company") or {}).get("display_name", "")
                    title = aj.get("title", "")
                    link = aj.get("redirect_url", "")
                    loc = aj.get("location", {}).get("display_name", "")

                    if not link or not title:
                        continue
                    if not _is_us_location(loc):
                        continue
                    if db.is_company_blocked(company_name):
                        continue

                    jid = _job_id(company_name, title, link)
                    desc = aj.get("description", "")

                    # Build a job dict compatible with score_job
                    job_dict = {
                        "job_title": title,
                        "job_description": desc,
                        "employer_name": company_name,
                        "job_apply_is_direct": False,
                    }
                    if is_blacklisted(job_dict, blacklist):
                        continue
                    sc = score_job(job_dict)
                    if sc < SCORE_THRESHOLD:
                        continue
                    skip, _ = llm.hard_skip_check(title, desc, company_name)
                    if skip:
                        continue

                    entry = {
                        "id": jid,
                        "title": title,
                        "company": company_name,
                        "location": loc,
                        "apply_link": link,
                        "ats": "other",
                        "score": sc,
                        "description": desc,
                        "posted_at": aj.get("created", ""),
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        "source": "adzuna",
                        "query": query,
                    }
                    total_new += db.upsert_jobs([entry])

        if not skip_ats:
            discovery_status["phase"] = "Fetching ATS companies..."
            companies = json.loads(Path("companies.json").read_text())
            import ats_discovery
            from ats_discovery import (
                fetch_greenhouse, fetch_lever, fetch_ashby,
                fetch_amazon, fetch_workday, fetch_pinpoint,
                fetch_linkedin,
            )
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import time
            ats_discovery.FRESHNESS_DAYS = max(1, freshness_hours / 24)

            # Track consecutive failures per ATS to bail early when service is down
            ats_fail_count = {}
            ATS_FAIL_THRESHOLD = 3  # skip remaining companies after 3 consecutive failures
            skipped_ats_types = set()

            # Group companies by ATS type for smarter batching
            def _fetch_company(company):
                name = company.get("name", "")
                ats_type = (company.get("ats") or "").lower()
                slug = company.get("slug", "")
                linkedin_id = company.get("linkedin_id", "")

                if not name or not ats_type:
                    return ats_type, name, [], False
                if ats_type not in ("linkedin", "amazon", "apple") and not slug:
                    return ats_type, name, [], False
                if db.is_company_blocked(name):
                    return ats_type, name, [], False

                try:
                    if ats_type == "greenhouse":
                        raw = fetch_greenhouse(slug, name)
                    elif ats_type == "lever":
                        raw = fetch_lever(slug, name)
                    elif ats_type == "ashby":
                        raw = fetch_ashby(slug, name)
                    elif ats_type == "amazon":
                        raw = fetch_amazon(name)
                    elif ats_type == "linkedin":
                        if not linkedin_id:
                            return ats_type, name, [], False
                        raw = fetch_linkedin(linkedin_id, name)
                    elif ats_type == "workday":
                        raw = fetch_workday(slug, name, company.get("wd_num", 5), company.get("site", ""))
                    elif ats_type == "pinpoint":
                        raw = fetch_pinpoint(slug, name)
                    else:
                        return ats_type, name, [], False
                    return ats_type, name, raw, False
                except Exception as e:
                    _log(f"[ats] {name} ({ats_type}) fetch error: {e}")
                    return ats_type, name, [], True  # True = was an error

            # Process companies with concurrent fetching
            blacklist = load_json(BLACKLIST_PATH)
            with ThreadPoolExecutor(max_workers=12) as executor:
                futures = {}
                for company in companies:
                    ats_type = (company.get("ats") or "").lower()
                    if ats_type in skipped_ats_types:
                        continue
                    f = executor.submit(_fetch_company, company)
                    futures[f] = company

                for future in as_completed(futures):
                    ats_type, name, raw_jobs, was_error = future.result()

                    # Track consecutive failures per ATS type
                    if was_error or (not raw_jobs and ats_type in ("ashby",)):
                        ats_fail_count[ats_type] = ats_fail_count.get(ats_type, 0) + 1
                        if ats_fail_count[ats_type] >= ATS_FAIL_THRESHOLD:
                            _log(f"[ats] {ats_type} failed {ATS_FAIL_THRESHOLD}x consecutively — skipping remaining {ats_type} companies")
                            skipped_ats_types.add(ats_type)
                    else:
                        ats_fail_count[ats_type] = 0  # reset on success

                    for job in raw_jobs:
                        jid = _job_id(
                            job.get("employer_name", ""),
                            job.get("job_title", ""),
                            job.get("job_apply_link", ""),
                        )
                        title_lower = (job.get("job_title") or "").lower()
                        if any(kw in title_lower for kw in SKIP_TITLE_KEYWORDS):
                            continue
                        if is_blacklisted(job, blacklist):
                            continue
                        sc = score_job(job)
                        threshold = 25 if ats_type == "workday" else SCORE_THRESHOLD
                        if sc < threshold:
                            continue
                        skip, _ = llm.hard_skip_check(
                            job.get("job_title", ""),
                            job.get("job_description", ""),
                            name,
                        )
                        if skip:
                            continue

                        entry = {
                            "id": jid,
                            "title": job.get("job_title"),
                            "company": name,
                            "location": job.get("job_city", ""),
                            "apply_link": job.get("job_apply_link"),
                            "ats": ats_type,
                            "score": sc,
                            "description": job.get("job_description", ""),
                            "posted_at": job.get("job_posted_at_datetime_utc", ""),
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                            "source": ats_type,
                            "query": "",
                        }
                        total_new += db.upsert_jobs([entry])

        # --- SimplifyJobs GitHub (New-Grad-Positions) ---
        if not skip_simplify:
            discovery_status["phase"] = "Fetching Simplify GitHub..."
            try:
                simplify_jobs = fetch_simplify_github(freshness_days=max(1, freshness_hours / 24))
                _log(f"[simplify] {len(simplify_jobs)} jobs passed filters")
                blacklist = load_json(BLACKLIST_PATH)
                for job in simplify_jobs:
                    jid = _job_id(
                        job.get("employer_name", ""),
                        job.get("job_title", ""),
                        job.get("job_apply_link", ""),
                    )
                    title_lower = (job.get("job_title") or "").lower()
                    if any(kw in title_lower for kw in SKIP_TITLE_KEYWORDS):
                        continue
                    if is_blacklisted(job, blacklist):
                        continue
                    if db.is_company_blocked(job.get("employer_name", "")):
                        continue
                    sc = score_job(job)
                    # Simplify listings have no description, so score is title-only — use lower threshold
                    if sc < 25:
                        continue

                    entry = {
                        "id": jid,
                        "title": job.get("job_title"),
                        "company": job.get("employer_name", ""),
                        "location": job.get("job_city", ""),
                        "apply_link": job.get("job_apply_link"),
                        "ats": "simplify",
                        "score": sc,
                        "description": job.get("job_description", ""),
                        "posted_at": job.get("job_posted_at_datetime_utc", ""),
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        "source": "simplify",
                        "query": "",
                    }
                    total_new += db.upsert_jobs([entry])
            except Exception as e:
                _log(f"[simplify] Error: {e}")

    finally:
        now = datetime.now(timezone.utc).isoformat()
        discovery_status["running"] = False
        discovery_status["phase"] = ""
        discovery_status["last_run"] = now
        discovery_status["new_jobs"] = total_new
        # Persist so it survives server restarts
        db.kv_set("discovery_last_run", now)
        db.kv_set("discovery_new_jobs", str(total_new))


@app.post("/api/discover")
def trigger_discovery(body: DiscoverRequest, background_tasks: BackgroundTasks):
    if discovery_status["running"]:
        raise HTTPException(409, "Discovery already running")
    background_tasks.add_task(
        _run_discovery, body.queries, body.location, body.skip_jsearch, body.skip_ats, body.freshness_hours, body.skip_adzuna, body.skip_simplify,
    )
    return {"status": "started"}

@app.get("/api/discover/status")
def get_discovery_status():
    return discovery_status


# ---------------------------------------------------------------------------
# LLM JD match + resume recommendation + hard-skip analysis
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/match")
def match_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    jd = job.get("description", "")
    title = job.get("title", "")
    company = job.get("company", "")

    # Auto-fetch JD if missing (e.g. Simplify jobs have no description)
    if not jd.strip() and job.get("apply_link"):
        _log(f"[match] No description for {company} — {title}, fetching from URL...")
        fetched = _fetch_jd_from_url(job["apply_link"])
        if fetched.get("description", "").strip():
            jd = fetched["description"]
            # Persist the fetched description so we don't need to re-fetch
            db.update_job(job_id, description=jd)
            _log(f"[match] Fetched JD ({len(jd)} chars) from {job['apply_link'][:60]}...")
        else:
            _log(f"[match] Could not fetch JD from {job['apply_link'][:60]}")

    recommended_resume, scores, matched_kw = get_resume_type(title, jd)
    resume_text = get_resume_text(recommended_resume)

    base_result = {
        "recommended_resume": recommended_resume,
        "resume_scores": scores,
        "matched_keywords": {k: v[:5] for k, v in matched_kw.items()},
    }

    skip, skip_reason = llm.hard_skip_check(title, jd, company)
    if skip:
        db.update_job(job_id, match_pct=0, match_summary=f"Auto-skipped: {skip_reason}",
                      recommended_resume=recommended_resume,
                      resume_scores=json.dumps(scores),
                      matched_keywords=json.dumps({k: v[:5] for k, v in matched_kw.items()}))
        return {**base_result, "match_pct": 0, "summary": f"Auto-skipped: {skip_reason}",
                "team": None, "project": None, "hard_skip": True, "skip_reason": skip_reason}

    if not llm.is_available():
        return {**base_result, "match_pct": None,
                "summary": "No LLM configured — showing resume recommendation only",
                "team": None, "project": None}

    if not jd:
        return {**base_result, "match_pct": None,
                "summary": "No description available for this job",
                "team": None, "project": None}

    if not resume_text:
        return {**base_result, "match_pct": None,
                "summary": f"No resume file found. Place .txt files in resumes/ directory (e.g. resumes/{recommended_resume}.txt)",
                "team": None, "project": None}

    system_prompt = (
        "You are a brutally honest technical recruiter reviewing a candidate's resume against a job description.\n"
        "Write your summary as if speaking DIRECTLY TO the candidate (use 'you/your', NOT 'this candidate/their').\n"
        "Compare specific resume experience against specific JD requirements — cite exact technologies, years, and projects.\n\n"
        "CANDIDATE PROFILE (memorize this):\n"
        "- MS in Software Engineering Systems (Northeastern, graduated Dec 2025)\n"
        "- 3+ years professional experience at IBM (Associate + Application Developer)\n"
        "- Currently working as AI Software Engineer at Humanitarians AI (nonprofit)\n"
        "- NO PhD. NO security clearance. ~3.5 years professional experience total.\n"
        "- Strong: Java/Spring Boot, Python, React/TypeScript, Node.js, LLM/RAG/agents\n"
        "- Weak: No C/C++, no robotics, no embedded systems, no ML research publications\n"
        "- Needs visa sponsorship (international student on OPT)\n\n"
        "Respond with ONLY a valid JSON object (no markdown fences):\n"
        "{\n"
        '  "match_pct": <integer 0-100>,\n'
        '  "summary": "<2-3 sentences in 2nd person: address the candidate as you. Compare their specific resume skills/experience against specific JD requirements. Be precise — name technologies, years, projects. Example: Your Spring Boot and React experience directly matches their full-stack requirement, but they need 5+ years and you have ~3.>",\n'
        '  "team": "<team name from JD, or null>",\n'
        '  "project": "<project/product name from JD, or null>",\n'
        '  "key_strengths": ["<strength1>", "<strength2>"],\n'
        '  "gaps": ["<gap1>", "<gap2>"],\n'
        '  "min_years_required": <integer or null>,\n'
        '  "requires_phd": <true if PhD is listed as REQUIRED (not preferred), else false>,\n'
        '  "requires_clearance": <true if security clearance is required, else false>,\n'
        '  "sponsorship_available": <true if they explicitly say they sponsor visas, false ONLY if the JD text explicitly says they do NOT sponsor (e.g. "no visa sponsorship", "will not sponsor"). null if not mentioned. IMPORTANT: E-Verify statements are NOT "no sponsorship" — E-Verify is standard employment verification that all employers use, including those who sponsor visas. Do NOT guess based on company reputation or E-Verify.>,\n'
        '  "seniority_level": "<junior|mid|senior|staff|lead|principal|director>",\n'
        '  "is_ml_specialist_role": <true if the PRIMARY job function is ML model training/research/data science rather than software engineering>,\n'
        '  "salary_min": <integer or null — lowest annual base salary in USD from the JD compensation range. Convert hourly to annual (×2080). null if not mentioned>,\n'
        '  "salary_max": <integer or null — highest annual base salary in USD from the JD compensation range. null if not mentioned>,\n'
        '  "scam_flag": <true if fake/scam posting>\n'
        "}\n\n"
        "SCORING — USE THE FULL RANGE, DO NOT CLUSTER AROUND 60-75:\n"
        "- 90-100: Perfect fit — right seniority, right stack, right experience level\n"
        "- 80-89: Excellent — meets nearly all requirements, minor gaps only\n"
        "- 70-79: Good — solid skill overlap, experience level is reasonable\n"
        "- 55-69: Decent — has some relevant skills but clear gaps\n"
        "- 40-54: Stretch — missing significant requirements\n"
        "- 20-39: Unlikely — major mismatches in experience or skills\n"
        "- 0-19: No chance — deal-breakers present\n\n"
        "HARD RULES (violating these = automatic score cap):\n"
        "- PhD REQUIRED (not preferred): cap at 35 — candidate has MS only\n"
        "- Security clearance required: cap at 10\n"
        "- No sponsorship / must be authorized to work: cap at 5 — ONLY if the JD explicitly states 'no visa sponsorship', 'will not sponsor', etc. E-Verify is NOT a sponsorship restriction. Do NOT assume based on company name, salary, or E-Verify.\n"
        "- Principal/Director level: cap at 15\n"
        "- Requires C/C++ as PRIMARY language: cap at 30 — candidate doesn't know C++\n"
        "- Salary >$300K usually means senior+ — factor seniority mismatch\n"
        "- ML Engineer/Scientist roles requiring model training, ML research, or deep statistics: cap at 45\n"
        "  (candidate builds APPS with LLMs/AI, does NOT train models or do ML research)\n\n"
        "SENIORITY GUIDANCE (penalize, do NOT hard cap):\n"
        "- Senior/Staff/Lead with 5+ years required: candidate has ~3 years. Penalize 10-15 points but score based on actual skill match. A strong skill match with a seniority gap can still score 60-75.\n"
        "- Senior roles with 3-4 years required: minor penalty (5-10 points), candidate is close\n\n"
        "GOOD MATCH SIGNALS (score 75+):\n"
        "- New grad / entry-level / 0-2 years roles\n"
        "- Java + Spring Boot backend roles\n"
        "- Python backend / infrastructure / platform roles\n"
        "- Python + LLM/AI/RAG/agents APPLICATION roles (building with AI, NOT training models)\n"
        "- React + TypeScript frontend roles\n"
        "- Full stack (Node + React + PostgreSQL)\n"
        "- Backend/platform engineer roles (APIs, distributed systems, cloud infra)\n"
        "- Titles with 'Associate', 'Junior', 'New Grad', 'SDE I', 'SDE 1', 'Engineer II'\n\n"
        "POOR MATCH SIGNALS (score lower):\n"
        "- ML Engineer / Data Scientist / Research Scientist requiring model training, MLOps,\n"
        "  ML pipelines, statistical modeling, recommendation systems, anomaly detection algorithms\n"
        "- Roles where PRIMARY skill is ML/data science, not software engineering\n"
        "- DevOps/SRE/Infrastructure-only roles with no application development\n\n"
        "LOCATION: Do NOT penalize for location — candidate relocates anywhere in US.\n"
        "PREFERRED vs REQUIRED: Only penalize for REQUIRED qualifications.\n"
        "Flag scam_flag=true if JD is generic, company seems fake, or harvests data."
    )

    jd_for_llm = jd

    user_prompt = (
        f"RESUME:\n{resume_text[:3000]}\n\n"
        f"JOB TITLE: {title}\n"
        f"COMPANY: {company}\n\n"
        f"JOB DESCRIPTION:\n{jd_for_llm}"
    )

    raw = llm.call(system_prompt, user_prompt)
    if not raw:
        raise HTTPException(502, "LLM call returned empty response")

    result = llm.parse_json(raw)
    if not result:
        _log(f"[match] Failed to parse LLM response: {raw[:500]}")
        raise HTTPException(502, f"Could not parse LLM response")

    # --- Hard enforcement caps (LLM may still be generous) ---
    score = result.get("match_pct", 50)
    warnings = []
    jd_lower = jd.lower()

    # Defense companies almost always require US person / clearance
    DEFENSE_COMPANIES = {
        "anduril", "palantir", "lockheed martin", "raytheon", "northrop grumman",
        "general dynamics", "bae systems", "l3harris", "leidos", "booz allen",
        "saic", "caci", "mantech", "peraton", "shield ai", "skydio",
    }
    is_defense = company.lower() in DEFENSE_COMPANIES

    # Text-based scan for citizenship/sponsorship requirements the LLM might have missed
    citizenship_patterns = [
        "u.s. citizen", "us citizen", "us person", "u.s. person",
        "must be a united states citizen", " itar ", "itar compliance", "itar regulated",
        "security clearance required",
        "active clearance", "top secret", "ts/sci", "secret clearance",
        "must be authorized to work", "will not sponsor", "does not sponsor",
        "no visa sponsorship", "unable to sponsor", "cannot sponsor",
        "must be legally authorized to work in the u",
        "work authorization is required", "work authorization required",
        "not eligible for visa sponsorship", "sponsorship is not available",
        "must have current work authorization",
    ]
    has_citizenship_text = any(p in jd_lower for p in citizenship_patterns)

    if result.get("scam_flag"):
        score = 0
        warnings.append("SCAM FLAG")

    if result.get("requires_clearance") or (is_defense and "clearance" in jd_lower):
        score = min(score, 10)
        warnings.append("CLEARANCE REQUIRED")

    if is_defense:
        if result.get("sponsorship_available") is not True:
            score = min(score, 5)
            warnings.append("DEFENSE CO — US PERSON REQUIRED")
    elif has_citizenship_text:
        # Only flag if the actual JD text contains sponsorship/citizenship language
        score = min(score, 5)
        warnings.append("NO SPONSORSHIP")

    if result.get("requires_phd"):
        score = min(score, 35)
        warnings.append("PhD REQUIRED")

    seniority = (result.get("seniority_level") or "").lower()
    if seniority in ("principal", "director"):
        score = min(score, 15)
        warnings.append(f"{seniority.upper()} LEVEL")
    elif seniority in ("senior", "staff", "lead"):
        min_years = result.get("min_years_required")
        if min_years and min_years >= 5:
            # Soft penalty: reduce by 15% instead of hard cap
            score = int(score * 0.85)
            warnings.append(f"SENIOR ({min_years}+ yrs required)")
        elif min_years and min_years >= 3:
            # Minor penalty for close-range seniority gap
            score = int(score * 0.92)

    # Experience penalty even if seniority wasn't detected (soft, not hard cap)
    min_years = result.get("min_years_required")
    if min_years and min_years >= 7:
        score = int(score * 0.75)
        if "yrs" not in " ".join(warnings).lower():
            warnings.append(f"Requires {min_years}+ years")
    elif min_years and min_years >= 5:
        # Only apply if seniority block didn't already penalize
        if seniority not in ("senior", "staff", "lead"):
            score = int(score * 0.85)
            if "yrs" not in " ".join(warnings).lower():
                warnings.append(f"Requires {min_years}+ years")
    elif min_years and min_years >= 4:
        score = min(score, 60)

    # ML specialist role cap — candidate builds apps WITH AI, doesn't train models
    if result.get("is_ml_specialist_role"):
        ml_keywords = ["model training", "mlops", "ml pipeline", "feature store",
                        "recommendation system", "anomaly detection", "ml lifecycle",
                        "model serving", "sagemaker", "mlflow", "kubeflow"]
        ml_hits = sum(1 for kw in ml_keywords if kw in jd_lower)
        if ml_hits >= 3:
            score = min(score, 40)
            warnings.append("ML SPECIALIST ROLE")
        elif ml_hits >= 1:
            score = min(score, 55)
            warnings.append("ML-heavy role")

    result["match_pct"] = score
    if warnings:
        prefix = "[" + " | ".join(warnings) + "] "
        result["summary"] = prefix + result.get("summary", "")

    scores_json = json.dumps(scores)
    keywords_json = json.dumps({k: v[:5] for k, v in matched_kw.items()})
    salary_min = result.get("salary_min")
    salary_max = result.get("salary_max")
    update_kwargs = dict(
        match_pct=result.get("match_pct"),
        match_summary=result.get("summary"),
        team=result.get("team"),
        project=result.get("project"),
        recommended_resume=recommended_resume,
        resume_scores=scores_json,
        matched_keywords=keywords_json,
    )
    if salary_min is not None:
        update_kwargs["salary_min"] = salary_min
    if salary_max is not None:
        update_kwargs["salary_max"] = salary_max
    db.update_job(job_id, **update_kwargs)
    result["recommended_resume"] = recommended_resume
    result["resume_scores"] = scores
    result["matched_keywords"] = {k: v[:5] for k, v in matched_kw.items()}
    return result


# ---------------------------------------------------------------------------
# Recruiter outreach message generator
# ---------------------------------------------------------------------------

class OutreachRequest(BaseModel):
    recruiter_name: str | None = None
    linkedin_post: str | None = None

@app.post("/api/jobs/{job_id}/outreach")
def generate_outreach(job_id: str, req: OutreachRequest = None):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Return cached outreach if available and no custom context provided
    has_custom = req and (req.recruiter_name or req.linkedin_post)
    if not has_custom and job.get("outreach_full") and job.get("outreach_short"):
        return {
            "full": job["outreach_full"],
            "short": job["outreach_short"],
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "cached": True,
        }

    if not llm.is_available():
        raise HTTPException(503, "No LLM configured")

    jd = job.get("description", "")
    title = job.get("title", "")
    company = job.get("company", "")
    team = job.get("team", "")
    match_summary = job.get("match_summary", "")

    if not jd:
        raise HTTPException(400, "No job description available")

    recruiter_name = (req.recruiter_name or "").strip() if req else ""
    linkedin_post = (req.linkedin_post or "").strip() if req else ""

    system_prompt = (
        "You generate LinkedIn recruiter outreach messages for a job applicant.\n\n"
        "CANDIDATE PROFILE:\n"
        "- MS in Software Engineering Systems (Northeastern, graduated Dec 2025)\n"
        "- 3+ years professional experience at IBM (Associate + Application Developer)\n"
        "- Currently working as AI Software Engineer at Humanitarians AI (nonprofit)\n"
        "- Strong: Java/Spring Boot, Python, React/TypeScript, Node.js, LLM/RAG/agents\n"
        "- Built full stack apps, AI pipelines, distributed systems\n\n"
        "STRICT RULES:\n"
        "1. Generate TWO versions: a full message (150-250 words) and a short version (STRICTLY under 260 characters, leave room for salutations)\n"
        "2. SHORT VERSION OPENING (follow EXACTLY, do NOT add extra words before 'I applied'):\n"
        "   With recruiter name: 'Hey [Name]! Wanted to put a face to my resume! I applied for the [role] role.'\n"
        "   Without recruiter name: 'Hey! Wanted to put a face to my resume! I applied for the [role] role.'\n"
        "   CRITICAL: Do NOT add the word 'just' anywhere. 'Just wanted' is BANNED. Write 'Wanted to' not 'Just wanted to'.\n"
        "3. Always mention that you applied\n"
        "4. Include a human touch and offer to share resume\n"
        "5. Reference something SPECIFIC from the JD or LinkedIn post\n"
        "6. Be VERY optimistic about the match\n"
        "7. NEVER mention visa, OPT, sponsorship, work authorization, or immigration status\n"
        "8. BANNED WORDS (never use): resonated, resonate, stood out, thrills, thrilled, excited to, "
        "passionate about, delighted, I wanted to reach out, stood out to me\n"
        "9. NO hyphens, dashes, em dashes, or en dashes ANYWHERE. This is the highest priority rule.\n"
        "10. Must sound like a real human wrote it, not AI. Be casual and natural.\n"
        "11. No AI sounding words or corporate buzzwords\n"
        "12. If a LinkedIn post is provided, acknowledge something specific from it and mirror the poster's tone\n\n"
        "Respond with ONLY a valid JSON object (no markdown fences):\n"
        "{\n"
        '  "full": "<the full message, 150-250 words>",\n'
        '  "short": "<the short version, MUST be under 260 characters>"\n'
        "}"
    )

    # Build context for the LLM
    jd_snippet = jd[:2000] if len(jd) > 2000 else jd
    user_parts = [
        f"JOB TITLE: {title}",
        f"COMPANY: {company}",
    ]
    if team:
        user_parts.append(f"TEAM: {team}")
    if match_summary:
        user_parts.append(f"MATCH ANALYSIS: {match_summary}")
    if recruiter_name:
        user_parts.append(f"RECRUITER NAME: {recruiter_name}")
    if linkedin_post:
        user_parts.append(f"LINKEDIN POST BY RECRUITER:\n{linkedin_post[:1000]}")
    user_parts.append(f"JOB DESCRIPTION:\n{jd_snippet}")

    user_prompt = "\n\n".join(user_parts)

    raw = llm.call(system_prompt, user_prompt)
    if not raw:
        raise HTTPException(502, "LLM call returned empty response")

    result = llm.parse_json(raw)
    if not result or "full" not in result or "short" not in result:
        raise HTTPException(502, "Could not parse outreach messages")

    # Enforce no dashes (highest priority rule)
    for key in ("full", "short"):
        result[key] = result[key].replace("—", " ").replace("–", " ").replace("-", " ")

    # Strip "just" from short version opening — LLM keeps adding it despite instructions
    import re
    result["short"] = re.sub(r'^(Hey[^!]*!) *[Jj]ust wanted', r'\1 Wanted', result["short"])
    result["short"] = re.sub(r'[Jj]ust wanted to put', 'Wanted to put', result["short"])

    # Log if short version exceeds target (LLM should handle length)
    if len(result["short"]) > 260:
        _log(f"[outreach] Short version is {len(result['short'])} chars (target: 260)")

    # Persist to DB
    db.update_job(job_id, outreach_full=result["full"], outreach_short=result["short"])

    return {
        "full": result["full"],
        "short": result["short"],
        "job_title": title,
        "company": company,
    }


# ---------------------------------------------------------------------------
# LinkedIn recruiter search builder — US geoId filter
# ---------------------------------------------------------------------------

LINKEDIN_OVERRIDES_PATH = Path("linkedin_overrides.json")


def _load_linkedin_overrides() -> dict:
    if LINKEDIN_OVERRIDES_PATH.exists():
        try:
            return json.loads(LINKEDIN_OVERRIDES_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_linkedin_overrides(data: dict):
    LINKEDIN_OVERRIDES_PATH.write_text(json.dumps(data, indent=2))


def _normalize_company(name: str) -> str:
    """Normalize company name for matching — strips suffixes like Inc., Corp., etc."""
    key = name.lower().strip()
    # Remove common suffixes
    key = re.sub(r',?\s*(inc\.?|corp\.?|corporation|llc|ltd\.?|co\.?|technologies|technology|software|systems|group|holdings)$', '', key).strip()
    # Remove trailing punctuation
    key = key.rstrip('.,')
    return key


def _get_linkedin_id(company: str) -> tuple[str | None, bool]:
    """Returns (linkedin_id, is_verified). Checks overrides first, then companies.json."""
    overrides = _load_linkedin_overrides()
    key = company.lower().strip()
    normalized = _normalize_company(company)

    # Exact match first, then normalized match
    if key in overrides:
        return overrides[key], True
    for okey, oval in overrides.items():
        if _normalize_company(okey) == normalized:
            return oval, True

    try:
        companies = json.loads(Path("companies.json").read_text())
        for c in companies:
            cname = c.get("name", "").lower()
            if (cname == key or _normalize_company(cname) == normalized) and c.get("linkedin_id"):
                return c["linkedin_id"], False
    except Exception:
        pass
    return None, False


@app.get("/api/jobs/{job_id}/linkedin-search")
def linkedin_search(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    company = job.get("company", "")

    linkedin_id, verified = _get_linkedin_id(company)

    # LinkedIn keyword search matches titles AND headlines/taglines
    # Extract a short, clean role from the job title for "hiring <role>" matching
    title = job.get("title", "")
    role_hint = title.strip()
    # Drop team/qualifier suffixes: "Engineer, Database" or "Engineer - Platform" or "Engineer (Cloud)"
    role_hint = re.split(r'\s*[,(|\-–—]\s*', role_hint)[0].strip()
    # Remove seniority prefixes
    for prefix in ["Associate ", "Senior ", "Staff ", "Principal ", "Lead ", "Junior ", "Jr. ", "Sr. "]:
        if role_hint.startswith(prefix):
            role_hint = role_hint[len(prefix):].strip()
            break
    # Remove level suffixes: "Engineer 3", "Engineer II", "SDE III", "Developer I"
    role_hint = re.sub(r'\s+[IVX]+$', '', role_hint)
    role_hint = re.sub(r'\s+\d+$', '', role_hint)
    # Normalize verbose titles to what recruiters actually write in their headlines
    ROLE_NORMALIZE = {
        "software development engineer": "software engineer",
        "software dev engineer": "software engineer",
        "sde": "software engineer",
        "swe": "software engineer",
    }
    role_lower = role_hint.lower()
    if role_lower in ROLE_NORMALIZE:
        role_hint = ROLE_NORMALIZE[role_lower]
    # Cap length — keep it short for LinkedIn
    if len(role_hint) > 30:
        role_hint = " ".join(role_hint.split()[:3])

    # Use LinkedIn's title filter to restrict to recruiter-type roles
    # This prevents matching random SWEs who have "technical" in their headline
    title_filter = "recruiter OR talent acquisition OR sourcer"

    if linkedin_id and verified:
        query = f'"hiring {role_hint}" OR recruiter OR "talent acquisition"'
    else:
        query = f'{company} recruiter'

    url = "https://www.linkedin.com/search/results/people/?"
    url += f"keywords={urllib.parse.quote(query)}"
    url += f"&titleFreeText={urllib.parse.quote(title_filter)}"
    url += f"&geoUrn=%5B%22103644278%22%5D"
    url += "&origin=FACETED_SEARCH"
    if linkedin_id and verified:
        url += f"&currentCompany=%5B%22{linkedin_id}%22%5D"

    return {"url": url, "query": query, "title_filter": title_filter, "company": company, "linkedin_id": linkedin_id, "verified": verified}


@app.get("/api/linkedin-id")
def get_linkedin_id(company: str = ""):
    if not company.strip():
        raise HTTPException(400, "company query param required")
    lid, verified = _get_linkedin_id(company.strip())
    return {"company": company.strip(), "linkedin_id": lid, "verified": verified}


@app.patch("/api/linkedin-id")
def update_linkedin_id(body: dict):
    company = body.get("company", "").strip()
    lid = body.get("linkedin_id", "").strip()
    if not company or not lid:
        raise HTTPException(400, "company and linkedin_id required")
    overrides = _load_linkedin_overrides()
    # Store under both exact and normalized keys for reliable lookups
    overrides[company.lower()] = lid
    normalized = _normalize_company(company)
    if normalized != company.lower():
        overrides[normalized] = lid
    _save_linkedin_overrides(overrides)

    # Also update companies.json if the company exists there
    try:
        companies_path = Path("companies.json")
        companies = json.loads(companies_path.read_text())
        updated = False
        for c in companies:
            if c.get("name", "").lower() == company.lower() or _normalize_company(c.get("name", "")) == normalized:
                c["linkedin_id"] = lid
                updated = True
                break
        if updated:
            companies_path.write_text(json.dumps(companies, indent=2))
    except Exception as e:
        _log(f"[linkedin-id] Failed to update companies.json: {e}")

    return {"ok": True, "company": company, "linkedin_id": lid}


@app.get("/api/jobs/{job_id}/linkedin-leaders")
def linkedin_leaders(job_id: str, role: str = "hiring"):
    """
    LinkedIn search for people who can help get hired.
    role param lets the frontend switch between search strategies:
      - hiring  = engineering managers / directors (decision makers)
      - team    = staff/senior engineers on the team (referral sources)
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    company = job.get("company", "")
    team = job.get("team") or ""
    title = job.get("title", "")

    # Extract a useful team/domain hint from the job title
    # e.g. "Senior Software Engineer, Payments" -> "Payments"
    team_hint = team
    if not team_hint:
        # Try to grab the part after a comma/dash in the title
        for sep in [",", " - ", " – ", " | "]:
            if sep in title:
                team_hint = title.split(sep, 1)[1].strip()
                break

    linkedin_id, verified = _get_linkedin_id(company)

    if role == "team":
        # Find senior/staff engineers on the team who can refer
        if team_hint:
            title_terms = f"software engineer {team_hint}"
        else:
            title_terms = "senior software engineer"
    else:
        # Find hiring decision makers
        if team_hint:
            title_terms = f"engineering manager {team_hint}"
        else:
            title_terms = "engineering manager"

    # If we have verified company ID, don't waste keywords on company name
    if linkedin_id and verified:
        keywords = title_terms
    else:
        keywords = f"{company} {title_terms}"

    url = "https://www.linkedin.com/search/results/people/?"
    url += f"keywords={urllib.parse.quote(keywords)}"
    url += "&geoUrn=%5B%22103644278%22%5D"
    url += "&origin=FACETED_SEARCH"
    if linkedin_id and verified:
        url += f"&currentCompany=%5B%22{linkedin_id}%22%5D"

    return {"url": url, "query": keywords, "company": company, "role": role}


# ---------------------------------------------------------------------------
# Hunter.io — email finder
# ---------------------------------------------------------------------------

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")


@app.get("/api/jobs/{job_id}/find-emails")
def find_emails(job_id: str):
    """Use Hunter.io to find emails at the company domain."""
    if not HUNTER_API_KEY:
        raise HTTPException(400, "HUNTER_API_KEY not configured. Add it to .env")

    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    company = job.get("company", "")

    # Step 1: Find the company domain via Hunter domain-search
    try:
        search_resp = http_requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "company": company,
                "api_key": HUNTER_API_KEY,
                "limit": 10,
            },
            timeout=15,
        )
        data = search_resp.json()

        if search_resp.status_code != 200:
            errors = data.get("errors", [])
            msg = errors[0].get("details", "Hunter API error") if errors else "Hunter API error"
            raise HTTPException(search_resp.status_code, msg)

        result = data.get("data", {})
        domain = result.get("domain", "")
        pattern = result.get("pattern", "")
        emails = result.get("emails", [])

        people = []
        for e in emails:
            person = {
                "email": e.get("value", ""),
                "first_name": e.get("first_name", ""),
                "last_name": e.get("last_name", ""),
                "position": e.get("position", ""),
                "department": e.get("department", ""),
                "linkedin": e.get("linkedin", ""),
                "confidence": e.get("confidence", 0),
            }
            people.append(person)

        # Save to collected_emails DB
        if people:
            db.save_collected_emails(
                company=company,
                domain=domain,
                people=people,
                job_id=job_id,
                job_title=job.get("title", ""),
            )

        return {
            "company": company,
            "domain": domain,
            "pattern": pattern,
            "people": people,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Hunter.io lookup failed: {e}")


# ---------------------------------------------------------------------------
# Collected Emails dashboard
# ---------------------------------------------------------------------------

@app.get("/api/collected-emails")
def list_collected_emails(company: str = None, limit: int = 200, offset: int = 0):
    return db.get_collected_emails(company=company, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard():
    return {
        "job_stats": db.get_job_stats(),
        "app_stats": db.get_application_stats(),
        "due_reminders": db.get_due_reminders(),
        "discovery": discovery_status,
    }


@app.get("/api/evaluations")
def list_evaluations(limit: int = 50):
    return db.get_evaluated_jobs(limit=limit)


@app.post("/api/jobs/cleanup-non-us")
def cleanup_non_us():
    count = db.delete_non_us_jobs()
    return {"deleted": count}

@app.post("/api/jobs/clear-queue")
def clear_queue():
    count = db.clear_pending_jobs()
    return {"cleared": count}


# ---------------------------------------------------------------------------
# Blocked companies (no sponsorship, etc.)
# ---------------------------------------------------------------------------

class BlockCompanyRequest(BaseModel):
    company: str
    reason: str = "no sponsorship"

@app.get("/api/blocked-companies")
def list_blocked_companies():
    return db.get_blocked_companies()

@app.post("/api/blocked-companies")
def block_company(body: BlockCompanyRequest):
    db.block_company(body.company, body.reason)
    return {"ok": True, "company": body.company}

@app.delete("/api/blocked-companies/{company}")
def unblock_company(company: str):
    db.unblock_company(company)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Fix Workday URLs
# ---------------------------------------------------------------------------

@app.get("/api/analytics")
def get_analytics():
    return db.get_analytics()


@app.post("/api/jobs/fix-workday-urls")
def fix_workday_urls():
    companies = json.loads(Path("companies.json").read_text())
    fixed = db.fix_workday_urls(companies)
    return {"fixed": fixed}


@app.post("/api/jobs/backfill-descriptions")
def backfill_descriptions():
    """Fetch JDs for jobs that have an apply_link but no description."""
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, apply_link FROM jobs WHERE (description IS NULL OR description = '') AND apply_link != ''"
        ).fetchall()

    filled = 0
    errors = 0
    for row in rows:
        jid, url = row["id"], row["apply_link"]
        try:
            fetched = _fetch_jd_from_url(url)
            desc = fetched.get("description", "").strip()
            if desc:
                db.update_job(jid, description=desc)
                filled += 1
                _log(f"[backfill] Filled {jid} ({len(desc)} chars)")
            else:
                _log(f"[backfill] No JD found for {jid}: {url[:60]}")
        except Exception as e:
            errors += 1
            _log(f"[backfill] Error {jid}: {e}")

    _log(f"[backfill] Done: {filled} filled, {errors} errors, {len(rows) - filled - errors} no JD found")
    return {"total": len(rows), "filled": filled, "errors": errors}


# ---------------------------------------------------------------------------
# Auto-Apply Engine
# ---------------------------------------------------------------------------

class AutoApplyStart(BaseModel):
    min_score: int = 60
    limit: int = 50
    ext_wait: int = 8
    delay: int = 3

class AutoApplyAction(BaseModel):
    action: str   # applied | applied_recruiter | skip | stop

@app.post("/api/auto-apply/start")
def auto_apply_start(body: AutoApplyStart):
    ok = auto_apply_engine.start(
        min_score=body.min_score,
        limit=body.limit,
        ext_wait=body.ext_wait,
        delay=body.delay,
    )
    if not ok:
        status = auto_apply_engine.get_status()
        if status["status"] == "running":
            raise HTTPException(409, "Already running")
        raise HTTPException(400, status.get("error", "Failed to start"))
    return {"ok": True}

@app.get("/api/auto-apply/status")
def auto_apply_status():
    return auto_apply_engine.get_status()

@app.post("/api/auto-apply/stop")
def auto_apply_stop():
    auto_apply_engine.stop()
    return {"ok": True}

@app.post("/api/auto-apply/action")
def auto_apply_action(body: AutoApplyAction):
    auto_apply_engine.send_action(body.action)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)
