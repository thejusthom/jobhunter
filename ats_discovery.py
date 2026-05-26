"""
ATS Discovery Module
Queries Greenhouse, Lever, Ashby, Amazon, Apple, Workday, Pinpoint,
SmartRecruiters, Oracle Cloud HCM, and LinkedIn public APIs.
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

NON_US_COUNTRIES = [
    "canada", "india", "ireland", "spain", "germany", "uk", "united kingdom",
    "france", "brazil", "australia", "japan", "singapore", "estonia", "netherlands",
    "sweden", "poland", "czech", "israel", "korea", "china", "mexico", "colombia",
    "argentina", "portugal", "italy", "belgium", "switzerland", "austria", "denmark",
    "norway", "finland", "romania", "hungary", "bulgaria", "croatia", "serbia",
    "philippines", "vietnam", "thailand", "indonesia", "malaysia", "taiwan",
    "hong kong", "new zealand",
]

NON_US_CITIES = [
    "toronto", "vancouver", "montreal", "ottawa", "calgary", "edmonton", "winnipeg",
    "london", "dublin", "berlin", "munich", "paris", "amsterdam", "stockholm",
    "warsaw", "prague", "tel aviv", "bangalore", "bengaluru", "hyderabad", "mumbai",
    "delhi", "chennai", "pune", "kolkata", "noida", "gurgaon", "sydney", "melbourne",
    "tokyo", "singapore", "seoul", "beijing", "shanghai", "sao paulo", "mexico city",
    "bogota", "buenos aires", "lisbon", "barcelona", "madrid", "rome", "milan",
    "zurich", "geneva", "vienna", "copenhagen", "oslo", "helsinki", "bucharest",
    "brisbane", "auckland", "wellington", "kuala lumpur", "jakarta", "manila",
    "ho chi minh", "hanoi", "taipei", "bangkok", "guadalajara", "monterrey",
    "cape town", "johannesburg", "nairobi", "lagos", "cairo", "riyadh", "dubai",
    "abu dhabi", "doha", "muscat",
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
    if not location or location.strip() in ("", ","):
        return True
    loc_lower = location.lower().strip()

    # Check for known non-US countries
    for country in NON_US_COUNTRIES:
        if country in loc_lower:
            # "CA" appears in California locations — only block standalone "canada"
            return False

    # Check for known non-US cities
    for city in NON_US_CITIES:
        if city in loc_lower:
            return False

    # Canadian provinces that look like US abbreviations
    if "british columbia" in loc_lower or "can-remote" in loc_lower or "can - remote" in loc_lower:
        return False

    # "Remote - <country>" pattern: block unless it mentions US
    if "remote" in loc_lower:
        # Split on common separators
        parts = [p.strip() for p in re.split(r'[-,;|]', loc_lower) if p.strip()]
        # If there's a qualifier after "remote" and it's not US-related, reject
        for part in parts:
            if part in ("remote",):
                continue
            if part in ("us", "usa", "united states"):
                return True
            # Check if this part is a US state abbreviation or city — allow it
            us_markers = [
                "ny", "ca", "wa", "tx", "ma", "co", "ga", "il", "or", "pa",
                "fl", "nc", "mn", "ut", "az", "md", "oh", "mi", "in", "va",
                "new york", "san francisco", "seattle", "austin", "boston",
                "chicago", "los angeles", "denver", "atlanta", "dallas",
                "houston", "portland", "phoenix", "miami", "philadelphia",
                "washington", "dc", "california", "texas", "virginia",
                "massachusetts", "colorado", "georgia", "illinois", "oregon",
            ]
            if any(m in part for m in us_markers):
                return True
        # "Remote" alone with no US qualifier after checking all parts
        if len(parts) > 1:
            return False

    # "ON, CA" is Ontario, Canada — not California
    if ", on," in loc_lower or loc_lower.endswith(", on") or "ontario" in loc_lower:
        if "toronto" in loc_lower or "canada" in loc_lower or "on, ca" in loc_lower:
            return False

    return True


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
# Apple — SSR hydration data from jobs.apple.com
# ---------------------------------------------------------------------------

def _parse_apple_ssr(html_text: str) -> dict | None:
    """Extract __staticRouterHydrationData from Apple jobs HTML."""
    idx = html_text.find("__staticRouterHydrationData")
    if idx < 0:
        return None
    parse_idx = html_text.find('JSON.parse("', idx)
    if parse_idx < 0:
        return None
    inner_start = parse_idx + len('JSON.parse("')
    pos = inner_start
    while pos < len(html_text):
        next_quote = html_text.find('"', pos)
        if next_quote == -1:
            return None
        if html_text[next_quote - 1] != '\\':
            inner_end = next_quote
            break
        pos = next_quote + 1
    else:
        return None
    raw_json = html_text[inner_start:inner_end]
    unescaped = raw_json.replace('\\"', '"').replace('\\\\', '\\')
    return json.loads(unescaped)


def fetch_apple(company_name: str = "Apple") -> list:
    """Fetch software engineering jobs from jobs.apple.com via SSR data."""
    base = "https://jobs.apple.com/en-us/search"
    params = {
        "search": "software engineer",
        "location": "united-states-USA",
        # Software teams
        "team": (
            "apps-and-frameworks-SFTWR-AF "
            "core-operating-systems-SFTWR-COS "
            "machine-learning-and-ai-SFTWR-MLAI "
            "cloud-and-infrastructure-SFTWR-CLD "
            "devops-and-site-reliability-SFTWR-DSR "
            "information-systems-and-technology-SFTWR-ISTECH "
            "security-and-privacy-SFTWR-SP"
        ),
    }
    results = []
    seen_ids = set()

    for page_num in range(1, 4):  # up to 3 pages (60 jobs)
        try:
            p = {**params, "page": str(page_num)} if page_num > 1 else params
            resp = requests.get(base, params=p, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if resp.status_code != 200:
                print(f"[ats] Apple page {page_num} HTTP {resp.status_code}")
                break

            data = _parse_apple_ssr(resp.text)
            if not data:
                print(f"[ats] Apple page {page_num}: no SSR data")
                break

            search = data.get("loaderData", {}).get("search", {})
            postings = search.get("searchResults", [])
            if not postings:
                break
        except Exception as e:
            print(f"[ats] Apple page {page_num} failed: {e}")
            break

        for j in postings:
            job_id = j.get("id", "")
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            # Check US location
            locs = j.get("locations", [])
            country_ids = [loc.get("countryID", "") for loc in locs]
            if not any("USA" in c for c in country_ids):
                continue

            # Freshness check
            posted_str = j.get("postDateInGMT", "")
            if posted_str:
                try:
                    dt = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
                    if not _is_fresh(dt):
                        continue
                except (ValueError, TypeError):
                    pass

            slug_title = j.get("transformedPostingTitle", "")
            apply_url = f"https://jobs.apple.com/en-us/details/{job_id}/{slug_title}"
            city = ""
            if locs:
                city = locs[0].get("name", "")

            # Fetch full description from detail page
            description = j.get("jobSummary", "")
            try:
                detail_resp = requests.get(
                    apply_url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15,
                )
                if detail_resp.status_code == 200:
                    detail_data = _parse_apple_ssr(detail_resp.text)
                    if detail_data:
                        jd = (detail_data.get("loaderData", {})
                              .get("jobDetails", {})
                              .get("jobsData", {}))
                        full_desc = jd.get("description", "")
                        summary = jd.get("jobSummary", "")
                        if full_desc or summary:
                            description = (summary + "\n" + full_desc).strip()
                time.sleep(0.3)
            except Exception:
                pass  # fall back to search-page summary

            results.append({
                "employer_name": company_name,
                "job_title": j.get("postingTitle", ""),
                "job_description": description,
                "job_apply_link": apply_url,
                "job_city": city,
                "job_country": "US",
                "job_apply_is_direct": True,
                "job_posted_at_datetime_utc": posted_str,
                "_ats": "apple",
            })

        time.sleep(0.5)
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
        # "N Locations" is vague — extract primary location from externalPath
        if re.match(r"^\d+\s+locations?$", loc_text, re.IGNORECASE):
            path_loc = (ext_path.split("/job/")[1].split("/")[0] if "/job/" in ext_path else "")
            path_loc = path_loc.replace("---", " - ").replace("-", " ")
            if path_loc:
                loc_text = path_loc
        if not _is_us_location(loc_text):
            continue

        # Fetch full job description from detail endpoint
        description = ""
        if ext_path:
            try:
                detail_url = f"https://{slug}.wd{wd_num}.myworkdayjobs.com/wday/cxs/{slug}/{site}{ext_path}"
                dr = requests.get(
                    detail_url,
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                if dr.status_code == 200:
                    description = _strip_html(dr.json().get("jobPostingInfo", {}).get("jobDescription", ""))
                time.sleep(0.3)  # rate limit
            except Exception:
                pass
        if not description:
            description = " ".join(j.get("bulletFields", []) or [])

        results.append({
            "employer_name": company_name,
            "job_title": j.get("title", ""),
            "job_description": description,
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
# Oracle Cloud HCM — public REST API
# ---------------------------------------------------------------------------

def fetch_oracle_hcm(slug: str, company_name: str, site: str = "CX_1001") -> list:
    """Fetch jobs from Oracle Cloud HCM public REST API.
    slug = subdomain prefix, e.g. 'jpmc' for jpmc.fa.oraclecloud.com
    site = site number, e.g. 'CX_1001'
    """
    # Determine base URL — some use .fa.oraclecloud.com, some .fa.us2.oraclecloud.com
    base_urls = [
        f"https://{slug}.fa.oraclecloud.com",
        f"https://{slug}.fa.us2.oraclecloud.com",
    ]

    data = None
    base_url = None
    for base in base_urls:
        api_url = (
            f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand=requisitionList.secondaryLocations"
            f"&finder=findReqs;siteNumber={site},keyword=software engineer,selectedPostingTypes="
            f"&limit=25&offset=0"
        )
        try:
            resp = requests.get(api_url, timeout=15, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items and items[0].get("requisitionList"):
                    base_url = base
                    break
        except Exception:
            continue

    if not data or not base_url:
        print(f"[ats] Oracle HCM {company_name}: no accessible API endpoint found")
        return []

    item = data["items"][0]
    total = item.get("TotalJobsCount", 0)
    reqs = item.get("requisitionList", [])
    print(f"[ats] Oracle HCM {company_name}: {total} total jobs, {len(reqs)} in first page")

    results = []
    for j in reqs:
        loc = j.get("PrimaryLocation", "")
        country = j.get("PrimaryLocationCountry", "")

        # US filter
        if country and country.upper() != "US":
            continue
        if not country and not _is_us_location(loc):
            continue

        # Freshness
        posted = j.get("PostedDate", "")
        if posted:
            try:
                dt = datetime.fromisoformat(posted + "T00:00:00+00:00")
                if not _is_fresh(dt):
                    continue
            except (ValueError, TypeError):
                pass

        title = j.get("Title", "")
        job_id = j.get("Id", "")
        description = j.get("ShortDescriptionStr", "") or ""
        qualifications = j.get("ExternalQualificationsStr", "") or ""
        responsibilities = j.get("ExternalResponsibilitiesStr", "") or ""
        full_desc = f"{description}\n{responsibilities}\n{qualifications}".strip()

        apply_url = f"{base_url}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}"

        results.append({
            "employer_name": company_name,
            "job_title": title,
            "job_description": full_desc,
            "job_apply_link": apply_url,
            "job_city": loc,
            "job_country": "US",
            "job_apply_is_direct": True,
            "job_posted_at_datetime_utc": posted + "T00:00:00Z" if posted else "",
            "_ats": "oracle_hcm",
        })

    return results


# ---------------------------------------------------------------------------
# SmartRecruiters — public postings API
# ---------------------------------------------------------------------------

def fetch_smartrecruiters(slug: str, company_name: str) -> list:
    """Fetch jobs from SmartRecruiters public API (no key needed)."""
    results = []
    offset = 0
    limit = 100

    while True:
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        try:
            resp = requests.get(url, params={"offset": offset, "limit": limit}, timeout=15)
            if resp.status_code != 200:
                print(f"[ats] SmartRecruiters {company_name} failed: HTTP {resp.status_code}")
                break
            data = resp.json()
            postings = data.get("content", [])
            if not postings:
                break
        except Exception as e:
            print(f"[ats] SmartRecruiters {company_name} failed: {e}")
            break

        for j in postings:
            # Location filter
            loc = j.get("location", {})
            country = loc.get("country", "")
            city = loc.get("city", "")
            region = loc.get("region", "")
            loc_text = f"{city}, {region}" if city else region or ""

            if country and country.upper() not in ("US", "USA"):
                continue
            if not country and not _is_us_location(loc_text):
                continue

            # Freshness filter
            created = j.get("releasedDate", "") or j.get("createdOn", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if not _is_fresh(dt):
                        continue
                except (ValueError, TypeError):
                    pass

            title = j.get("name", "")
            job_id = j.get("id", "")

            # Fetch full posting detail for description + apply URL
            description = ""
            apply_url = f"https://jobs.smartrecruiters.com/{slug}/{job_id}"
            try:
                detail_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{job_id}"
                detail_resp = requests.get(detail_url, timeout=10)
                if detail_resp.status_code == 200:
                    detail = detail_resp.json()
                    # Get apply URL
                    if detail.get("applyUrl"):
                        apply_url = detail["applyUrl"]
                    # Get description from jobAd sections
                    sections = detail.get("jobAd", {}).get("sections", {})
                    for section_key in ("jobDescription", "qualifications", "additionalInformation"):
                        sec = sections.get(section_key, {})
                        if sec and sec.get("text"):
                            description += sec["text"] + "\n\n"
                    description = description.strip()
            except Exception:
                pass  # use empty desc if detail fetch fails

            results.append({
                "employer_name": company_name,
                "job_title": title,
                "job_description": description,
                "job_apply_link": apply_url,
                "job_city": loc_text,
                "job_country": "US",
                "job_apply_is_direct": True,
                "job_posted_at_datetime_utc": created,
                "_ats": "smartrecruiters",
            })

        # Pagination
        total = data.get("totalFound", 0)
        offset += limit
        if offset >= total:
            break

    return results


# ---------------------------------------------------------------------------
# LinkedIn — guest API, no auth required
# Uses f_C (company ID) filter to search jobs by company
# ---------------------------------------------------------------------------

_LINKEDIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _parse_linkedin_cards(html_text: str) -> list:
    """Parse LinkedIn job cards from guest API HTML response."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, "html.parser")
    jobs = []
    for card in soup.find_all("div", class_="base-card"):
        title_el = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        location_el = card.find("span", class_="job-search-card__location")
        link_el = card.find("a", class_="base-card__full-link")
        time_el = card.find("time")

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""
        loc = location_el.get_text(strip=True) if location_el else ""
        link = link_el["href"] if link_el and link_el.get("href") else ""
        posted = time_el.get("datetime", "") if time_el else ""

        # Extract job ID from link
        job_id = ""
        if link and "-" in link:
            job_id = link.rstrip("/").split("-")[-1].split("?")[0]

        if title:
            jobs.append({
                "title": title,
                "company": company,
                "location": loc,
                "link": link,
                "job_id": job_id,
                "posted": posted,
            })
    return jobs


