"""SQLite database layer for JobHunter."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = Path("jobhunter.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT DEFAULT '',
            apply_link TEXT DEFAULT '',
            ats TEXT DEFAULT '',
            score REAL DEFAULT 0.0,
            match_pct REAL DEFAULT NULL,
            match_summary TEXT DEFAULT NULL,
            description TEXT DEFAULT '',
            posted_at TEXT DEFAULT '',
            discovered_at TEXT DEFAULT '',
            source TEXT DEFAULT '',
            query TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            acted_at TEXT DEFAULT NULL,
            team TEXT DEFAULT NULL,
            project TEXT DEFAULT NULL,
            recommended_resume TEXT DEFAULT NULL,
            resume_scores TEXT DEFAULT NULL,
            matched_keywords TEXT DEFAULT NULL,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT DEFAULT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT DEFAULT '',
            apply_link TEXT DEFAULT '',
            status TEXT DEFAULT 'applied',
            applied_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source TEXT DEFAULT 'jobhunter',
            salary_min INTEGER DEFAULT NULL,
            salary_max INTEGER DEFAULT NULL,
            notes TEXT DEFAULT '',
            resume_used TEXT DEFAULT '',
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE TABLE IF NOT EXISTS recruiters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            email TEXT DEFAULT '',
            application_id INTEGER DEFAULT NULL,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER DEFAULT NULL,
            recruiter_id INTEGER DEFAULT NULL,
            job_id TEXT DEFAULT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id),
            FOREIGN KEY (recruiter_id) REFERENCES recruiters(id)
        );

        CREATE TABLE IF NOT EXISTS blocked_companies (
            company TEXT PRIMARY KEY,
            reason TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS collected_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            domain TEXT DEFAULT '',
            email TEXT NOT NULL,
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            position TEXT DEFAULT '',
            department TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            confidence INTEGER DEFAULT 0,
            job_id TEXT DEFAULT NULL,
            job_title TEXT DEFAULT '',
            collected_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
        CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_date);
        CREATE INDEX IF NOT EXISTS idx_reminders_completed ON reminders(completed);
        CREATE INDEX IF NOT EXISTS idx_collected_emails_company ON collected_emails(company);
        """)

        # Add outreach columns if missing
        cols = {r[1] for r in db.execute("PRAGMA table_info(jobs)").fetchall()}
        if "outreach_full" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN outreach_full TEXT DEFAULT NULL")
        if "outreach_short" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN outreach_short TEXT DEFAULT NULL")
        if "outreach_short_hm" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN outreach_short_hm TEXT DEFAULT NULL")
        if "resume_scores" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN resume_scores TEXT DEFAULT NULL")
        if "matched_keywords" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN matched_keywords TEXT DEFAULT NULL")
        if "salary_min" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN salary_min INTEGER DEFAULT NULL")
        if "salary_max" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN salary_max INTEGER DEFAULT NULL")

        # Add job_id column to reminders if missing
        reminder_cols = {r[1] for r in db.execute("PRAGMA table_info(reminders)").fetchall()}
        if "job_id" not in reminder_cols:
            db.execute("ALTER TABLE reminders ADD COLUMN job_id TEXT DEFAULT NULL")

        # Add contact_linkedin column to jobs if missing
        if "contact_linkedin" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN contact_linkedin TEXT DEFAULT NULL")

        # Add email_used column to applications if missing
        app_cols = {r[1] for r in db.execute("PRAGMA table_info(applications)").fetchall()}
        if "email_used" not in app_cols:
            db.execute("ALTER TABLE applications ADD COLUMN email_used TEXT DEFAULT 'thomsonthejus@gmail.com'")

        # Scheduled discovery table
        db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_discoveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cron_hours TEXT NOT NULL DEFAULT '9',
                sources TEXT NOT NULL DEFAULT 'simplify',
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run TEXT DEFAULT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # H-1B sponsor companies (imported from 80-Days-to-Stay dataset)
        db.execute("""
            CREATE TABLE IF NOT EXISTS h1b_sponsors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                name_norm TEXT NOT NULL,
                industry TEXT DEFAULT '',
                website TEXT DEFAULT '',
                city TEXT DEFAULT '',
                state TEXT DEFAULT '',
                executives TEXT DEFAULT '',
                total_funding REAL DEFAULT NULL,
                latest_funding_stage TEXT DEFAULT '',
                latest_funding_date TEXT DEFAULT '',
                total_approvals REAL DEFAULT NULL,
                total_denials REAL DEFAULT NULL,
                approval_rate REAL DEFAULT NULL,
                median_salary REAL DEFAULT NULL,
                top_titles TEXT DEFAULT '',
                has_h1b INTEGER DEFAULT 0
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_sponsors_norm ON h1b_sponsors(name_norm)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sponsors_h1b ON h1b_sponsors(has_h1b, total_approvals DESC)")


def migrate_json_to_db():
    """One-time migration from queue.json and application_log.json to SQLite."""
    queue_path = Path("queue.json")
    log_path = Path("application_log.json")

    with get_db() as db:
        existing = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if existing > 0:
            return

        if queue_path.exists():
            jobs = json.loads(queue_path.read_text())
            for j in jobs:
                db.execute("""
                    INSERT OR IGNORE INTO jobs (id, title, company, location, apply_link, ats, score,
                        description, posted_at, discovered_at, source, query, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    j.get("id"), j.get("title", ""), j.get("company", ""),
                    j.get("location", ""), j.get("apply_link", ""), j.get("ats", ""),
                    j.get("score", 0), j.get("description", ""),
                    j.get("posted_at", ""), j.get("discovered_at", ""),
                    j.get("source", ""), j.get("query", ""), j.get("status", "pending"),
                ))

        if log_path.exists():
            logs = json.loads(log_path.read_text())
            now = datetime.now(timezone.utc).isoformat()
            for entry in logs:
                db.execute("""
                    INSERT INTO applications (job_id, title, company, apply_link, status, applied_at, updated_at, source)
                    VALUES (?, ?, ?, ?, 'applied', ?, ?, 'jobhunter')
                """, (
                    entry.get("id"), entry.get("title", ""), entry.get("company", ""),
                    entry.get("apply_link", ""), entry.get("opened_at", now), now,
                ))


