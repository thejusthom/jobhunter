"""
JobHunter Discovery Module
Fetches jobs from JSearch API, scores them, and queues for manual review.
"""

import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"
JSEARCH_KEY = os.environ.get("JSEARCH_API_KEY", "")

SCORE_THRESHOLD = 70
QUEUE_PATH = Path("queue.json")
LOG_PATH = Path("applied_log.json")
BLACKLIST_PATH = Path("blacklist.json")

# Job boards to reject outright — spam/low-quality aggregators
BLACKLISTED_PUBLISHERS = {
    "bebee.com", "jooble.org", "jobrapido.com",
    "jobomas.com", "jobtome.com", "trovit.com", "mitula.com",
    "neuvoo.com", "careerjet.com", "jobsora.com",
}

# Quality publishers — these are fine to apply through
ALLOWED_PUBLISHERS = {
    "indeed.com", "ziprecruiter.com", "glassdoor.com",
    "dice.com", "wellfound.com", "angel.co",
    "builtinboston.com", "builtinnyc.com", "builtinaustin.com",
    "builtinchicago.com", "builtin.com",
    "talent.com", "simplyhired.com", "monster.com",
    "cybercoders.com", "hired.com",
    # Direct ATS — if JSearch ever surfaces these, always prefer them
    "lever.co", "ashbyhq.com", "greenhouse.io",
    "workable.com", "smartrecruiters.com", "myworkdayjobs.com",
    "icims.com", "taleo.net", "jobvite.com",
}


def load_json(path: Path) -> list | dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return [] if "log" in path.name or "queue" in path.name else {}


def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def job_id(job: dict) -> str:
    key = f"{job.get('employer_name','')}{job.get('job_title','')}{job.get('job_apply_link','')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


_jsearch_rate_limited = False  # module-level flag to skip JSearch after 429

def fetch_jobs(query: str, location: str = "United States", pages: int = 3, date_posted: str = "today") -> list:
    global _jsearch_rate_limited
    if _jsearch_rate_limited:
        return []

    headers = {
        "X-RapidAPI-Key": JSEARCH_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    jobs = []
    for page in range(1, pages + 1):
        params = {
            "query": query,
            "location": location,
            "page": str(page),
            "num_pages": "1",
            "employment_types": "FULLTIME",
            "date_posted": date_posted,
        }
        try:
            resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=20)
            if resp.status_code == 429:
                _log(f"[discovery] JSearch rate-limited (429) — skipping remaining queries")
                _jsearch_rate_limited = True
                return jobs
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("jobs", [])
            jobs.extend(data)
            time.sleep(0.5)
        except Exception as e:
            _log(f"[discovery] Page {page} failed: {e}")
            # If it's a 429 wrapped in an exception, bail
            if "429" in str(e):
                _jsearch_rate_limited = True
                return jobs
    return jobs


def _best_apply_link(job: dict) -> str | None:
    """
    Pick the best apply link from apply_options.
    Priority: known ATS > any non-blacklisted link (including direct company pages).
    Only rejects explicitly blacklisted spam aggregators.
    """
    options = job.get("apply_options") or []
    primary = job.get("job_apply_link", "")

    all_links = [opt.get("apply_link", "") for opt in options if opt.get("apply_link")]
    if primary and primary not in all_links:
        all_links.insert(0, primary)

    # Strip spam aggregators
    clean = [l for l in all_links if l and not any(bad in l for bad in BLACKLISTED_PUBLISHERS)]
    if not clean:
        return None

    # Prefer direct ATS platforms first
    for link in clean:
        for ats in ALLOWED_PUBLISHERS:
            if ats in link:
                return link

    # Accept anything else — direct company career pages are fine
    return clean[0]


def _is_fresh(job: dict, max_age_hours: int = 24) -> bool:
    """
    True if the job was actually posted within max_age_hours.
    """
    posted_str = job.get("job_posted_at_datetime_utc")
    if not posted_str:
        return True  # no timestamp — can't reject, let it through
    try:
        posted = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - posted) <= timedelta(hours=max_age_hours)
    except (ValueError, TypeError):
        return True


def is_blacklisted(job: dict, blacklist: dict) -> bool:
    company = job.get("employer_name", "").lower()
    companies = [c.lower() for c in blacklist.get("companies", [])]
    keywords = [k.lower() for k in blacklist.get("keywords", [])]
    title = job.get("job_title", "").lower()
    description = job.get("job_description", "").lower()

    if company in companies:
        return True
    return any(kw in title or kw in description for kw in keywords)


