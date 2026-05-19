"""FastAPI backend for JobHunter dashboard."""

import os
import sys
import re
import json
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

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
from ats_discovery import discover_from_ats, SKIP_TITLE_KEYWORDS, _job_id
from resume_selector import get_resume_type, get_resume_text, RESUME_KEYWORDS


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
    title: str
    due_date: str

class DiscoverRequest(BaseModel):
    queries: list[str] | None = None
    location: str = "United States"
    skip_jsearch: bool = False
    skip_ats: bool = False
    skip_adzuna: bool = False
    freshness_hours: int = 24


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
def list_jobs(
    status: str | None = None,
    min_score: float | None = None,
    limit: int = 25,
    offset: int = 0,
):
    jobs = db.get_jobs(status=status, min_score=min_score, limit=limit, offset=offset)
    total = db.count_jobs(status=status, min_score=min_score)
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
    return job

@app.patch("/api/jobs/{job_id}")
def update_job(job_id: str, body: JobUpdate):
    db.update_job(job_id, **body.model_dump(exclude_none=True))
    return db.get_job(job_id)


# ---------------------------------------------------------------------------
# Application endpoints
# ---------------------------------------------------------------------------

@app.get("/api/applications")
def list_applications(status: str | None = None, limit: int = 100, offset: int = 0):
    return db.get_applications(status=status, limit=limit, offset=offset)

@app.get("/api/applications/stats")
def application_stats():
    return db.get_application_stats()

@app.post("/api/applications")
def create_application(body: ApplicationCreate):
    app_id = db.create_application(**body.model_dump())
    if body.job_id:
        db.update_job(body.job_id, status="applied")
    return {"id": app_id}

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

discovery_status = {"running": False, "last_run": None, "new_jobs": 0}

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
                print(f"[adzuna] Page {page} failed: HTTP {resp.status_code}")
                break
            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            jobs.extend(results)
            import time
            time.sleep(0.3)
        except Exception as e:
            print(f"[adzuna] Page {page} failed: {e}")
            break
    return jobs


def _run_discovery(queries: list[str], location: str, skip_jsearch: bool, skip_ats: bool, freshness_hours: int = 24, skip_adzuna: bool = False):
    discovery_status["running"] = True
    total_new = 0

    date_posted_map = {24: "today", 72: "3days", 168: "week", 720: "month"}
    date_posted = min(date_posted_map.items(), key=lambda x: abs(x[0] - freshness_hours))[1]

    try:
        if not skip_jsearch:
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
            from config import SEARCH_KEYWORDS
            from ats_discovery import _is_us_location
            qs = queries or SEARCH_KEYWORDS
            blacklist = load_json(BLACKLIST_PATH)
            max_days = max(1, int(freshness_hours / 24))

            for query in qs:
                raw = _fetch_adzuna(query, location="us", pages=2, max_days_old=max_days)
                print(f"[adzuna] '{query}': {len(raw)} results")
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
            companies = json.loads(Path("companies.json").read_text())
            import ats_discovery
            from ats_discovery import (
                fetch_greenhouse, fetch_lever, fetch_ashby,
                fetch_amazon, fetch_workday, fetch_pinpoint,
            )
            import time
            ats_discovery.FRESHNESS_DAYS = max(1, freshness_hours / 24)

            for company in companies:
                name = company.get("name", "")
                ats = company.get("ats", "").lower()
                slug = company.get("slug", "")
                if not (name and ats and slug):
                    continue
                if db.is_company_blocked(name):
                    continue

                if ats == "greenhouse":
                    raw_jobs = fetch_greenhouse(slug, name)
                elif ats == "lever":
                    raw_jobs = fetch_lever(slug, name)
                elif ats == "ashby":
                    raw_jobs = fetch_ashby(slug, name)
                elif ats == "amazon":
                    raw_jobs = fetch_amazon(name)
                elif ats == "workday":
                    raw_jobs = fetch_workday(slug, name, company.get("wd_num", 5), company.get("site", ""))
                elif ats == "pinpoint":
                    raw_jobs = fetch_pinpoint(slug, name)
                else:
                    continue

                blacklist = load_json(BLACKLIST_PATH)
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
                    threshold = 25 if ats == "workday" else SCORE_THRESHOLD
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
                        "ats": ats,
                        "score": sc,
                        "description": job.get("job_description", ""),
                        "posted_at": job.get("job_posted_at_datetime_utc", ""),
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        "source": ats,
                        "query": "",
                    }
                    total_new += db.upsert_jobs([entry])
                time.sleep(0.3)
    finally:
        discovery_status["running"] = False
        discovery_status["last_run"] = datetime.now(timezone.utc).isoformat()
        discovery_status["new_jobs"] = total_new