# --- Job queries ---

SORT_OPTIONS = {
    "posted_newest": "posted_at DESC NULLS LAST, discovered_at DESC",
    "posted_oldest": "posted_at ASC NULLS LAST, discovered_at ASC",
    "newest": "discovered_at DESC",
    "oldest": "discovered_at ASC",
    "match_desc": "match_pct DESC NULLS LAST",
    "match_asc": "match_pct ASC NULLS LAST",
    "company_asc": "company COLLATE NOCASE ASC",
    "company_desc": "company COLLATE NOCASE DESC",
    "salary_desc": "salary_max DESC NULLS LAST",
    "title_asc": "title COLLATE NOCASE ASC",
}


def get_jobs(status=None, min_score=None, limit=100, offset=0, search=None, sort=None):
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if min_score is not None:
        clauses.append("match_pct >= ?")
        params.append(min_score)
    if search:
        clauses.append("(title LIKE ? OR company LIKE ?)")
        like = f"%{search}%"
        params.extend([like] * 2)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    order = SORT_OPTIONS.get(sort, "acted_at DESC NULLS LAST, discovered_at DESC, match_pct DESC")
    params.extend([limit, offset])
    with get_db() as db:
        rows = db.execute(f"SELECT * FROM jobs {where} ORDER BY {order} LIMIT ? OFFSET ?", params).fetchall()
        return [dict(r) for r in rows]