def _linkedin_job_detail(job_id: str) -> dict:
    """Fetch full job description from LinkedIn guest API."""
    from bs4 import BeautifulSoup
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        resp = requests.get(url, headers=_LINKEDIN_HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")
        desc_el = soup.find("div", class_="show-more-less-html__markup")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""
        # Try to find apply URL
        apply_el = soup.find("a", class_="apply-button")
        apply_url = apply_el.get("href", "") if apply_el else ""
        return {"description": description, "apply_url": apply_url}
    except Exception:
        return {}


def fetch_linkedin(linkedin_id: str, company_name: str) -> list:
    """Fetch jobs for a company via LinkedIn guest API using company ID."""
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": "software engineer",
        "location": "United States",
        "start": 0,
        "f_C": linkedin_id,
        "f_TPR": "r86400",  # past 24 hours
    }

    try:
        resp = requests.get(url, params=params, headers=_LINKEDIN_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
    except Exception as e:
        print(f"[ats] LinkedIn search failed for {company_name}: {e}")
        return []

    cards = _parse_linkedin_cards(resp.text)
    if not cards:
        return []

    results = []
    for card in cards:
        title = card["title"]
        loc = card["location"]
        posted = card["posted"]

        # Basic US filter
        if loc and not any(state in loc for state in [
            ", AL", ", AK", ", AZ", ", AR", ", CA", ", CO", ", CT", ", DE", ", FL",
            ", GA", ", HI", ", ID", ", IL", ", IN", ", IA", ", KS", ", KY", ", LA",
            ", ME", ", MD", ", MA", ", MI", ", MN", ", MS", ", MO", ", MT", ", NE",
            ", NV", ", NH", ", NJ", ", NM", ", NY", ", NC", ", ND", ", OH", ", OK",
            ", OR", ", PA", ", RI", ", SC", ", SD", ", TN", ", TX", ", UT", ", VT",
            ", VA", ", WA", ", WV", ", WI", ", WY", "United States", "Remote",
        ]):
            continue

        # Freshness check
        if posted:
            try:
                dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                if not _is_fresh(dt):
                    continue
            except (ValueError, TypeError):
                pass

        # Fetch description (rate-limited)
        description = ""
        apply_url = card["link"]
        if card["job_id"]:
            time.sleep(0.5)
            detail = _linkedin_job_detail(card["job_id"])
            if detail:
                description = detail.get("description", "")
                if detail.get("apply_url"):
                    apply_url = detail["apply_url"]

        results.append({
            "employer_name": card["company"] or company_name,
            "job_title": title,
            "job_description": description,
            "job_apply_link": apply_url,
            "job_city": loc,
            "job_country": "US",
            "job_apply_is_direct": False,
            "job_posted_at_datetime_utc": posted,
            "_ats": "linkedin",
        })

    return results


# ---------------------------------------------------------------------------
# JSearch fallback — for companies without a direct ATS API
# Uses the same JSearch/RapidAPI key from discovery.py
# ---------------------------------------------------------------------------

def fetch_jsearch_company(company_name: str) -> list:
    """Search JSearch for jobs at a specific company (fallback for custom portals)."""
    from discovery import JSEARCH_KEY, JSEARCH_URL
    if not JSEARCH_KEY:
        return []

    headers = {
        "X-RapidAPI-Key": JSEARCH_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": f"software engineer at {company_name}",
        "location": "United States",
        "page": "1",
        "num_pages": "1",
        "employment_types": "FULLTIME",
        "date_posted": "today",
    }

    try:
        resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("jobs", [])
    except Exception as e:
        print(f"[ats] JSearch fallback for {company_name} failed: {e}")
        return []

    results = []
    for j in data:
        loc = j.get("job_city", "") or ""
        country = j.get("job_country", "")
        if country and country.upper() not in ("US", "USA"):
            continue

        # Only include jobs actually from this company
        employer = j.get("employer_name", "")
        if company_name.lower() not in employer.lower():
            continue

        posted = j.get("job_posted_at_datetime_utc", "")
        if posted:
            try:
                dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                if not _is_fresh(dt):
                    continue
            except (ValueError, TypeError):
                pass

        results.append({
            "employer_name": j.get("employer_name", company_name),
            "job_title": j.get("job_title", ""),
            "job_description": j.get("job_description", ""),
            "job_apply_link": j.get("job_apply_link", ""),
            "job_city": loc,
            "job_country": "US",
            "job_apply_is_direct": j.get("job_apply_is_direct", False),
            "job_posted_at_datetime_utc": posted,
            "_ats": "jsearch",
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
        ats = (company.get("ats") or "").lower()
        slug = company.get("slug", "")

        # Skip companies with no name
        if not name:
            continue
        # LinkedIn companies use linkedin_id instead of slug
        if ats == "linkedin":
            linkedin_id = company.get("linkedin_id", "")
            if not linkedin_id:
                continue
        elif not ats or not slug:
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
        elif ats == "apple":
            raw_jobs = fetch_apple(name)
        elif ats == "workday":
            wd_num = company.get("wd_num", 5)
            site = company.get("site", "")
            raw_jobs = fetch_workday(slug, name, wd_num, site)
        elif ats == "pinpoint":
            raw_jobs = fetch_pinpoint(slug, name)
        elif ats == "smartrecruiters":
            raw_jobs = fetch_smartrecruiters(slug, name)
        elif ats == "oracle_hcm":
            site = company.get("site", "CX_1001")
            raw_jobs = fetch_oracle_hcm(slug, name, site)
        elif ats == "linkedin":
            linkedin_id = company.get("linkedin_id", "")
            raw_jobs = fetch_linkedin(linkedin_id, name)
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
            threshold = 25 if ats == "workday" else SCORE_THRESHOLD
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
                "description": job.get("job_description", ""),
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