def score_job(job: dict) -> float:
    """
    Resume-aware scorer for Thejus Thomson.
    Tiered: primary stack (0–0.65) + secondary (0–0.20) + title match (0.10) + easy-apply (0.05).
    Returns 0 to 100.
    """
    title = job.get("job_title", "").lower()
    description = job.get("job_description", "").lower()
    combined = title + " " + description

    hard_negatives = [
        "clearance required", "security clearance", "c++ only",
        "10+ years", "15+ years", "no sponsorship",
        "us citizen only", "must be a us citizen", "green card only",
        "principal engineer", "staff engineer", "engineering manager",
        "director of engineering", "vp of", "vice president",
        "embedded systems", "firmware", "fpga", "vhdl", "verilog",
        "c# only", ".net only", "cobol", "mainframe",
    ]
    if any(neg in combined for neg in hard_negatives):
        return 0.0

    # Core stack — Java/Spring, Python, React/TS, Node, AI/LLM
    primary = [
        "java", "spring boot", "spring mvc", "hibernate",
        "python", "fastapi", "django", "flask",
        "react", "next.js", "typescript", "redux",
        "node.js", "nodejs", "express",
        "llm", "langchain", "rag", "generative ai", "gen ai",
        "fine-tuning", "openai", "claude", "agentic",
        "apache camel", "kafka", "microservices",
    ]
    # Solid supporting skills
    secondary = [
        "postgresql", "mongodb", "sqlite", "redis",
        "aws", "gcp", "docker", "kubernetes",
        "rest api", "graphql", "oauth", "jwt",
        "ci/cd", "github actions", "jenkins", "terraform",
        "software engineer", "backend engineer", "full stack", "fullstack",
        "tailwind", "next", "angular",
    ]
    # Role title alignment
    target_titles = [
        "software engineer", "backend engineer", "full stack", "fullstack",
        "ai engineer", "ml engineer", "machine learning engineer",
        "java developer", "java engineer", "python developer", "python engineer",
        "react developer", "node developer", "new grad", "associate engineer",
        "junior engineer", "junior developer", "sde i", "sde 1",
    ]

    primary_hits = sum(1 for kw in primary if kw in combined)
    secondary_hits = sum(1 for kw in secondary if kw in combined)
    title_match = any(t in title for t in target_titles)

    score = min(primary_hits / 7, 0.65)
    score += min(secondary_hits / 8, 0.20)
    if title_match:
        score += 0.10
    if job.get("job_apply_is_direct"):
        score += 0.05

    return round(min(score, 1.0) * 100)


def already_applied(jid: str, log: list) -> bool:
    return any(entry.get("id") == jid for entry in log)


def discover(queries: list[str], location: str = "United States") -> list:
    blacklist = load_json(BLACKLIST_PATH)
    applied_log = load_json(LOG_PATH)
    queue = load_json(QUEUE_PATH)
    existing_ids = {entry.get("id") for entry in queue}

    new_entries = []

    for query in queries:
        _log(f"[discovery] Searching: '{query}'")
        jobs = fetch_jobs(query, location=location)
        _log(f"[discovery] Found {len(jobs)} raw results")

        for job in jobs:
            jid = job_id(job)

            if jid in existing_ids:
                continue
            if already_applied(jid, applied_log):
                continue

            if not _is_fresh(job):
                _log(f"[discovery] Stale/reposted: {job.get('employer_name')} — {job.get('job_title')}")
                continue

            link = _best_apply_link(job)
            if link is None:
                _log(f"[discovery] No quality link: {job.get('employer_name')} — {job.get('job_title')}")
                continue

            if is_blacklisted(job, blacklist):
                _log(f"[discovery] Blacklisted: {job.get('employer_name')} — {job.get('job_title')}")
                continue

            score = score_job(job)
            if score < SCORE_THRESHOLD:
                _log(f"[discovery] Skipped ({score}): {job.get('employer_name')} — {job.get('job_title')}")
                continue

            # Detect which publisher the link came from
            ats = next(
                (d.split(".")[0] for d in ALLOWED_PUBLISHERS if d in link),
                "other"
            )

            entry = {
                "id": jid,
                "score": score,
                "title": job.get("job_title"),
                "company": job.get("employer_name"),
                "location": (job.get("job_city") or "") + ", " + (job.get("job_country") or ""),
                "apply_link": link,
                "ats": ats,
                "description": job.get("job_description", ""),
                "posted_at": job.get("job_posted_at_datetime_utc", ""),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "source": "jsearch",
                "query": query,
                "status": "pending",
            }

            new_entries.append(entry)
            existing_ids.add(jid)
            _log(f"[discovery] Queued ({score}) [{ats}]: {entry['company']} — {entry['title']}")

    queue.extend(new_entries)
    save_json(QUEUE_PATH, queue)
    _log(f"[discovery] Done. {len(new_entries)} new jobs queued.")
    return new_entries


if __name__ == "__main__":
    discover(
        queries=[
            "software engineer Java Spring Boot",
            "full stack engineer Python React",
            "backend engineer Node.js PostgreSQL",
            "AI engineer LLM Python",
        ],
        location="United States",
    )
