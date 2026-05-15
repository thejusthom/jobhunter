import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

JSEARCH_API_KEY: str = os.getenv("JSEARCH_API_KEY", "")

_raw_keywords = os.getenv("SEARCH_KEYWORDS", "software engineer")
SEARCH_KEYWORDS: list[str] = [k.strip() for k in _raw_keywords.split(",") if k.strip()]

SEARCH_LOCATION: str = os.getenv("SEARCH_LOCATION", "United States")
MIN_RELEVANCE_SCORE: float = float(os.getenv("MIN_RELEVANCE_SCORE", "70"))

BLACKLIST_PATH: str = os.getenv("BLACKLIST_PATH", "blacklist.json")
QUEUE_PATH: str = os.getenv("QUEUE_PATH", "queue.json")
LOG_PATH: str = os.getenv("LOG_PATH", "application_log.json")
