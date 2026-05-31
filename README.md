# JobHunter

AI-powered job discovery and application tracking platform. Aggregates listings from 10+ ATS platforms and job APIs, evaluates them against your resume with LLM-powered matching, generates personalized recruiter outreach messages, and provides a complete pipeline from discovery to application tracking.

## Features

### Discovery Engine

- **Multi-source job aggregation** — pulls jobs from 6 different data sources in parallel:
  - **ATS Direct APIs** — Greenhouse, Lever, Ashby (GraphQL), Workday, Amazon, SmartRecruiters, Oracle Cloud HCM, Pinpoint
  - **JSearch API** — aggregates Indeed, LinkedIn, Glassdoor, ZipRecruiter via RapidAPI
  - **Adzuna API** — additional job board coverage (free tier: 250 req/day)
  - **SimplifyJobs GitHub** — curates new-grad positions from the SimplifyJobs/New-Grad-Positions repo
  - **LinkedIn scraping** — direct LinkedIn job fetching via company LinkedIn IDs
  - **Manual URL add** — paste any job URL to auto-fetch title, company, location, and full JD
- **Parallel ATS fetching** — ThreadPoolExecutor with 12 workers, discovery completes in ~60 seconds across 290+ companies
- **Smart deduplication** — prevents duplicate entries from multiple sources via title+company matching
- **US-only filtering** — intelligent location detection filters out non-US postings
- **Freshness controls** — configurable discovery window (24 hours, 48 hours, 3 days, 1 week)
- **Live discovery status** — real-time phase display on dashboard (e.g., "Fetching ATS companies...", "Running JSearch queries...")
- **Persistent status** — discovery run history survives server restarts via SQLite key-value store

### AI-Powered Job Evaluation

- **Multi-provider LLM support** — works with Gemini (default), Anthropic Claude, or OpenAI GPT
- **Resume-to-JD matching** — LLM evaluates candidate fit and returns a 0-100 match percentage with detailed scoring rationale
- **Hard-skip rules** — automatic zero-cost filtering for deal-breakers (PhD required, security clearance, no sponsorship, senior-only roles) before LLM evaluation
- **Hard enforcement caps** — post-LLM score adjustments for citizenship requirements, ML-specialist roles, seniority mismatches
- **Salary extraction** — LLM extracts salary range (min/max) from job descriptions, displayed as badges on job cards
- **Team and project extraction** — identifies specific team names and project/product names from JDs
- **Scam detection** — flags suspicious or fake job postings
- **Sponsorship detection** — distinguishes actual "no sponsorship" statements from E-Verify boilerplate
- **Batch matching** — "Match All" evaluates all pending jobs sequentially with outreach generation for strong matches

### Resume Intelligence

- **5 resume variants** — AI/ML, Frontend, Backend, SRE/DevOps, Full Stack
- **Keyword-based recommendation** — exhaustive keyword matching against JD to recommend the best resume variant
- **Resume scoring** — scores each resume variant against the job, showing percentage fit for all five
- **Matched keywords display** — shows which specific keywords matched for transparency

### Recruiter Outreach

- **AI-generated messages** — LLM creates personalized LinkedIn recruiter messages (full and short versions)
- **Context-aware** — uses job title, company, team, match analysis, and resume highlights
- **One-click copy** — copy outreach messages directly from the job detail panel
- **Batch generation** — Match All automatically generates outreach for jobs scoring 50%+

### URL-Based Job Fetching

Paste any job URL and JobHunter auto-extracts the details:

| ATS | URL Pattern | Method |
|-----|------------|--------|
| **Greenhouse** | `boards.greenhouse.io/*/jobs/*`, `?gh_jid=` param | REST API |
| **Lever** | `jobs.lever.co/*/*` | REST API |
| **Ashby** | `jobs.ashbyhq.com/*/*` | GraphQL API |
| **Workday** | `*.myworkdayjobs.com/*/job/*` | JSON API |
| **LinkedIn** | `linkedin.com/jobs/view/*` | Guest API (full JD) |
| **Oracle HCM** | `*.oraclecloud.com/hcmUI/*/job/*` | OG meta tags |
| **Any URL** | Fallback | OG tags + HTML scraping |

### Job Queue