@app.post("/api/discover")
def trigger_discovery(body: DiscoverRequest, background_tasks: BackgroundTasks):
    if discovery_status["running"]:
        raise HTTPException(409, "Discovery already running")
    background_tasks.add_task(
        _run_discovery, body.queries, body.location, body.skip_jsearch, body.skip_ats, body.freshness_hours, body.skip_adzuna,
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
                      recommended_resume=recommended_resume)
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
        "You are a brutally honest technical recruiter evaluating candidate-job fit.\n\n"
        "CANDIDATE PROFILE (memorize this):\n"
        "- MS in Software Engineering (Northeastern, graduating Dec 2025)\n"
        "- 3+ years professional experience at IBM (Associate + Application Developer)\n"
        "- Current: AI Software Engineer at Humanitarians AI (nonprofit)\n"
        "- NO PhD. NO security clearance. NO 5+ years experience.\n"
        "- Strong: Java/Spring Boot, Python, React/TypeScript, Node.js, LLM/RAG/agents\n"
        "- Weak: No C/C++, no robotics, no embedded systems, no ML research publications\n"
        "- Needs visa sponsorship (international student on OPT)\n\n"
        "Respond with ONLY a valid JSON object (no markdown fences):\n"
        "{\n"
        '  "match_pct": <integer 0-100>,\n'
        '  "summary": "<2-3 sentences: key strengths, notable gaps, honest assessment>",\n'
        '  "team": "<team name from JD, or null>",\n'
        '  "project": "<project/product name from JD, or null>",\n'
        '  "key_strengths": ["<strength1>", "<strength2>"],\n'
        '  "gaps": ["<gap1>", "<gap2>"],\n'
        '  "min_years_required": <integer or null>,\n'
        '  "requires_phd": <true if PhD is listed as REQUIRED (not preferred), else false>,\n'
        '  "requires_clearance": <true if security clearance is required, else false>,\n'
        '  "sponsorship_available": <true if they sponsor, false if they explicitly do NOT, null if not mentioned>,\n'
        '  "seniority_level": "<junior|mid|senior|staff|lead|principal|director>",\n'
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
        "- No sponsorship / must be authorized to work: cap at 5\n"
        "- Senior/Staff/Lead with 5+ years required: cap at 40 — candidate has ~2 years\n"
        "- Principal/Director level: cap at 15\n"
        "- Requires C/C++ as PRIMARY language: cap at 30 — candidate doesn't know C++\n"
        "- Salary >$300K usually means senior+ — factor seniority mismatch\n\n"
        "GOOD MATCH SIGNALS (score 75+):\n"
        "- New grad / entry-level / 0-2 years roles\n"
        "- Java + Spring Boot roles\n"
        "- Python + LLM/AI/RAG/agents roles\n"
        "- React + TypeScript frontend roles\n"
        "- Full stack (Node + React + PostgreSQL)\n"
        "- Titles with 'Associate', 'Junior', 'New Grad', 'SDE I', 'SDE 1'\n\n"
        "LOCATION: Do NOT penalize for location — candidate relocates anywhere in US.\n"
        "PREFERRED vs REQUIRED: Only penalize for REQUIRED qualifications.\n"
        "Flag scam_flag=true if JD is generic, company seems fake, or harvests data."
    )

    # Smart truncation: keep first 3500 chars + last 1500 chars (where legal/requirements live)
    if len(jd) > 5000:
        jd_for_llm = jd[:3500] + "\n...[truncated]...\n" + jd[-1500:]
    else:
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
        print(f"[match] Failed to parse LLM response: {raw[:500]}")
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
        "must be a united states citizen", "itar", "security clearance required",
        "active clearance", "top secret", "ts/sci", "secret clearance",
        "must be authorized to work", "will not sponsor", "does not sponsor",
        "no visa sponsorship", "unable to sponsor", "cannot sponsor",
        "authorized to work in the u", "work authorization required",
    ]
    has_citizenship_text = any(p in jd_lower for p in citizenship_patterns)

    if result.get("scam_flag"):
        score = 0
        warnings.append("SCAM FLAG")

    if result.get("requires_clearance") or (is_defense and "clearance" in jd_lower):
        score = min(score, 10)
        warnings.append("CLEARANCE REQUIRED")

    if has_citizenship_text or is_defense:
        if result.get("sponsorship_available") is not True:
            score = min(score, 5)
            if is_defense:
                warnings.append("DEFENSE CO — US PERSON REQUIRED")
            else:
                warnings.append("NO SPONSORSHIP")

    if result.get("sponsorship_available") is False and "SPONSORSHIP" not in " ".join(warnings) and "DEFENSE" not in " ".join(warnings):
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
            score = min(score, 40)
            warnings.append(f"SENIOR ({min_years}+ yrs required)")
        elif min_years and min_years >= 3:
            score = min(score, 55)

    # Experience cap even if seniority wasn't detected
    min_years = result.get("min_years_required")
    if min_years and min_years >= 7:
        score = min(score, 30)
        if "yrs" not in " ".join(warnings).lower():
            warnings.append(f"Requires {min_years}+ years")
    elif min_years and min_years >= 5:
        score = min(score, 40)
        if "yrs" not in " ".join(warnings).lower():
            warnings.append(f"Requires {min_years}+ years")

    result["match_pct"] = score
    if warnings:
        prefix = "[" + " | ".join(warnings) + "] "
        result["summary"] = prefix + result.get("summary", "")

    db.update_job(
        job_id,
        match_pct=result.get("match_pct"),
        match_summary=result.get("summary"),
        team=result.get("team"),
        project=result.get("project"),
        recommended_resume=recommended_resume,
    )
    result["recommended_resume"] = recommended_resume
    result["resume_scores"] = scores
    result["matched_keywords"] = {k: v[:5] for k, v in matched_kw.items()}
    return result


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