def get_job(job_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def update_job(job_id, **fields):
    allowed = {"status", "notes", "match_pct", "match_summary", "team", "project", "recommended_resume", "resume_scores", "matched_keywords", "outreach_full", "outreach_short", "outreach_short_hm", "description", "salary_min", "salary_max", "title", "company", "location", "ats", "apply_link", "contact_linkedin"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["acted_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [job_id]
    with get_db() as db:
        db.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", params)


def upsert_jobs(entries: list):
    inserted = 0
    with get_db() as db:
        for j in entries:
            title = j.get("title", "")
            company = j.get("company", "")
            # Dedup: skip if same title+company already exists (even from a different source)
            existing = db.execute(
                "SELECT id, status FROM jobs WHERE LOWER(title) = LOWER(?) AND LOWER(company) = LOWER(?) LIMIT 1",
                (title, company),
            ).fetchone()
            if existing:
                continue
            cursor = db.execute("""
                INSERT OR IGNORE INTO jobs (id, title, company, location, apply_link, ats, score,
                    description, posted_at, discovered_at, source, query, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                j.get("id"), title, company,
                j.get("location", ""), j.get("apply_link", ""), j.get("ats", ""),
                j.get("score", 0), j.get("description", ""),
                j.get("posted_at", ""), j.get("discovered_at", ""),
                j.get("source", ""), j.get("query", ""),
            ))
            inserted += cursor.rowcount
    return inserted


def count_jobs(status=None, min_score=None, search=None):
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if min_score is not None:
        clauses.append("match_pct >= ?")
        params.append(min_score)
    if search:
        clauses.append("(title LIKE ? OR company LIKE ?)")
        like = f"%{search}%"
        params.extend([like] * 2)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with get_db() as db:
        row = db.execute(f"SELECT COUNT(*) as count FROM jobs {where}", params).fetchone()
        return row["count"]


# ---------------------------------------------------------------------------
# Key-value store (persists discovery status, etc. across restarts)
# ---------------------------------------------------------------------------

def kv_get(key: str, default: str = None) -> str | None:
    with get_db() as db:
        row = db.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

def kv_set(key: str, value: str):
    with get_db() as db:
        db.execute(
            "INSERT INTO kv_store (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )


# --- Scheduled Discoveries ---

def get_scheduled_discoveries():
    with get_db() as db:
        rows = db.execute("SELECT * FROM scheduled_discoveries ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def create_scheduled_discovery(name: str, cron_hours: str, sources: str):
    with get_db() as db:
        db.execute(
            "INSERT INTO scheduled_discoveries (name, cron_hours, sources) VALUES (?, ?, ?)",
            (name, cron_hours, sources),
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_scheduled_discovery(sd_id: int, **kwargs):
    allowed = {"name", "cron_hours", "sources", "enabled", "last_run"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [sd_id]
    with get_db() as db:
        db.execute(f"UPDATE scheduled_discoveries SET {sets} WHERE id = ?", vals)


def delete_scheduled_discovery(sd_id: int):
    with get_db() as db:
        db.execute("DELETE FROM scheduled_discoveries WHERE id = ?", (sd_id,))


def get_job_stats():
    with get_db() as db:
        rows = db.execute("SELECT status, COUNT(*) as count FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["count"] for r in rows}


def get_evaluated_jobs(limit=20):
    with get_db() as db:
        rows = db.execute(
            "SELECT id, title, company, match_pct, match_summary, team, project, recommended_resume, acted_at "
            "FROM jobs WHERE match_pct IS NOT NULL ORDER BY acted_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# --- Application queries ---

def get_applications(status=None, search=None, limit=100, offset=0):
    clauses, params = [], []
    if status:
        clauses.append("a.status = ?")
        params.append(status)
    if search:
        clauses.append("(a.company LIKE ? OR a.title LIKE ?)")
        like = f"%{search}%"
        params.extend([like] * 2)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    with get_db() as db:
        rows = db.execute(f"""
            SELECT a.*, j.contact_linkedin as job_contact_linkedin
            FROM applications a
            LEFT JOIN jobs j ON a.job_id = j.id
            {where} ORDER BY a.updated_at DESC LIMIT ? OFFSET ?
        """, params).fetchall()
        return [dict(r) for r in rows]


def create_application(**fields):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO applications (job_id, title, company, location, apply_link, status, applied_at, updated_at, source, salary_min, salary_max, notes, resume_used, email_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fields.get("job_id"), fields.get("title", ""), fields.get("company", ""),
            fields.get("location", ""), fields.get("apply_link", ""),
            fields.get("status", "applied"), fields.get("applied_at") or now, now,
            fields.get("source", "manual"), fields.get("salary_min"),
            fields.get("salary_max"), fields.get("notes", ""), fields.get("resume_used", ""),
            fields.get("email_used", "thomsonthejus@gmail.com"),
        ))
        return cursor.lastrowid


def update_application(app_id, **fields):
    allowed = {"status", "notes", "salary_min", "salary_max", "resume_used", "email_used"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [app_id]
    with get_db() as db:
        db.execute(f"UPDATE applications SET {set_clause} WHERE id = ?", params)


def get_application_stats():
    with get_db() as db:
        rows = db.execute("SELECT status, COUNT(*) as count FROM applications GROUP BY status").fetchall()
        stats = {r["status"]: r["count"] for r in rows}
        weekly = db.execute("SELECT COUNT(*) as count FROM applications WHERE applied_at >= date('now', '-7 days')").fetchone()
        stats["this_week"] = weekly["count"]
        return stats


# --- Recruiter queries ---

def get_recruiters(application_id=None):
    if application_id:
        with get_db() as db:
            rows = db.execute("SELECT * FROM recruiters WHERE application_id = ? ORDER BY created_at DESC", (application_id,)).fetchall()
            return [dict(r) for r in rows]
    with get_db() as db:
        rows = db.execute("SELECT * FROM recruiters ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def create_recruiter(**fields):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO recruiters (name, company, linkedin_url, email, application_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            fields.get("name", ""), fields.get("company", ""),
            fields.get("linkedin_url", ""), fields.get("email", ""),
            fields.get("application_id"), fields.get("notes", ""), now,
        ))
        return cursor.lastrowid


# --- Reminder queries ---

def get_reminders(include_completed=False):
    clause = "" if include_completed else "WHERE r.completed = 0"
    with get_db() as db:
        rows = db.execute(f"""
            SELECT r.*, a.title as app_title, a.company as app_company,
                   j.title as job_title, j.company as job_company, j.apply_link as job_link, j.contact_linkedin as job_contact_linkedin
            FROM reminders r
            LEFT JOIN applications a ON r.application_id = a.id
            LEFT JOIN jobs j ON r.job_id = j.id
            {clause}
            ORDER BY r.due_date ASC
        """).fetchall()
        return [dict(r) for r in rows]


def get_due_reminders():
    with get_db() as db:
        rows = db.execute("""
            SELECT r.*, a.title as app_title, a.company as app_company,
                   j.title as job_title, j.company as job_company, j.apply_link as job_link, j.contact_linkedin as job_contact_linkedin
            FROM reminders r
            LEFT JOIN applications a ON r.application_id = a.id
            LEFT JOIN jobs j ON r.job_id = j.id
            WHERE r.completed = 0 AND r.due_date <= datetime('now', 'localtime')
            ORDER BY r.due_date ASC
        """).fetchall()
        return [dict(r) for r in rows]


def create_reminder(**fields):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO reminders (application_id, recruiter_id, job_id, title, due_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            fields.get("application_id"), fields.get("recruiter_id"), fields.get("job_id"),
            fields.get("title", ""), fields.get("due_date", ""), now,
        ))
        return cursor.lastrowid


def complete_reminder(reminder_id):
    with get_db() as db:
        db.execute("UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,))


def update_reminder(reminder_id, **fields):
    allowed = {"title", "due_date"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [reminder_id]
    with get_db() as db:
        db.execute(f"UPDATE reminders SET {set_clause} WHERE id = ?", params)


def delete_reminder(reminder_id):
    with get_db() as db:
        db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))


def delete_non_us_jobs():
    from ats_discovery import _is_us_location
    with get_db() as conn:
        rows = conn.execute("SELECT id, location FROM jobs").fetchall()
        to_delete = []
        for r in rows:
            if not _is_us_location(r["location"]):
                to_delete.append(r["id"])
        if to_delete:
            conn.execute(f"UPDATE applications SET job_id = NULL WHERE job_id IN ({','.join('?' * len(to_delete))})", to_delete)
            conn.execute(f"DELETE FROM jobs WHERE id IN ({','.join('?' * len(to_delete))})", to_delete)
        return len(to_delete)


def get_analytics():
    with get_db() as db:
        apps_by_company = db.execute(
            "SELECT company, COUNT(*) as count FROM applications GROUP BY company ORDER BY count DESC"
        ).fetchall()

        apps_by_day = db.execute(
            "SELECT DATE(applied_at) as day, COUNT(*) as count FROM applications GROUP BY DATE(applied_at) ORDER BY day"
        ).fetchall()

        apps_by_status = db.execute(
            "SELECT status, COUNT(*) as count FROM applications GROUP BY status ORDER BY count DESC"
        ).fetchall()

        apps_by_source = db.execute(
            "SELECT source, COUNT(*) as count FROM applications GROUP BY source ORDER BY count DESC"
        ).fetchall()

        apps_by_resume = db.execute(
            "SELECT COALESCE(NULLIF(resume_used, ''), 'none') as resume, COUNT(*) as count FROM applications GROUP BY resume ORDER BY count DESC"
        ).fetchall()

        jobs_by_ats = db.execute(
            "SELECT ats, COUNT(*) as count FROM jobs GROUP BY ats ORDER BY count DESC"
        ).fetchall()

        jobs_by_company = db.execute(
            "SELECT company, COUNT(*) as count FROM jobs GROUP BY company ORDER BY count DESC LIMIT 20"
        ).fetchall()

        match_pct_dist = db.execute(
            "SELECT CASE "
            "WHEN match_pct >= 80 THEN '80-100' "
            "WHEN match_pct >= 60 THEN '60-79' "
            "WHEN match_pct >= 40 THEN '40-59' "
            "WHEN match_pct >= 20 THEN '20-39' "
            "ELSE '0-19' END as bracket, COUNT(*) as count "
            "FROM jobs WHERE match_pct IS NOT NULL GROUP BY bracket ORDER BY bracket"
        ).fetchall()

        total_apps = db.execute("SELECT COUNT(*) as count FROM applications").fetchone()["count"]
        total_jobs = db.execute("SELECT COUNT(*) as count FROM jobs").fetchone()["count"]
        total_recruiters = db.execute("SELECT COUNT(*) as count FROM recruiters").fetchone()["count"]
        total_evals = db.execute("SELECT COUNT(*) as count FROM jobs WHERE match_pct IS NOT NULL").fetchone()["count"]
        avg_match = db.execute("SELECT AVG(match_pct) as avg FROM jobs WHERE match_pct IS NOT NULL").fetchone()["avg"]
        blocked = db.execute("SELECT COUNT(*) as count FROM blocked_companies").fetchone()["count"]

        apps_this_week = db.execute(
            "SELECT COUNT(*) as count FROM applications WHERE applied_at >= date('now', '-7 days')"
        ).fetchone()["count"]
        apps_this_month = db.execute(
            "SELECT COUNT(*) as count FROM applications WHERE applied_at >= date('now', '-30 days')"
        ).fetchone()["count"]

        recruiters_by_company = db.execute(
            "SELECT company, COUNT(*) as count FROM recruiters WHERE company != '' GROUP BY company ORDER BY count DESC LIMIT 15"
        ).fetchall()

    return {
        "totals": {
            "applications": total_apps,
            "jobs_discovered": total_jobs,
            "recruiters_contacted": total_recruiters,
            "evaluations": total_evals,
            "avg_match_pct": round(avg_match, 1) if avg_match else 0,
            "blocked_companies": blocked,
            "apps_this_week": apps_this_week,
            "apps_this_month": apps_this_month,
        },
        "apps_by_company": [dict(r) for r in apps_by_company],
        "apps_by_day": [dict(r) for r in apps_by_day],
        "apps_by_status": [dict(r) for r in apps_by_status],
        "apps_by_source": [dict(r) for r in apps_by_source],
        "apps_by_resume": [dict(r) for r in apps_by_resume],
        "jobs_by_ats": [dict(r) for r in jobs_by_ats],
        "jobs_by_company": [dict(r) for r in jobs_by_company],
        "match_pct_distribution": [dict(r) for r in match_pct_dist],
        "recruiters_by_company": [dict(r) for r in recruiters_by_company],
    }


def clear_pending_jobs():
    with get_db() as db:
        cursor = db.execute("UPDATE jobs SET status = 'skipped' WHERE status = 'pending'")
        return cursor.rowcount


# --- Blocked companies ---

def block_company(company: str, reason: str = "no sponsorship"):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO blocked_companies (company, reason, created_at) VALUES (?, ?, ?)",
            (company, reason, now),
        )
        db.execute(
            "UPDATE jobs SET status = 'skipped', notes = ? WHERE LOWER(company) = LOWER(?) AND status = 'pending'",
            (f"Blocked: {reason}", company),
        )


def unblock_company(company: str):
    with get_db() as db:
        db.execute("DELETE FROM blocked_companies WHERE LOWER(company) = LOWER(?)", (company,))


def get_blocked_companies():
    with get_db() as db:
        rows = db.execute("SELECT * FROM blocked_companies ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def is_company_blocked(company: str) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT 1 FROM blocked_companies WHERE LOWER(company) = LOWER(?)", (company,)
        ).fetchone()
        return row is not None


# --- Fix Workday URLs ---

def fix_workday_urls(companies: list):
    slug_to_info = {}
    for c in companies:
        if c.get("ats") == "workday":
            slug_to_info[c["name"].lower()] = {
                "slug": c["slug"],
                "wd_num": c.get("wd_num", 5),
                "site": c.get("site", ""),
            }

    with get_db() as db:
        rows = db.execute("SELECT id, company, apply_link FROM jobs WHERE ats = 'workday'").fetchall()
        fixed = 0
        for r in rows:
            link = r["apply_link"] or ""
            company_lower = (r["company"] or "").lower()
            info = slug_to_info.get(company_lower)
            if not info:
                continue
            base = f"https://{info['slug']}.wd{info['wd_num']}.myworkdayjobs.com"
            expected_prefix = f"{base}/en-US/{info['site']}"
            if link.startswith(expected_prefix):
                continue
            if link.startswith(base):
                path = link[len(base):]
                new_url = f"{expected_prefix}{path}"
                db.execute("UPDATE jobs SET apply_link = ? WHERE id = ?", (new_url, r["id"]))
                fixed += 1
        return fixed


# --- Collected emails ---

def save_collected_emails(company: str, domain: str, people: list, job_id: str = None, job_title: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with get_db() as db:
        for p in people:
            email = p.get("email", "")
            if not email:
                continue
            # Skip if already collected
            existing = db.execute(
                "SELECT 1 FROM collected_emails WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                continue
            db.execute("""
                INSERT INTO collected_emails (company, domain, email, first_name, last_name,
                    position, department, linkedin_url, confidence, job_id, job_title, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company, domain, email,
                p.get("first_name", ""), p.get("last_name", ""),
                p.get("position", ""), p.get("department", ""),
                p.get("linkedin", ""), p.get("confidence", 0),
                job_id, job_title, now,
            ))
            inserted += 1
    return inserted


def get_collected_emails(company: str = None, limit: int = 200, offset: int = 0):
    clauses, params = [], []
    if company:
        clauses.append("LOWER(company) LIKE ?")
        params.append(f"%{company.lower()}%")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    with get_db() as db:
        rows = db.execute(
            f"SELECT * FROM collected_emails {where} ORDER BY collected_at DESC LIMIT ? OFFSET ?",
            params
        ).fetchall()
        total = db.execute(
            f"SELECT COUNT(*) as count FROM collected_emails {where.replace('LIMIT ? OFFSET ?', '') if where else ''}",
            params[:-2] if clauses else []
        ).fetchone()["count"]
        return {"emails": [dict(r) for r in rows], "total": total}


# --- H-1B sponsors ---

import re as _re

_CORP_SUFFIXES = _re.compile(
    r"\b(INCORPORATED|CORPORATION|COMPANY|HOLDINGS?|GROUP|INC|CORP|LLC|LLP|LTD|PLC|CO|LP|USA|US)\b\.?",
)


def normalize_sponsor_name(name: str) -> str:
    """Normalize a company name for fuzzy matching: uppercase, strip punctuation and corp suffixes."""
    n = (name or "").upper()
    n = _re.sub(r"[^A-Z0-9 ]", " ", n)
    # Strip trailing corporate suffixes repeatedly (e.g. "FOO HOLDINGS INC")
    prev = None
    while prev != n:
        prev = n
        n = _CORP_SUFFIXES.sub(" ", n)
    return _re.sub(r"\s+", " ", n).strip()


def import_sponsors(rows: list[dict]) -> int:
    """Bulk import sponsor rows (replaces existing data)."""
    import ast

    def _f(v):
        try:
            return float(v) if v not in (None, "") else None
        except ValueError:
            return None

    def _titles(v):
        # CSV stores titles as a Python list repr; normalize to JSON
        if not v:
            return ""
        try:
            parsed = ast.literal_eval(v)
            if isinstance(parsed, list):
                return json.dumps(parsed)
        except (ValueError, SyntaxError):
            pass
        return json.dumps([v])

    with get_db() as db:
        db.execute("DELETE FROM h1b_sponsors")
        count = 0
        for r in rows:
            name = (r.get("company_name") or "").strip()
            if not name:
                continue
            approvals = _f(r.get("Total Approvals"))
            db.execute("""
                INSERT INTO h1b_sponsors (name, name_norm, industry, website, city, state,
                    executives, total_funding, latest_funding_stage, latest_funding_date,
                    total_approvals, total_denials, approval_rate, median_salary, top_titles, has_h1b)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, normalize_sponsor_name(name),
                r.get("industry", "") or "", r.get("website", "") or "",
                (r.get("city", "") or "").title(), r.get("state", "") or "",
                r.get("executive_officers", "") or "",
                _f(r.get("total_funding")), r.get("latest_funding_stage", "") or "",
                r.get("latest_funding_date", "") or "",
                approvals, _f(r.get("Total Denials")), _f(r.get("Approval_Rate")),
                _f(r.get("median_salary_offered")), _titles(r.get("top_job_titles_sponsored")),
                1 if approvals is not None else 0,
            ))
            count += 1
        return count


def lookup_sponsor(company: str) -> dict | None:
    """Find H-1B sponsorship data for a company by normalized name (exact, then prefix match)."""
    norm = normalize_sponsor_name(company)
    if not norm:
        return None
    with get_db() as db:
        row = db.execute(
            """SELECT * FROM h1b_sponsors
               WHERE has_h1b = 1 AND (name_norm = ? OR name_norm LIKE ? OR ? LIKE name_norm || ' %')
               ORDER BY (name_norm = ?) DESC, total_approvals DESC LIMIT 1""",
            (norm, norm + " %", norm, norm),
        ).fetchone()
        return dict(row) if row else None


def lookup_sponsor_executives(company: str) -> dict | None:
    """Find any sponsor row (incl. funding-only) with executives listed, for outreach."""
    norm = normalize_sponsor_name(company)
    if not norm:
        return None
    with get_db() as db:
        row = db.execute(
            """SELECT name, executives, website, latest_funding_stage FROM h1b_sponsors
               WHERE executives != '' AND (name_norm = ? OR name_norm LIKE ?)
               ORDER BY (name_norm = ?) DESC LIMIT 1""",
            (norm, norm + " %", norm),
        ).fetchone()
        return dict(row) if row else None


def get_sponsors(search=None, min_approvals=None, min_rate=None, state=None,
                 eng_only=False, sort="approvals", limit=50, offset=0):
    clauses, params = ["has_h1b = 1"], []
    if search:
        clauses.append("(name LIKE ? OR top_titles LIKE ? OR city LIKE ?)")
        params += [f"%{search}%"] * 3
    if min_approvals is not None:
        clauses.append("total_approvals >= ?")
        params.append(min_approvals)
    if min_rate is not None:
        clauses.append("approval_rate >= ?")
        params.append(min_rate)
    if state:
        clauses.append("state = ?")
        params.append(state.upper())
    if eng_only:
        clauses.append("""(UPPER(top_titles) LIKE '%SOFTWARE%' OR UPPER(top_titles) LIKE '%ENGINEER%'
            OR UPPER(top_titles) LIKE '%DEVELOPER%' OR UPPER(top_titles) LIKE '%DATA%')""")
    where = "WHERE " + " AND ".join(clauses)
    order = {
        "approvals": "total_approvals DESC",
        "rate": "approval_rate DESC, total_approvals DESC",
        "salary": "median_salary DESC NULLS LAST",
        "name": "name COLLATE NOCASE ASC",
    }.get(sort, "total_approvals DESC")
    with get_db() as db:
        rows = db.execute(
            f"SELECT * FROM h1b_sponsors {where} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) FROM h1b_sponsors {where}", params).fetchone()[0]
        return {"sponsors": [dict(r) for r in rows], "total": total}


def sponsor_counts() -> dict:
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM h1b_sponsors").fetchone()[0]
        h1b = db.execute("SELECT COUNT(*) FROM h1b_sponsors WHERE has_h1b = 1").fetchone()[0]
        return {"total": total, "with_h1b": h1b}


if __name__ == "__main__":
    init_db()
    migrate_json_to_db()
    print("DB initialized and migrated.")