- **Paginated list** — 25 jobs per page with status filter tabs (Pending, Applied, Skipped, Blocked, All)
- **Color-coded ATS badges** — distinct colors for each ATS platform (green for Greenhouse, orange for Workday, blue for LinkedIn, etc.)
- **Salary display** — salary range shown on both job cards and detail panel
- **Auto-advance** — after taking action (apply, skip, block), automatically shows the next job
- **Detail panel** — full JD view with match results, resume recommendation, outreach, and action buttons
- **Inline actions** — Applied, Applied + Recruiter, Contacted, Skip, No Visa, Expired, Bad Link, Not US, Block Company
- **Follow-up dialog** — after clicking Apply, prompts to log what happened with optional follow-up reminder

### LinkedIn Integration

- **Company LinkedIn IDs** — stored per company for precise recruiter searches
- **Recruiter search** — one-click LinkedIn People Search filtered by company ID for "technical recruiter" or "talent acquisition"
- **Hiring manager search** — search for engineering managers at the company
- **Referral search** — search for potential referral connections
- **Inline LinkedIn ID editor** — edit LinkedIn IDs directly from any page

### Email Discovery

- **Hunter.io integration** — finds recruiter email addresses and email patterns at target companies
- **Domain detection** — auto-detects company email domains
- **Pattern display** — shows email pattern (e.g., `{first}.{last}@company.com`) for manual use
- **Collected emails dashboard** — centralized view of all discovered emails

### Application Tracking

- **Manual and automatic logging** — applications created from job queue actions or manually
- **Add by URL** — paste a job URL to auto-create an application with fetched details
- **Status tracking** — Applied, Interview, Offer, Rejected, Withdrawn, Ghosted
- **Salary tracking** — log salary range per application
- **Resume used** — track which resume variant was submitted
- **Notes** — per-application notes
- **Recruiter contacts** — link recruiter information to specific applications

### Auto-Apply Engine

- **Semi-automated applying** — opens job links sequentially, pauses for manual completion
- **Configurable thresholds** — minimum match score and job limit
- **Status tracking** — real-time progress with pause/resume/stop controls
- **Action logging** — records outcome (applied, applied + recruiter, skipped) for each job

### Reminders

- **Follow-up scheduling** — set reminders with date/time picker linked to applications
- **Due reminders dashboard** — prominent display of overdue follow-ups on the main dashboard
- **Completion tracking** — mark reminders as done

### Analytics

- **Application stats** — total applications, weekly/monthly counts, average match percentage
- **By company** — applications per company with counts
- **By status** — breakdown across all status types
- **By source** — which discovery sources yield the most applications
- **By resume** — which resume variant is used most
- **By ATS** — job distribution across ATS platforms
- **Match distribution** — histogram of AI match scores (0-19, 20-39, 40-59, 60-79, 80-100)
- **Recruiters by company** — recruiter contact distribution
- **30-day timeline** — daily application activity chart

### Company Management

- **290+ pre-configured companies** — with ATS type, slug, and LinkedIn ID
- **Company blocking** — block companies to auto-skip all their roles (e.g., no sponsorship)
- **Blocklist management** — view, add, remove blocked companies from Settings
- **Blacklist rules** — JSON-based keyword and company name auto-skip rules

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11+, FastAPI, SQLite (WAL mode) |
| Frontend | React 18, Vite 6, Tailwind CSS 4 |
| AI | Gemini (default), Anthropic Claude, or OpenAI GPT |
| Data | JSearch API, Adzuna API, SimplifyJobs GitHub, direct ATS APIs |
| Email | Hunter.io API |
| Styling | Dark theme, CSS animations, responsive design |

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- At least one LLM API key (Gemini recommended for free tier)

### Installation

```bash
git clone https://github.com/thejusthom/jobhunter.git
cd jobhunter

# Backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt

# Frontend
cd frontend
npm install
cd ..
```

### Environment Variables

Create a `.env` file in the project root:

```env
# LLM Provider (pick one)
LLM_PROVIDER=gemini                    # gemini (default), anthropic, or openai
GEMINI_API_KEY=your_gemini_key         # Free tier available
# ANTHROPIC_API_KEY=your_anthropic_key
# OPENAI_API_KEY=your_openai_key
# LLM_MODEL=gemini-2.5-flash          # Override default model

# Job Discovery APIs
JSEARCH_API_KEY=your_jsearch_key       # RapidAPI JSearch
ADZUNA_APP_ID=your_adzuna_id           # Optional: Adzuna API
ADZUNA_APP_KEY=your_adzuna_key

# Email Discovery
HUNTER_API_KEY=your_hunter_key         # Optional: Hunter.io

# Search Configuration
SEARCH_KEYWORDS=software engineer,backend engineer,full stack developer
SEARCH_LOCATION=United States
MIN_RELEVANCE_SCORE=0.70
```

### Running

```bash
# Terminal 1 — Backend (port 8001)
venv\Scripts\activate
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2 — Frontend (port 5174)
cd frontend
npm run dev
```

Or use the combined runner:

```bash
python run.py
```

Then open **http://localhost:5174** in your browser.

## Usage

### Discovery Flow

1. Open the **Dashboard** and select a freshness window (24h to 1 week)
2. Click **Run All** to fetch from all sources, or use individual buttons (ATS Only, JSearch Only, Adzuna Only, Simplify Only)
3. Watch the live phase indicator as discovery progresses
4. New jobs appear in the **Job Queue** when discovery completes

### Job Evaluation Flow

1. Go to **Job Queue** and review pending jobs
2. Click **Match %** to run AI evaluation — returns match score, salary range, resume recommendation, and outreach message
3. Use **Match All** to batch-evaluate all pending jobs
4. Review results: match percentage badge, salary range, team/project, strengths and gaps

### Application Flow

1. Click **Apply** on a job to open the application link
2. After applying, use the follow-up dialog to log your action
3. Optionally set a follow-up reminder
4. Track application status changes from the **Applications** page
5. Or paste a URL directly in the Applications page to quick-add

### Recruiter Outreach Flow

1. After matching a job, click **Recruiters** to search LinkedIn for recruiters at the company
2. Click **Hiring Mgr** to find engineering managers
3. Copy the AI-generated outreach message (full or short version)
4. Use **Emails** to find recruiter email addresses via Hunter.io

## API Endpoints

### Jobs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/jobs` | List jobs with filters (status, search, min_score, limit, offset) |
| GET | `/api/jobs/{id}` | Get single job |
| PATCH | `/api/jobs/{id}` | Update job status/notes |
| POST | `/api/jobs/add-by-url` | Add job by URL (auto-fetches details) |
| POST | `/api/jobs/{id}/match` | Run AI match evaluation |
| POST | `/api/jobs/{id}/outreach` | Generate recruiter outreach message |
| GET | `/api/jobs/{id}/find-emails` | Find emails via Hunter.io |
| GET | `/api/jobs/{id}/linkedin-search` | Get LinkedIn recruiter search URL |
| GET | `/api/jobs/{id}/linkedin-leaders` | Get LinkedIn hiring manager search URL |
| POST | `/api/jobs/cleanup-non-us` | Remove non-US jobs |
| POST | `/api/jobs/clear-queue` | Clear all pending jobs |

### Applications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/applications` | List applications with filters |
| POST | `/api/applications` | Create application manually |
| POST | `/api/applications/add-by-url` | Create application from URL |
| PATCH | `/api/applications/{id}` | Update application status/notes |

