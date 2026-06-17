"""Expand the h1b_sponsors table with companies from free public sources.

Sources:
  1. Y Combinator company directory (yc-oss public API) — ~6,000 startups
  2. Greenhouse board probing — slug-based API checks
  3. Lever board probing — slug-based API checks
  4. Ashby board probing — slug-based API checks

Each source is additive: existing companies (matched by normalized name) are
skipped. New companies are inserted with has_h1b=0 so they're clearly separate
from H-1B sponsors but still get probed for ATS boards.

Usage:
  python expand_companies.py [--source yc|greenhouse|lever|ashby|ats|all] [--dry-run]
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

import database

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 15

_CORP_RE = re.compile(
    r"\b(INC|CORP|LLC|LTD|CO|CORPORATION|INCORPORATED|COMPANY|HOLDINGS|GROUP|LP|PLC)\.?\b",
    re.IGNORECASE,
)


def _norm(name: str) -> str:
    return database.normalize_sponsor_name(name)


def _get_json(url: str, headers: dict | None = None) -> dict | list:
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def _post_json(url: str, body: dict, headers: dict | None = None) -> dict:
    hdrs = {"User-Agent": UA, "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Source 1: Y Combinator companies (yc-oss public API)
# ---------------------------------------------------------------------------
def fetch_yc_companies() -> list[dict]:
    """Fetch all YC companies via the yc-oss public JSON API (~6,000 companies)."""
    print("[YC] Fetching Y Combinator companies from yc-oss API...")

    url = "https://yc-oss.github.io/api/companies/all.json"
    try:
        data = _get_json(url)
    except Exception as e:
        print(f"  [YC] Error fetching: {e}")
        return []

    companies = []
    for h in data:
        name = (h.get("name") or "").strip()
        if not name:
            continue
        status = (h.get("status") or "").lower()
        if status in ("dead", "inactive"):
            continue
        website = h.get("website") or h.get("url") or ""
        website = website.replace("https://", "").replace("http://", "").rstrip("/")
        location = h.get("location") or ""
        city = ""
        state = ""
        if location:
            parts = [p.strip() for p in location.split(",")]
            city = parts[0] if parts else ""
            if len(parts) >= 2 and len(parts[1]) <= 3:
                state = parts[1]
        industries = h.get("industries") or []
        tags = h.get("tags") or []
        companies.append({
            "name": name,
            "website": website,
            "industry": ", ".join(industries[:3]) if industries else ", ".join(tags[:3]),
            "city": city,
            "state": state,
            "source": "yc",
        })

    print(f"  [YC] Total: {len(companies)} active YC companies")
    return companies


# ---------------------------------------------------------------------------
# Source 2: Greenhouse — probe common slug patterns from known tech companies
# ---------------------------------------------------------------------------
def _check_greenhouse(slug: str) -> dict | None:
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}"
        data = _get_json(url)
        if data.get("name"):
            return {
                "name": data["name"],
                "slug": slug,
                "ats": "greenhouse",
                "website": "",
            }
    except Exception:
        pass
    return None


def fetch_greenhouse_companies(extra_slugs: list[str] | None = None) -> list[dict]:
    """Probe Greenhouse boards API with common company name slugs."""
    print("[Greenhouse] Probing for active Greenhouse boards...")

    # Get tech company slugs from common naming patterns + well-known companies
    # The boards-api endpoint returns company info if the slug exists
    slugs = set()

    # Known tech company slugs to seed with
    seed_slugs = [
        "stripe", "figma", "notion", "discord", "ramp", "brex", "plaid",
        "datadog", "gitlab", "cloudflare", "mongodb", "elastic", "hashicorp",
        "twilio", "confluent", "databricks", "snyk", "lacework", "wiz",
        "fivetran", "dbt-labs", "airbyte", "prefect", "dagster", "temporal",
        "vercel", "netlify", "supabase", "planetscale", "neon", "turso",
        "linear", "height", "shortcut", "asana", "clickup", "monday",
        "airtable", "retool", "internal", "airplane", "windmill",
        "postman", "insomnia", "stoplight", "readme",
        "sentry", "honeycomb", "lightstep", "chronosphere",
        "vanta", "drata", "secureframe", "launchdarkly", "split",
        "amplitude", "mixpanel", "heap", "fullstory", "hotjar",
        "segment", "rudderstack", "mparticle", "hightouch",
        "algolia", "typesense", "meilisearch",
        "liveblocks", "ably", "pusher", "pubnub",
        "clerk", "auth0", "stytch", "workos",
        "resend", "sendgrid", "postmark", "mailgun",
        "novu", "courier", "knock",
        "cal-com", "calendly", "savvycal",
        "webflow", "framer", "bubble",
        "sanity", "contentful", "strapi", "hygraph",
        "prisma", "drizzle", "hasura", "graphbase",
        "railway", "render", "fly", "modal",
        "replicate", "huggingface", "anthropic", "openai", "cohere",
        "anyscale", "fireworks-ai", "together-ai",
        "pinecone", "weaviate", "qdrant", "chroma",
        "langchain", "llamaindex",
        "clickhouse", "timescale", "cockroach-labs", "singlestore",
        "materialize", "risingwave",
        "pulumi", "crossplane", "spacelift",
        "tailscale", "ngrok", "zscaler",
        "snorkflow", "labelbox", "scale-ai", "roboflow",
        "weights-and-biases", "neptune-ai", "mlflow",
        "replit", "gitpod", "coder", "codespaces",
        "loom", "mmhmm", "around", "grain",
        "deel", "remote", "oyster", "papaya-global",
        "gusto", "rippling", "justworks",
        "mercury", "meow", "novo", "relay",
        "lithic", "marqeta", "synapse",
        "chime", "varo", "current", "aspiration",
        "carta", "pulley", "equity-bee",
        "checkr", "certn", "hireright",
        "greenhouse", "lever", "ashby", "gem",
        "watershed", "persefoni", "sinai",
        "opensea", "blur", "magic-eden",
        "alchemy", "infura", "moralis",
        "verifiable", "truework", "argyle",
        "ironclad", "juro", "agiloft", "icertis",
        "gong", "chorus", "clari", "salesloft", "outreach",
        "attentive", "klaviyo", "customer-io", "braze",
        "highspot", "seismic", "showpad",
        "descript", "runway", "pika",
        "flexport", "project44", "fourkites",
        "samsara", "motive", "platform-science",
        "toast", "square", "clover",
        "benchling", "dotmatics", "scibite",
    ]
    slugs.update(seed_slugs)
    if extra_slugs:
        slugs.update(extra_slugs)

    companies = []
    found = 0
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_check_greenhouse, s): s for s in slugs}
        for f in as_completed(futures):
            result = f.result()
            if result:
                companies.append({
                    "name": result["name"],
                    "website": "",
                    "industry": "tech",
                    "city": "",
                    "state": "",
                    "source": "greenhouse_probe",
                    "ats_type": "greenhouse",
                    "ats_slug": result["slug"],
                })
                found += 1

    print(f"  [Greenhouse] Found {found}/{len(slugs)} active boards")
    return companies


# ---------------------------------------------------------------------------
# Source 3: Lever — probe jobs.lever.co/{slug} for active boards
# ---------------------------------------------------------------------------
def _check_lever(slug: str) -> dict | None:
    try:
        url = f"https://api.lever.co/v0/postings/{slug}?limit=1"
        data = _get_json(url)
        if isinstance(data, list) and len(data) > 0:
            return {"slug": slug, "name": slug.replace("-", " ").title()}
    except Exception:
        pass
    return None


def fetch_lever_companies() -> list[dict]:
    """Probe Lever API with common company name slugs."""
    print("[Lever] Probing for active Lever boards...")

    slugs = [
        "stripe", "netlify", "figma", "notion", "temporal", "databricks",
        "anthropic", "openai", "datadog", "cloudflare", "snyk", "wiz",
        "lacework", "grafana", "hashicorp", "cockroachlabs", "planetscale",
        "airbyte", "fivetran", "mux", "vercel", "railway", "supabase",
        "linear", "loom", "descript", "runway", "pika-labs",
        "amplitude", "mixpanel", "brex", "ramp", "mercury",
        "deel", "remote", "oyster", "gusto", "rippling",
        "sentry", "honeycomb", "vanta", "drata", "launchdarkly",
        "retool", "postman", "algolia", "clerk", "workos",
        "cal-com", "resend", "webflow", "sanity", "contentful",
        "prisma", "hasura", "clickhouse", "timescaledb",
        "pulumi", "tailscale", "ngrok", "replit", "gitpod",
        "labelbox", "scale", "roboflow", "weights-biases",
        "checkr", "ironclad", "gong", "attentive", "klaviyo",
        "flexport", "samsara", "toast", "benchling",
        "pinecone", "weaviate", "cohere", "anyscale",
        "modal", "replicate", "huggingface",
        "fly", "render", "neon",
        "carta", "chime", "plaid", "marqeta",
        "ashby", "greenhouse", "gem-analytics",
        "watershed", "opensea", "alchemy",
    ]

    companies = []
    found = 0
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_check_lever, s): s for s in slugs}
        for f in as_completed(futures):
            result = f.result()
            if result:
                companies.append({
                    "name": result["name"],
                    "website": "",
                    "industry": "tech",
                    "city": "",
                    "state": "",
                    "source": "lever_probe",
                    "ats_type": "lever",
                    "ats_slug": result["slug"],
                })
                found += 1

    print(f"  [Lever] Found {found}/{len(slugs)} active boards")
    return companies


# ---------------------------------------------------------------------------
# Source 4: Ashby — probe their public API
# ---------------------------------------------------------------------------
def _check_ashby(slug: str) -> dict | None:
    try:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        data = _get_json(url)
        if data.get("jobs") is not None:
            title = data.get("title") or slug.replace("-", " ").title()
            return {"slug": slug, "name": title}
    except Exception:
        pass
    return None


def fetch_ashby_companies() -> list[dict]:
    """Probe Ashby API with common company name slugs."""
    print("[Ashby] Probing for active Ashby boards...")

    slugs = [
        "notion", "linear", "ramp", "brex", "mercury", "vercel",
        "railway", "supabase", "neon", "turso", "cal-com",
        "resend", "clerk", "stytch", "workos", "descript",
        "runway", "pika", "liveblocks", "knock", "novu",
        "modal", "replicate", "pinecone", "weaviate", "chroma",
        "temporal", "prefect", "dagster", "windmill",
        "airplane", "retool", "postman",
        "vanta", "drata", "secureframe",
        "hightouch", "rudderstack", "census",
        "sanity", "contentful", "strapi",
        "webflow", "framer", "bubble",
        "sentry", "honeycomb", "axiom",
        "tailscale", "ngrok", "boundary",
        "clickhouse", "timescale", "singlestore",
        "pulumi", "spacelift", "crossplane",
        "labelbox", "scale", "roboflow",
        "benchling", "deepmind", "anthropic", "openai",
        "anyscale", "together", "fireworks",
        "deel", "remote", "oyster",
        "gusto", "rippling", "justworks",
        "carta", "pulley",
        "gong", "salesloft", "outreach",
        "attentive", "klaviyo", "customer-io", "braze",
        "flexport", "samsara", "motive",
        "toast", "square",
    ]

    companies = []
    found = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_check_ashby, s): s for s in slugs}
        for f in as_completed(futures):
            result = f.result()
            if result:
                companies.append({
                    "name": result["name"],
                    "website": "",
                    "industry": "tech",
                    "city": "",
                    "state": "",
                    "source": "ashby_probe",
                    "ats_type": "ashby",
                    "ats_slug": result["slug"],
                })
                found += 1

    print(f"  [Ashby] Found {found}/{len(slugs)} active boards")
    return companies


# ---------------------------------------------------------------------------
# Source 5: GitHub job lists (Simplify, Jobright — extract ATS from apply URLs)
# ---------------------------------------------------------------------------
def _fetch_github_raw(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _extract_ats_from_url(url: str) -> tuple[str | None, str | None]:
    """Extract ATS type and slug from a job application URL."""
    import re as _r
    gh = _r.search(r'boards\.greenhouse\.io/([^/\"?]+)', url)
    if gh:
        return "greenhouse", gh.group(1)
    gh2 = _r.search(r'job-boards\.greenhouse\.io/([^/\"?]+)', url)
    if gh2:
        return "greenhouse", gh2.group(1)
    lv = _r.search(r'jobs\.lever\.co/([^/\"?]+)', url)
    if lv:
        return "lever", lv.group(1)
    ash = _r.search(r'jobs\.ashbyhq\.com/([^/\"?]+)', url)
    if ash:
        return "ashby", ash.group(1)
    sr = _r.search(r'careers\.smartrecruiters\.com/([^/\"?]+)', url)
    if sr:
        return "smartrecruiters", sr.group(1)
    pp = _r.search(r'([^/.]+)\.pinpointhq\.com', url)
    if pp:
        return "pinpoint", pp.group(1)
    return None, None


def fetch_github_job_lists() -> list[dict]:
    """Pull companies with ATS info from popular GitHub job listing repos."""
    print("[GitHub] Fetching companies from GitHub job listing repos...")

    sources = [
        ("Simplify Summer 2026", "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"),
        ("Jobright New Grad", "https://raw.githubusercontent.com/jobright-ai/2026-Software-Engineer-New-Grad/master/README.md"),
    ]

    all_found = {}  # name -> {ats_type, ats_slug, website}
    for label, url in sources:
        try:
            content = _fetch_github_raw(url)
        except Exception as e:
            print(f"  [{label}] Failed: {e}")
            continue

        count = 0
        for row in re.finditer(r'<tr>(.*?)</tr>', content, re.DOTALL):
            row_text = row.group(1)
            # Company name
            name_m = re.search(r'<a[^>]*>([^<]+)</a></strong>', row_text)
            if not name_m:
                # Try markdown format
                name_m = re.search(r'\*\*\[([^\]]+)\]', row_text)
            if not name_m:
                continue
            name = name_m.group(1).strip()
            if not name or name in all_found:
                continue

            # Extract ATS from application URLs
            ats_type, ats_slug = None, None
            for url_m in re.finditer(r'href="([^"]+)"', row_text):
                href = url_m.group(1)
                if 'simplify.jobs' in href or 'imgur.com' in href:
                    continue
                t, s = _extract_ats_from_url(href)
                if t:
                    ats_type, ats_slug = t, s
                    break

            # Website from company link
            website = ""
            web_m = re.search(r'<a href="(https?://[^"]+)"[^>]*>' + re.escape(name), row_text)
            if not web_m:
                # Jobright format
                web_m = re.search(r'\*\*\[' + re.escape(name) + r'\]\((https?://[^)]+)\)', row_text)
            if web_m:
                w = web_m.group(1)
                if 'simplify.jobs' not in w and 'jobright.ai' not in w:
                    website = w.replace("https://", "").replace("http://", "").rstrip("/")

            all_found[name] = {
                "name": name,
                "website": website,
                "industry": "tech",
                "city": "",
                "state": "",
                "source": "github_jobs",
                "ats_type": ats_type,
                "ats_slug": ats_slug,
            }
            count += 1

        # Also handle markdown table format (jobright style)
        for line in content.split('\n'):
            if not line.startswith('|'):
                continue
            cols = line.split('|')
            if len(cols) < 3:
                continue
            name_m = re.match(r'\s*\*\*\[([^\]]+)\]\(([^)]+)\)\*\*', cols[1].strip())
            if not name_m:
                continue
            name = name_m.group(1).strip()
            website_raw = name_m.group(2).strip()
            if name in all_found:
                continue
            website = ""
            if 'jobright.ai' not in website_raw and 'simplify.jobs' not in website_raw:
                website = website_raw.replace("https://", "").replace("http://", "").rstrip("/")

            # Check other columns for ATS URLs
            ats_type, ats_slug = None, None
            for col in cols[2:]:
                for url_m in re.finditer(r'https?://[^\s)\"]+', col):
                    t, s = _extract_ats_from_url(url_m.group())
                    if t:
                        ats_type, ats_slug = t, s
                        break
                if ats_type:
                    break

            all_found[name] = {
                "name": name,
                "website": website,
                "industry": "tech",
                "city": "",
                "state": "",
                "source": "github_jobs",
                "ats_type": ats_type,
                "ats_slug": ats_slug,
            }
            count += 1

        with_ats = sum(1 for v in all_found.values() if v.get("ats_type"))
        print(f"  [{label}] {count} companies ({with_ats} with confirmed ATS)")

    companies = list(all_found.values())
    with_ats = sum(1 for c in companies if c.get("ats_type"))
    print(f"  [GitHub] Total: {len(companies)} unique companies, {with_ats} with confirmed ATS boards")
    return companies


# ---------------------------------------------------------------------------
# Insert into database
# ---------------------------------------------------------------------------
def insert_new_companies(companies: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """Insert companies that don't already exist (by normalized name). Returns (added, skipped)."""
    database.init_db()

    with database.get_db() as db:
        existing = {
            r[0]
            for r in db.execute("SELECT name_norm FROM h1b_sponsors").fetchall()
        }

    new_companies = []
    skipped = 0
    seen_norms = set()
    for c in companies:
        norm = _norm(c["name"])
        if not norm or norm in existing or norm in seen_norms:
            skipped += 1
            continue
        seen_norms.add(norm)
        new_companies.append(c)

    if dry_run:
        print(f"\n[DRY RUN] Would add {len(new_companies)} new companies (skipped {skipped} duplicates)")
        for c in new_companies[:20]:
            print(f"  + {c['name']} ({c.get('source', '?')}) — {c.get('website', '')}")
        if len(new_companies) > 20:
            print(f"  ... and {len(new_companies) - 20} more")
        return len(new_companies), skipped

    added = 0
    with database.get_db() as db:
        for c in new_companies:
            norm = _norm(c["name"])
            db.execute("""
                INSERT INTO h1b_sponsors
                    (name, name_norm, industry, website, city, state,
                     executives, total_funding, latest_funding_stage,
                     latest_funding_date, total_approvals, total_denials,
                     approval_rate, median_salary, top_titles, has_h1b,
                     ats_type, ats_slug, ats_checked)
                VALUES (?, ?, ?, ?, ?, ?, '', NULL, '', '', NULL, NULL, NULL, NULL, '', 0, ?, ?, ?)
            """, (
                c["name"], norm,
                c.get("industry", ""), c.get("website", ""),
                c.get("city", ""), c.get("state", ""),
                c.get("ats_type"),
                c.get("ats_slug"),
                # If we already know the ATS, mark as checked
                time.strftime("%Y-%m-%dT%H:%M:%SZ") if c.get("ats_type") else None,
            ))
            added += 1

    print(f"\nAdded {added} new companies, skipped {skipped} duplicates")
    return added, skipped


