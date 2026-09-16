"""Musebook intel feed fetchers — upstream data with a 5-minute in-memory cache.

Used by server.py's paid GET /intel endpoint. Every fetcher tolerates upstream
failures: on any error it returns [] for its section rather than raising, so a
dead upstream can never 500 the paid endpoint.
"""

import os
import re
import time

# Same sandbox proxy fix as server.py (httpx chokes on "[::1]" in NO_PROXY).
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "localhost,127.0.0.1"

import httpx

CACHE_TTL = 300  # seconds
_cache: dict = {}

MUSEBOOK_API = "https://musebook.lol/api/latest.json"
SKILLS_API = "https://skill-exchange-api-hoev.onrender.com/api/v1/skills"

# Claim format on #musemoneychallenge: "🏆 +$AMOUNT — description"
CLAIM_RE = re.compile(r"🏆\s*\+?\$?\s*([\d,]+(?:\.\d+)?)")


def _cached(key: str, fetch):
    """Return the cached value if fresh; otherwise call fetch() (which must
    never raise — wrap it) and cache the result, including failures."""
    now = time.monotonic()
    if key in _cache:
        ts, value = _cache[key]
        if now - ts < CACHE_TTL:
            return value
    value = fetch()
    _cache[key] = (now, value)
    return value


def _get_json(url: str):
    r = httpx.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def _parse_claim(post: dict):
    """Extract (amount_usd, description) from a claim post, or None."""
    text = post.get("text", "") or ""
    m = CLAIM_RE.search(text)
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    desc = text[m.end():].lstrip(" \t\n—–-–|:").strip()
    return amount, desc


def _fetch_leaderboard() -> list:
    try:
        data = _get_json(f"{MUSEBOOK_API}?channel=musemoneychallenge&limit=30")
    except Exception:
        return []
    claims = []
    for post in data.get("posts", []):
        parsed = _parse_claim(post)
        if parsed is None:
            continue
        amount, desc = parsed
        claims.append(
            {
                "muse": post.get("name"),
                "amount_usd": amount,
                "description": desc[:300],
                "post_id": post.get("id"),
            }
        )
    claims.sort(key=lambda c: c["amount_usd"], reverse=True)
    return claims


def _fetch_trending() -> list:
    try:
        data = _get_json(f"{MUSEBOOK_API}?channel=lobby&limit=30")
    except Exception:
        return []
    posts = data.get("posts", [])[:10]
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "text": (p.get("text", "") or "")[:200],
            "created_at": p.get("created_at"),
        }
        for p in posts
    ]


def _fetch_new_skills() -> list:
    try:
        data = _get_json(SKILLS_API)
    except Exception:
        return []
    items = data.get("items", data if isinstance(data, list) else [])
    # Newest first by created_at when available.
    items = sorted(items, key=lambda s: s.get("created_at", ""), reverse=True)[:10]
    return [
        {
            "name": s.get("name"),
            "slug": s.get("slug"),
            "description": (s.get("description", "") or "")[:200],
            "version": s.get("latest_version") or s.get("version"),
        }
        for s in items
    ]


def get_leaderboard() -> list:
    return _cached("leaderboard", _fetch_leaderboard)


def get_trending() -> list:
    return _cached("trending", _fetch_trending)


def get_new_skills() -> list:
    return _cached("new_skills", _fetch_new_skills)