def _get_linkedin_id(company: str) -> tuple[str | None, bool]:
    """Returns (linkedin_id, is_verified). Checks overrides first, then companies.json."""
    overrides = _load_linkedin_overrides()
    key = company.lower().strip()
    if key in overrides:
        return overrides[key], True

    try:
        companies = json.loads(Path("companies.json").read_text())
        for c in companies:
            if c.get("name", "").lower() == key and c.get("linkedin_id"):
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

    # Simple "software recruiter" works best — team/title details just narrow results too much
    if linkedin_id and verified:
        query = "software recruiter"
    else:
        query = f"{company} software recruiter"

    url = "https://www.linkedin.com/search/results/people/?"
    url += f"keywords={urllib.parse.quote(query)}"
    url += f"&geoUrn=%5B%22103644278%22%5D"
    url += "&origin=FACETED_SEARCH"
    if linkedin_id and verified:
        url += f"&currentCompany=%5B%22{linkedin_id}%22%5D"

    return {"url": url, "query": query, "company": company, "linkedin_id": linkedin_id, "verified": verified}


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
    overrides[company.lower()] = lid
    _save_linkedin_overrides(overrides)

    # Also update companies.json if the company exists there
    try:
        companies_path = Path("companies.json")
        companies = json.loads(companies_path.read_text())
        updated = False
        for c in companies:
            if c.get("name", "").lower() == company.lower():
                c["linkedin_id"] = lid
                updated = True
                break
        if updated:
            companies_path.write_text(json.dumps(companies, indent=2))
    except Exception as e:
        print(f"[linkedin-id] Failed to update companies.json: {e}")

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


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)