def main():
    parser = argparse.ArgumentParser(description="Expand company pool from public sources")
    parser.add_argument("--source", default="all", choices=["yc", "greenhouse", "lever", "ashby", "ats", "github", "all"],
                        help="Which source to pull from (ats = greenhouse+lever+ashby)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB, just show what would be added")
    args = parser.parse_args()

    all_companies = []

    if args.source in ("yc", "all"):
        all_companies.extend(fetch_yc_companies())

    if args.source in ("greenhouse", "ats", "all"):
        all_companies.extend(fetch_greenhouse_companies())

    if args.source in ("lever", "ats", "all"):
        all_companies.extend(fetch_lever_companies())

    if args.source in ("ashby", "ats", "all"):
        all_companies.extend(fetch_ashby_companies())

    if args.source in ("github", "all"):
        all_companies.extend(fetch_github_job_lists())

    if not all_companies:
        print("No companies fetched from any source.")
        return

    print(f"\nTotal fetched: {len(all_companies)} companies across all sources")
    added, skipped = insert_new_companies(all_companies, dry_run=args.dry_run)

    if not args.dry_run:
        stats = database.sponsor_counts()
        print(f"\nDatabase totals: {stats['total']} companies, {stats['with_h1b']} H-1B sponsors, "
              f"{stats['ats_checked']} checked, {stats['ats_resolved']} with boards")


if __name__ == "__main__":
    main()
