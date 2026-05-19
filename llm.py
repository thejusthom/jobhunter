"""
Multi-provider LLM layer for JobHunter.
Supports: Gemini (REST, default), Anthropic, OpenAI.
Set LLM_PROVIDER in .env to switch providers.
"""

import os
import re
import json
import time
import requests as http_requests

_provider = None
_client = None
_model_name = None
_initialized = False


def _init():
    global _provider, _client, _model_name, _initialized
    if _initialized:
        return
    _initialized = True

    provider = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            print("[LLM] WARNING: No GEMINI_API_KEY in .env")
            return
        _provider = "gemini"
        _client = api_key
        _model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        print(f"[LLM] Using Gemini REST ({_model_name})")

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("[LLM] WARNING: No ANTHROPIC_API_KEY in .env")
            return
        try:
            import anthropic
            _client = anthropic.Anthropic(api_key=api_key)
            _provider = "anthropic"
            _model_name = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
            print(f"[LLM] Using Anthropic ({_model_name})")
        except ImportError:
            print("[LLM] anthropic not installed. Run: pip install anthropic")

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            print("[LLM] WARNING: No OPENAI_API_KEY in .env")
            return
        try:
            import openai
            _client = openai.OpenAI(api_key=api_key)
            _provider = "openai"
            _model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
            print(f"[LLM] Using OpenAI ({_model_name})")
        except ImportError:
            print("[LLM] openai not installed. Run: pip install openai")

    else:
        print(f"[LLM] Unknown provider: '{provider}'. Use: gemini, anthropic, openai")


def is_available() -> bool:
    _init()
    return _client is not None


def call(system_prompt: str, user_prompt: str, max_tokens: int = 1024, retries: int = 2) -> str:
    _init()
    if _client is None:
        return ""

    for attempt in range(retries + 1):
        try:
            if _provider == "gemini":
                resp = http_requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{_model_name}:generateContent?key={_client}",
                    json={
                        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                        "generationConfig": {
                            "temperature": 0.3,
                            "maxOutputTokens": 8192,
                            "thinkingConfig": {"thinkingBudget": 0},
                        },
                    },
                    timeout=45,
                )
                resp.raise_for_status()
                parts = resp.json()["candidates"][0]["content"]["parts"]
                text_parts = [p["text"] for p in parts if not p.get("thought") and p.get("text")]
                return "\n".join(text_parts)

            elif _provider == "anthropic":
                response = _client.messages.create(
                    model=_model_name,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text

            elif _provider == "openai":
                response = _client.chat.completions.create(
                    model=_model_name,
                    max_tokens=max_tokens,
                    temperature=0.3,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                return response.choices[0].message.content

        except Exception as e:
            print(f"[LLM] {_provider} call failed (attempt {attempt + 1}/{retries + 1}): {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                return ""
    return ""


def parse_json(raw: str) -> dict | None:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```\w*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # Find the outermost JSON object (handles nested braces)
    depth = 0
    start = None
    for i, ch in enumerate(clean):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(clean[start:i+1])
                except json.JSONDecodeError:
                    start = None
    return None


# ---------------------------------------------------------------------------
# Hard-skip rules (no LLM cost)
# ---------------------------------------------------------------------------

CLEARANCE_PATTERNS = [
    r"must have active .* clearance",
    r"active (ts|secret|top secret) clearance required",
    r"requires? .* security clearance",
    r"security clearance (is )?required",
    r"must (hold|possess|maintain|obtain) .* clearance",
    r"(ts/sci|top secret|secret) clearance",
    r"eligible for .* clearance",
    r"public trust .* required",
]

CITIZENSHIP_PATTERNS = [
    r"(us|u\.s\.?) citizen(s|ship)? (only|required|is required)",
    r"must be (a |an )?(us|u\.s\.?|united states) citizen",
    r"(only |open to )?(us|u\.s\.?) citizens",
    r"requires? (us|u\.s\.?) citizenship",
    r"green card (holder|required|only)",
    r"(gc|green card) or (us|u\.s\.?) citizen",
    r"must (have|hold|possess) (a )?(green card|permanent residen)",
    r"no (visa )?sponsorship",
    r"cannot sponsor",
    r"will not (be )?sponsor",
    r"(does|do) not (offer|provide) (visa )?sponsor",
    r"unable to (offer|provide) (visa )?sponsor",
    r"not (able|willing) to sponsor",
    r"without (the )?need for .* sponsorship",
    r"(not |un)able to sponsor",
    r"sponsorship is not available",
    r"sponsorship not available",
    r"(this|the) position (does not|will not|cannot) (offer |provide )?sponsor",
    r"must be (legally )?authorized to work",
    r"authorized to work in the (us|u\.s\.?|united states)",
    r"work authorization.*(required|must|necessary)",
    r"permanent resident(s)? (only|required)",
    r"(us|u\.s\.?) persons? only",
    r"itar .* (us|u\.s\.?) person",
    r"(eeo|equal opportunity).*(authorized|eligible) to work",
]

SCAM_PATTERNS = [
    r"no (prior )?experience (is )?required.* comprehensive training",
    r"must be \d+ years of age or older",
    r"must have a valid .* bank account",
    r"provide .* social security number",
    r"reply with .?yes",
    r"microsoft teams account",
    r"multiple openings.*position.*filled.*consider you",
]

HARD_SKIP_TITLE_KEYWORDS = [
    "staff engineer", "principal engineer", "director", "vp of",
    "vice president", "engineering manager", "head of engineering",
    "distinguished engineer", "fellow",
]


DEFENSE_COMPANIES = {
    "anduril", "palantir", "lockheed martin", "raytheon", "northrop grumman",
    "general dynamics", "bae systems", "l3harris", "leidos", "booz allen",
    "saic", "caci", "mantech", "peraton", "shield ai", "skydio",
    "general atomics", "boeing defense", "rtx", "huntington ingalls",
}


def hard_skip_check(title: str, description: str, company: str = "") -> tuple[bool, str | None]:
    """
    Rule-based skip check. No LLM cost.
    Returns (should_skip, reason_or_None).
    """
    title_lower = title.lower()
    desc_lower = description.lower()
    company_lower = company.lower().strip()

    # Defense companies require US person / clearance
    if company_lower in DEFENSE_COMPANIES:
        return True, f"Defense company: {company} (requires US person)"

    for kw in HARD_SKIP_TITLE_KEYWORDS:
        if kw in title_lower:
            return True, f"Title seniority mismatch: '{kw}'"

    for pattern in CLEARANCE_PATTERNS:
        if re.search(pattern, desc_lower):
            return True, "Security clearance required"

    for pattern in CITIZENSHIP_PATTERNS:
        if re.search(pattern, desc_lower):
            return True, "Requires US citizenship/green card or won't sponsor"

    for pattern in SCAM_PATTERNS:
        if re.search(pattern, desc_lower):
            return True, f"Scam pattern detected"

    return False, None
