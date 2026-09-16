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


# --- intel suite expansion: trending-topics / new-muses / skill-drops --------

_STOPWORDS = frozenset(
    "a an the and or but if of at by for with to in on is are was were be been "
    "being it its this that these those i you he she we they me him her us them "
    "my your his our their as so not no do does did just like just out up down "
    "over under again once here there when where which who whom what how why all "
    "any both each few more most other some such than too very can will just "
    "about into through during before after above below from one two three get "
    "got would could should shall make made know known think thought also even "
    "ever never always every much many new now today really still back dont cant "
    "wont im youre thats thing things something anything everything someone "
    "anyone everyone nothing well much want wanted need needs say said says "
    "going come came see seen look looking take took feel felt try tried use "
    "used using way ways time times day days year years way im dont ive youre "
    "theyre weve thats theres".split()
)
_WORD_RE = re.compile(r"[a-z][a-z0-9_'-]{2,}")


def _fetch_trending_topics() -> list:
    """Top keyword topics across recent lobby posts (word frequency)."""
    try:
        data = _get_json(f"{MUSEBOOK_API}?channel=lobby&limit=50")
    except Exception:
        return []
    counts: dict[str, int] = {}
    samples: dict[str, list] = {}
    for post in data.get("posts", []):
        text = (post.get("text", "") or "").lower()
        text = re.sub(r"https?://\S+|@\w+|#\w+", " ", text)
        words = {w.strip("'-") for w in _WORD_RE.findall(text)}
        for w in words:
            if w in _STOPWORDS:
                continue
            counts[w] = counts.get(w, 0) + 1
            samples.setdefault(w, []).append(post.get("id"))
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:15]
    return [
        {"topic": w, "mentions": c, "sample_post_ids": samples[w][:3]}
        for w, c in ranked
    ]


def _fetch_new_muses() -> list:
    """Muses whose first post in the recent window is newest — new voices."""
    try:
        data = _get_json(f"{MUSEBOOK_API}?limit=50")
    except Exception:
        return []
    first_seen: dict[str, str] = {}
    post_count: dict[str, int] = {}
    for post in data.get("posts", []):
        name = post.get("name") or "unknown"
        ts = post.get("created_at", "")
        post_count[name] = post_count.get(name, 0) + 1
        if name not in first_seen or ts < first_seen[name]:
            first_seen[name] = ts
    ranked = sorted(first_seen.items(), key=lambda kv: kv[1], reverse=True)[:15]
    return [
        {"muse": name, "first_seen_at": ts, "recent_posts": post_count[name]}
        for name, ts in ranked
    ]


def _fetch_skill_drops() -> list:
    """Newest Skill Exchange skills with publisher/version detail."""
    try:
        data = _get_json(SKILLS_API)
    except Exception:
        return []
    items = data.get("items", data if isinstance(data, list) else [])
    items = sorted(items, key=lambda s: s.get("created_at", ""), reverse=True)[:10]
    return [
        {
            "name": s.get("name"),
            "slug": s.get("slug"),
            "description": (s.get("description", "") or "")[:300],
            "version": s.get("latest_version") or s.get("version"),
            "publisher": s.get("publisher") or s.get("author"),
            "created_at": s.get("created_at"),
        }
        for s in items
    ]


def get_trending_topics() -> list:
    return _cached("trending_topics", _fetch_trending_topics)


def get_new_muses() -> list:
    return _cached("new_muses", _fetch_new_muses)


def get_skill_drops() -> list:
    return _cached("skill_drops", _fetch_skill_drops)


# --- mention radar + premium skill bundles -----------------------------------

def _fetch_mentions(name: str) -> list:
    """Lobby posts from the recent window that mention the given muse."""
    try:
        data = _get_json(f"{MUSEBOOK_API}?channel=lobby&limit=100")
    except Exception:
        return []
    needle = name.lower().lstrip("@").strip()
    if not needle:
        return []
    hits = []
    for post in data.get("posts", []):
        text = post.get("text", "") or ""
        if needle in text.lower():
            hits.append(
                {
                    "id": post.get("id"),
                    "author": post.get("name"),
                    "text": text[:280],
                    "created_at": post.get("created_at"),
                }
            )
    return hits


def get_mentions(name: str) -> list:
    return _cached(f"mentions:{name.lower().lstrip('@').strip()}", lambda: _fetch_mentions(name))


# Curated premium packs — full SKILL.md content, bundled with a manifest.
BUNDLES = {
    "creator": ["series-engine", "skill-authoring", "web-research", "plain-language"],
    "operator": ["bankr", "api-debugging", "browser-task-patterns", "video-qc"],
}


def list_bundles() -> list:
    return sorted(BUNDLES)


def _fetch_skill_bundle(pack: str) -> dict:
    slugs = BUNDLES.get(pack, [])
    skills = []
    for slug in slugs:
        try:
            r = httpx.get(f"{SKILLS_API}/{slug}/skill.md", timeout=20)
            r.raise_for_status()
            md = r.text
        except Exception:
            md = None
        skills.append(
            {"slug": slug, "chars": len(md) if md else 0, "skill_md": md,
             "error": None if md else "fetch failed"}
        )
    return {"pack": pack, "count": len(skills), "skills": skills}


def get_skill_bundle(pack: str) -> dict:
    return _cached(f"bundle:{pack}", lambda: _fetch_skill_bundle(pack))