### Discovery
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/discover` | Trigger discovery (with source toggles and freshness) |
| GET | `/api/discover/status` | Get discovery status and phase |

### Other
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Dashboard summary stats |
| GET | `/api/analytics` | Full analytics data |
| GET/POST | `/api/blocked-companies` | Manage blocked companies |
| GET/PATCH | `/api/linkedin-id` | Manage LinkedIn IDs |
| GET/POST | `/api/reminders` | Manage reminders |
| GET/POST | `/api/recruiters` | Manage recruiter contacts |
| POST | `/api/auto-apply/start` | Start auto-apply engine |
| GET | `/api/auto-apply/status` | Get auto-apply status |
| POST | `/api/auto-apply/stop` | Stop auto-apply engine |

## Project Structure

```
jobhunter/
├── server.py               # FastAPI backend — all API endpoints, JD fetching, LLM orchestration
├── database.py              # SQLite database layer — jobs, applications, recruiters, reminders, kv_store
├── discovery.py             # JSearch API integration — keyword queries, scoring, freshness filtering
├── ats_discovery.py         # ATS platform scrapers — Greenhouse, Lever, Ashby, Workday, Amazon,
│                            #   SmartRecruiters, Oracle HCM, Pinpoint, LinkedIn, SimplifyJobs
├── llm.py                   # Multi-provider LLM layer — Gemini, Anthropic, OpenAI with retry logic
├── resume_selector.py       # Keyword-based resume variant recommendation engine
├── auto_apply.py            # CLI auto-apply script
├── auto_apply_engine.py     # Auto-apply engine (server-integrated)
├── config.py                # Environment configuration loader
├── companies.json           # 290+ company configs — ATS type, slug, LinkedIn ID, site numbers
├── blacklist.json           # Auto-skip rules — company names and description keywords
├── requirements.txt         # Python dependencies
├── run.py                   # Combined backend + frontend runner
├── .env                     # API keys and configuration (not committed)
└── frontend/
    ├── src/
    │   ├── App.jsx           # Router + sidebar navigation
    │   ├── api.js            # API client — all endpoint wrappers
    │   ├── index.css          # Tailwind theme tokens, animations, dark theme
    │   ├── components/
    │   │   └── LinkedInIdEditor.jsx  # Inline LinkedIn ID editor component
    │   └── pages/
    │       ├── Dashboard.jsx      # Overview stats, discovery controls, due reminders
    │       ├── JobQueue.jsx       # Job list + detail panel, matching, actions, outreach
    │       ├── Applications.jsx   # Application tracking, add-by-URL, status management
    │       ├── AutoApply.jsx      # Semi-automated apply engine controls
    │       ├── Evaluations.jsx    # AI match history and scores
    │       ├── Analytics.jsx      # Charts and statistics (lazy-loaded)
    │       ├── Emails.jsx         # Collected email addresses dashboard
    │       ├── Recruiters.jsx     # Recruiter contacts management
    │       ├── Reminders.jsx      # Follow-up reminder management
    │       └── Settings.jsx       # Blocked companies management
    ├── index.html
    ├── vite.config.js          # Vite + Tailwind CSS 4 + API proxy config
    └── package.json
```

## Adding Companies

Edit `companies.json` to add companies for ATS discovery:

```json
// Greenhouse
{ "name": "Stripe", "ats": "greenhouse", "slug": "stripe", "linkedin_id": "2135371" }

// Lever
{ "name": "Netflix", "ats": "lever", "slug": "netflix", "linkedin_id": "165158" }

// Ashby (uses GraphQL)
{ "name": "Ramp", "ats": "ashby", "slug": "ramp", "linkedin_id": "18700244" }

// Workday
{ "name": "Autodesk", "ats": "workday", "slug": "autodesk", "wd_num": 1, "site": "Ext" }

// Oracle HCM
{ "name": "JPMorgan Chase", "ats": "oracle_hcm", "slug": "jpmc", "site": "CX_1001" }

// LinkedIn-only (no direct ATS access)
{ "name": "Google", "ats": "linkedin", "slug": "", "linkedin_id": "1441" }
```

Supported ATS types: `greenhouse`, `lever`, `ashby`, `workday`, `amazon`, `smartrecruiters`, `oracle_hcm`, `pinpoint`, `linkedin`

## Blacklisting

Edit `blacklist.json` to auto-skip jobs by company name or description keywords:

```json
{
  "companies": ["SomeCompany"],
  "keywords": ["clearance required", "senior director"]
}
```

For persistent company blocking with UI management, use the **Block Company** button in the Job Queue or manage from **Settings**.

## Database Schema

| Table | Purpose |
|-------|---------|
| `jobs` | Discovered jobs with title, company, JD, match scores, salary, outreach |
| `applications` | Tracked applications with status, salary, resume used, notes |
| `recruiters` | Recruiter contacts linked to applications |
| `reminders` | Follow-up reminders with due dates |
| `blocked_companies` | Permanently blocked companies |
| `collected_emails` | Email addresses found via Hunter.io |
| `kv_store` | Key-value pairs for persistent state (discovery status) |
