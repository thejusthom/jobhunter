# JobHunter

Morning job discovery + manual apply queue. Fetches jobs from JSearch API, scores them, and walks you through each one in the terminal — open the ones you want, skip the rest.

## Setup

```bash
git clone <repo>
cd jobhunter
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
```

Get a free JSearch API key from [rapidapi.com/jsearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch), then add it to `.env`:

```
JSEARCH_API_KEY=your_key_here
```

## Usage

```bash
python run.py                                          # discover + review queue
python run.py --skip-discovery                         # skip fetch, review existing queue
python run.py --queries "golang engineer,rust backend" # override keywords
python run.py --location "New York"                    # override location
python run.py                    # JSearch + ATS (all 48 companies) + queue
python run.py --skip-jsearch     # ATS only
python run.py --skip-ats         # JSearch only
python run.py --skip-discovery   # Just review the queue
```

## How it works

1. Searches JSearch for each keyword in `SEARCH_KEYWORDS`
2. Filters out blacklisted companies/keywords (`blacklist.json`)
3. Scores each job (keyword match, 0–1)
4. Adds qualifying jobs to `queue.json`
5. Walks you through each pending job:
   - `y` — opens in browser, logs to `application_log.json`
   - `n` — marks skipped
   - `skip` — leave pending, review later
   - `quit` — save and exit

## Blacklisting

Edit `blacklist.json` to add companies or description keywords to auto-skip.
