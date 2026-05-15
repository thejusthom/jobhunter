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

def _run_discovery(queries: list[str], location: str, skip_jsearch: bool, skip_ats: bool, freshness_hours: int = 24):
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
                        "description": job.get("job_description", "")[:2000],
                        "posted_at": job.get("job_posted_at_datetime_utc", ""),
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        "source": "jsearch",
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
                        "description": job.get("job_description", "")[:2000],
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
        _run_discovery, body.queries, body.location, body.skip_jsearch, body.skip_ats, body.freshness_hours,
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
        "You are a strict technical recruiter evaluating candidate-job fit.\n\n"
        "Analyze the resume against the job description REALISTICALLY. Do not inflate scores.\n\n"
        "Respond with ONLY a valid JSON object (no markdown fences):\n"
        "{\n"
        '  "match_pct": <integer 0-100>,\n'
        '  "summary": "<2-3 sentences: key strengths, notable gaps, overall assessment>",\n'
        '  "team": "<team name from JD, or null if not mentioned>",\n'
        '  "project": "<project/product name from JD, or null if not mentioned>",\n'
        '  "key_strengths": ["<strength1>", "<strength2>", "<strength3>"],\n'
        '  "gaps": ["<gap1>", "<gap2>"],\n'
        '  "min_years_required": <minimum years of experience required by JD, or null if not specified>,\n'
        '  "sponsorship_available": <true if JD says they sponsor visas, false if they say they do NOT sponsor, null if not mentioned>,\n'
        '  "scam_flag": <true if this looks like a fake/scam posting, else false>\n'
        "}\n\n"
        "SCORING GUIDE (be strict, do NOT default to 70-75):\n"
        "- 85-100: Near-perfect match — meets all required skills AND experience level\n"
        "- 70-84: Strong match — meets most required skills, experience level is close\n"
        "- 50-69: Decent match — has relevant skills but notable gaps in experience or stack\n"
        "- 30-49: Weak match — some transferable skills but missing key requirements\n"
        "- 10-29: Poor match — significant skill AND experience mismatch\n"
        "- 0-9: No match, scam, or deal-breaker (no sponsorship, clearance required)\n\n"
        "CRITICAL RULES:\n"
        "- EXPERIENCE: If JD requires X+ years and candidate has significantly less, "
        "this is a MAJOR penalty. 5+ years required with <2 years experience = score under 40.\n"
        "- SPONSORSHIP: If JD explicitly says 'no visa sponsorship', 'will not sponsor', "
        "'must be authorized to work', score 0-10 and mention it prominently in summary.\n"
        "- SENIORITY: Senior/Staff/Lead roles requiring 5+ years should score LOW for new grads.\n"
        "- REQUIRED vs PREFERRED: Only penalize for REQUIRED qualifications, not preferred/nice-to-have.\n"
        "- LOCATION: Do NOT penalize for location — candidate will relocate anywhere in US.\n"
        "- TRANSFERABLE SKILLS: Give modest credit (not full credit) for related skills.\n"
        "- DO NOT cluster scores around 70-75. Use the full 0-100 range based on actual fit.\n"
        "- Flag scam_flag=true if JD is generic, company seems fake, or posting harvests data."
    )

    user_prompt = (
        f"RESUME:\n{resume_text[:3000]}\n\n"
        f"JOB TITLE: {title}\n"
        f"COMPANY: {company}\n\n"
        f"JOB DESCRIPTION:\n{jd[:3000]}"
    )

    raw = llm.call(system_prompt, user_prompt)
    if not raw:
        raise HTTPException(502, "LLM call returned empty response")

    result = llm.parse_json(raw)
    if not result:
        print(f"[match] Failed to parse LLM response: {raw[:500]}")
        raise HTTPException(502, f"Could not parse LLM response")

    if result.get("scam_flag"):
        result["match_pct"] = 0
        result["summary"] = f"[SCAM FLAG] {result.get('summary', 'Suspicious posting')}"

    if result.get("sponsorship_available") is False:
        result["match_pct"] = min(result.get("match_pct", 0), 5)
        result["summary"] = f"[NO SPONSORSHIP] {result.get('summary', 'Does not sponsor visas')}"

    # Prepend experience warning to summary if relevant
    min_years = result.get("min_years_required")
    if min_years and min_years >= 5:
        summary = result.get("summary", "")
        if "experience" not in summary.lower() and "years" not in summary.lower():
            result["summary"] = f"[Requires {min_years}+ years exp] {summary}"

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

@app.get("/api/jobs/{job_id}/linkedin-search")
def linkedin_search(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    company = job.get("company", "")
    team = job.get("team") or ""

    if team:
        query = f"{company} {team} recruiter"
    else:
        query = f"{company} recruiter"

    linkedin_id = None
    try:
        companies = json.loads(Path("companies.json").read_text())
        for c in companies:
            if c.get("name", "").lower() == company.lower() and c.get("linkedin_id"):
                linkedin_id = c["linkedin_id"]
                break
    except Exception:
        pass

    url = "https://www.linkedin.com/search/results/people/?"
    url += f"keywords={urllib.parse.quote(query)}"
    url += f"&geoUrn=%5B%22103644278%22%5D"
    url += "&origin=FACETED_SEARCH"
    if linkedin_id:
        url += f"&currentCompany=%5B%22{linkedin_id}%22%5D"

    return {"url": url, "query": query}


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
