# JobHunter

AI-powered job discovery and application tracking tool. Aggregates job listings from multiple ATS platforms and JSearch API, scores them for relevance, and provides a clean UI to review, apply, and track your job search progress.

## Features

- **Multi-source discovery** — pulls jobs from Greenhouse, Lever, Ashby, Amazon, Workday, Pinpoint, and JSearch API (Indeed, LinkedIn, etc.)
- **Smart scoring** — keyword-based relevance scoring (0-1) with configurable thresholds
- **AI matching** — LLM-powered job-to-resume match percentage with team/project extraction
- **Resume recommendation** — automatically suggests which resume variant to use (AI/ML, Frontend, Backend, SRE, Full Stack) based on exhaustive keyword matching against the job description
- **US-only filtering** — smart location detection filters out non-US postings
- **Company blocking** — block companies (e.g., no sponsorship) to auto-skip all their roles
- **LinkedIn recruiter search** — one-click LinkedIn People Search with company ID filtering
- **Application tracking** — log applications with status, resume used, salary info, and notes
- **Recruiter management** — track recruiter contacts per application
- **Reminders** — set follow-up reminders with date/time picker
- **Analytics dashboard** — lazy-loaded stats: applications by company/status/source/resume, jobs by ATS, match % distribution, daily application timeline
- **Pagination** — 25 jobs per page with status filter tabs
- **Freshness controls** — configurable discovery window (24h, 48h, 3 days, 1 week)

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python, FastAPI, SQLite (WAL mode) |
| Frontend | React, Vite 6, Tailwind CSS 4 |
| AI | OpenAI GPT (job matching, hard-skip checks) |
| Data | JSearch API (RapidAPI), direct ATS API scraping |

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- JSearch API key ([rapidapi.com/jsearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch))
- OpenAI API key (for AI matching features)

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
JSEARCH_API_KEY=your_jsearch_key
OPENAI_API_KEY=your_openai_key

# Optional
SEARCH_KEYWORDS=software engineer,backend engineer,full stack developer
SEARCH_LOCATION=United States
MIN_RELEVANCE_SCORE=0.70
```

### Running

Start both the backend and frontend:

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

### Discovery

From the **Dashboard**, click **Run Discovery** to fetch fresh jobs. Use the freshness dropdown to control how far back to search. Discovery runs in the background and pulls from:

- **JSearch API** — aggregates Indeed, LinkedIn, Glassdoor, ZipRecruiter, and more
- **ATS APIs** — directly queries company career pages (Greenhouse, Lever, Ashby, Workday, Amazon, Pinpoint)

### Job Queue

Review discovered jobs in the **Job Queue**. For each job you can:

- **Apply** — opens the job link, then shows a follow-up dialog to log what you did
- **Match %** — runs AI evaluation against your resume to get a match score
- **Find Recruiters** — opens LinkedIn People Search filtered to that company
- **Skip** — mark as not interested
- **No Sponsorship** — skip the role with a note
- **Block Company** — skip all current and future roles from that company

Inline action buttons are also available directly in the detail panel without needing to click Apply first.

### Tracking

- **Applications** — view all logged applications with status tracking
- **Recruiters** — manage recruiter contacts linked to applications
- **Reminders** — set follow-up reminders with date/time picker
- **AI Evals** — review AI match scores and resume recommendations

### Analytics

The **Analytics** page (lazy-loaded) shows:

- Total applications, weekly/monthly counts, recruiter contacts
- Applications by company, status, source, and resume type
- Jobs by ATS platform and company
- Match percentage distribution
- 30-day application timeline

### Settings

Manage **blocked companies** — view the blocklist and unblock companies if needed.

## Project Structure

```
jobhunter/
├── server.py              # FastAPI backend with all API endpoints
├── database.py            # SQLite database layer
├── discovery.py           # JSearch API integration
├── ats_discovery.py       # ATS platform scrapers (Greenhouse, Lever, etc.)
├── llm.py                 # OpenAI LLM integration for job matching
├── resume_selector.py     # Keyword-based resume recommendation
├── config.py              # Environment configuration
├── companies.json         # ATS company configs + LinkedIn IDs
├── blacklist.json         # Auto-skip rules
├── requirements.txt       # Python dependencies
├── run.py                 # Combined backend + frontend runner
└── frontend/
    ├── src/
    │   ├── App.jsx        # Router + navigation
    │   ├── api.js         # API client
    │   ├── index.css      # Tailwind theme tokens
    │   └── pages/
    │       ├── Dashboard.jsx
    │       ├── JobQueue.jsx
    │       ├── Applications.jsx
    │       ├── Evaluations.jsx
    │       ├── Analytics.jsx
    │       ├── Recruiters.jsx
    │       ├── Reminders.jsx
    │       └── Settings.jsx
    ├── index.html
    ├── vite.config.js
    └── package.json
```

## Adding Companies

Edit `companies.json` to add companies for ATS discovery:

```json
{ "name": "Stripe", "ats": "greenhouse", "slug": "stripe", "linkedin_id": "2135371" }
```

For companies not on a supported ATS (discovered via JSearch), add with `"ats": null` to enable LinkedIn recruiter search:

```json
{ "name": "Andiamo", "ats": null, "slug": "", "linkedin_id": "32309" }
```

Supported ATS platforms: `greenhouse`, `lever`, `ashby`, `amazon`, `workday`, `pinpoint`

## Blacklisting

Edit `blacklist.json` to auto-skip jobs by company name or description keywords:

```json
{
  "companies": ["SomeCompany"],
  "keywords": ["clearance required", "senior director"]
}
```

For persistent company blocking with UI management, use the **Block Company** button in the Job Queue or manage from **Settings**.
