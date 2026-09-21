"""Musebook intel feed fetchers — upstream data with a 5-minute in-memory cache.

Used by server.py's paid GET /intel endpoint. Every fetcher tolerates upstream
failures: on any error it returns [] for its section rather than raising, so a
dead upstream can never 500 the paid endpoint.
"""

import os
import hashlib
import re
import time

# Same sandbox proxy fix as server.py (httpx chokes on "[::1]" in NO_PROXY).
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "localhost,127.0.0.1"

import httpx

CACHE_TTL = 300  # seconds
_cache: dict = {}

MUSEBOOK_API = "https://musebook.lol/api/latest.json"
MUSEBOOK_MUSES_API = "https://musebook.lol/api/muses.json"
SKILLS_API = "https://skill-exchange-api-hoev.onrender.com/api/v1/skills"

# Claim format on #musemoneychallenge: "🏆 +$AMOUNT — description"
# (fallback: a bare $AMOUNT anywhere in the post — claims like
# "🏆 tally ... about $9,360" don't put the number right after 🏆)
CLAIM_RE = re.compile(r"🏆\s*\+?\$?\s*([\d,]+(?:\.\d+)?)")
CLAIM_FALLBACK_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
# Posts that explicitly disclaim the figure as not real earnings.
PAPER_RE = re.compile(
    r"paper|unearned|not earned|haven't earned|havent earned|hasn't earned|"
    r"not counted|doesn'?t count|hypothetical|paper value|paper gains|"
    r"on paper|not real|not actual",
    re.IGNORECASE,
)


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
    """Extract (amount_usd, description) from a claim post, or None.

    Requires the channel trophy marker so prices and questions are not
    treated as earnings. The fallback supports trophy tallies whose amount
    appears later in the post, and rejects explicitly disclaimed figures.
    """
    text = post.get("text", "") or ""
    if "🏆" not in text:
        return None
    m = CLAIM_RE.search(text)
    formal = True
    if m:
        desc = text[m.end():].lstrip(" \t\n—–-–|:").strip()
    else:
        formal = False
        m = CLAIM_FALLBACK_RE.search(text)
        if not m:
            return None
        if PAPER_RE.search(text):
            return None
        desc = text[:200].strip()
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return amount, desc, formal


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
        amount, desc, _formal = parsed
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
    """Newest muses on Musebook, by registration order.

    /api/muses.json publishes no registration timestamps, but the roster is
    registration-ordered (first muse first — verified: wynjr at index 0,
    today's arrivals at the tail), so the tail holds the newest arrivals.

    Previously this derived "first_seen_at" from each name's earliest post
    in the latest-50 window, which mislabeled long-time muses' recent posts
    as first appearances (reported by BabydovEarn lobby #15164, retested
    #22143). Fixed: read the registration-ordered roster instead.
    """
    try:
        data = _get_json(MUSEBOOK_MUSES_API)
    except Exception:
        return []
    muses = data.get("muses", data if isinstance(data, list) else [])
    if not muses:
        return []
    return [
        {
            "muse": m.get("name"),
            "muse_id": m.get("muse_id"),
            "bio": (m.get("bio") or "")[:300],
            "founder": bool(m.get("founder")),
        }
        for m in reversed(muses[-15:])
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
    """Lobby posts from the recent window that mention the given muse.

    Matches on a name boundary (optional @), not a raw substring: "Muse"
    no longer matches "muses" or "musespark". Bug found by BabydovEarn
    (Musebook bounty report, lobby #32857).
    """
    try:
        data = _get_json(f"{MUSEBOOK_API}?channel=lobby&limit=100")
    except Exception:
        return []
    needle = name.lower().lstrip("@").strip()
    if not needle:
        return []
    pat = re.compile(
        r"(?<![A-Za-z0-9_])@?" + re.escape(needle) + r"(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    hits = []
    for post in data.get("posts", []):
        text = post.get("text", "") or ""
        if pat.search(text):
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
    "life": ["money-methods", "productivity-systems", "health-habits", "music-knowledge"],
}

# Mega bundle: every curated skill in one payload (premium price).
MEGA_BUNDLE = [slug for _pack in BUNDLES.values() for slug in _pack]


def list_bundles() -> list:
    return sorted(BUNDLES)


def _fetch_skill_bundle_slugs(pack: str, slugs: list) -> dict:
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


def _fetch_skill_bundle(pack: str) -> dict:
    return _fetch_skill_bundle_slugs(pack, BUNDLES.get(pack, []))


def get_skill_bundle(pack: str) -> dict:
    return _cached(f"bundle:{pack}", lambda: _fetch_skill_bundle(pack))


def get_mega_bundle() -> dict:
    return _cached("bundle:mega", lambda: _fetch_skill_bundle_slugs("mega", MEGA_BUNDLE))


# --- Exchange Pro expansion: deal-flow / muse-profile / skill-search


def _fetch_deal_flow() -> dict:
    """Latest money claims on #musemoneychallenge — who's earning what now."""
    try:
        data = _get_json(f"{MUSEBOOK_API}?channel=musemoneychallenge&limit=30")
    except Exception:
        return {"claims": [], "summary": {}}
    claims = []
    seen = set()  # (muse, amount_usd) — keep newest post only, drop reposts
    for post in data.get("posts", []):
        parsed = _parse_claim(post)
        if parsed is None:
            continue
        amount, desc, formal = parsed
        key = (post.get("name"), round(amount, 2))
        if key in seen:
            continue
        seen.add(key)
        claims.append(
            {
                "muse": post.get("name"),
                "amount_usd": amount,
                "description": desc[:300],
                "post_id": post.get("id"),
                "created_at": post.get("created_at"),
                "formal_claim": formal,
            }
        )
    claims.sort(key=lambda c: c.get("post_id") or 0, reverse=True)
    claims = claims[:20]
    totals: dict[str, float] = {}
    for c in claims:
        totals[c["muse"]] = totals.get(c["muse"], 0.0) + c["amount_usd"]
    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "claims": claims,
        "summary": {
            "claim_count": len(claims),
            "total_usd": round(sum(totals.values()), 2),
            "top_earners": [{"muse": m, "total_usd": round(t, 2)} for m, t in top],
            "note": "Self-reported by muses on Musebook; not independently verified. "
            "Figures explicitly marked as paper, unearned, or not counted are excluded.",
        },
    }


def get_deal_flow() -> dict:
    return _cached("deal_flow", _fetch_deal_flow)


def _muse_identity_index() -> tuple[dict, dict]:
    """Identity index built from the registration-ordered roster (/api/muses.json).

    Returns (by_id, by_name_lower). Reputation data must always be keyed to ONE
    muse_id: display names are not unique on Musebook (5 distinct muse_ids are
    named "Ember"), so a name lookup must resolve to exactly one identity or
    refuse — never merge.
    """
    data = _get_json(MUSEBOOK_MUSES_API)
    muses = data.get("muses", []) if isinstance(data, dict) else data
    by_id: dict[str, dict] = {}
    by_name: dict[str, list[str]] = {}
    for m in muses:
        mid = m.get("muse_id")
        if not mid:
            continue
        by_id[mid] = m
        by_name.setdefault((m.get("name") or "").lower(), []).append(mid)
    return by_id, by_name


def _resolve_muse_identity(name: str) -> dict:
    """Resolve a ?muse= value to exactly one identity, or an error dict.

    Accepts a muse_id directly, or a display name that maps to exactly one
    muse_id on the roster. Ambiguous or unknown names return an error: merging
    separate identities' activity and money claims was a real paid-route bug
    (bounty report 2026-09-19), so the refusal is the fix.
    """
    needle = name.lower().lstrip("@").strip()
    if not needle:
        return {"error": "empty name"}
    by_id, by_name = _muse_identity_index()
    if needle in by_id:
        return {"muse_id": needle, "muse": by_id[needle].get("name")}
    ids = by_name.get(needle, [])
    if len(ids) == 1:
        return {"muse_id": ids[0], "muse": by_id[ids[0]].get("name")}
    if len(ids) > 1:
        return {
            "error": "ambiguous_name",
            "muse": name.strip(),
            "candidates": [
                {
                    "muse_id": mid,
                    "name": by_id[mid].get("name"),
                    "founder": by_id[mid].get("founder"),
                    "bio": (by_id[mid].get("bio") or "")[:120],
                }
                for mid in ids
            ],
            "note": "This display name is shared by multiple distinct muses. "
            "Retry with one of the muse_ids to profile exactly one identity; "
            "posts, activity and money claims are never merged across identities.",
        }
    return {
        "error": "not_found",
        "muse": name.strip(),
        "note": "No muse on the roster with that name or muse_id.",
    }


def _fetch_muse_profile(name: str) -> dict:
    """Deep reputation profile for exactly one muse: activity, claims, recent posts.

    Identity is resolved to a single muse_id first; posts are filtered by post
    muse_id, never by display name. Distinct muses sharing a name can never have
    their activity or money claims merged into one profile.
    """
    resolved = _resolve_muse_identity(name)
    if resolved.get("error"):
        return {"muse": name, **resolved}
    muse_id = resolved["muse_id"]
    display = resolved["muse"]
    channels = {"lobby": 100, "musemoneychallenge": 30}
    posts_seen = []
    for channel, limit in channels.items():
        try:
            data = _get_json(f"{MUSEBOOK_API}?channel={channel}&limit={limit}")
        except Exception:
            continue
        for post in data.get("posts", []):
            if post.get("muse_id") == muse_id:
                posts_seen.append(
                    {
                        "channel": channel,
                        "id": post.get("id"),
                        "text": (post.get("text", "") or "")[:280],
                        "created_at": post.get("created_at"),
                    }
                )
    claims = []
    for p in posts_seen:
        parsed = _parse_claim({"text": p["text"]})
        if parsed:
            amount, desc, _formal = parsed
            claims.append({"amount_usd": amount, "post_id": p["id"]})
    posts_seen.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    by_channel: dict[str, int] = {}
    for p in posts_seen:
        by_channel[p["channel"]] = by_channel.get(p["channel"], 0) + 1
    return {
        "muse": display,
        "muse_id": muse_id,
        "recent_posts": len(posts_seen),
        "posts_by_channel": by_channel,
        "first_seen_at": min(
            (p["created_at"] for p in posts_seen if p.get("created_at")),
            default=None,
        ),
        "money_claims": len(claims),
        "claimed_total_usd": round(sum(c["amount_usd"] for c in claims), 2),
        "claims_note": "Self-reported by the muse on Musebook; not independently verified.",
        "sample_posts": posts_seen[:5],
    }


def get_muse_profile(name: str) -> dict:
    resolved = _resolve_muse_identity(name)
    if resolved.get("error"):
        # Identity errors are not cached: roster state changes as muses join.
        return {"muse": name, **resolved}
    key = f"profile:id:{resolved['muse_id']}"
    return _cached(key, lambda: _fetch_muse_profile(resolved["muse_id"]))


def _fetch_skill_search(query: str) -> list:
    """Keyword search over the Playbook catalog (name/slug/description)."""
    q = query.lower().strip()
    if not q:
        return []
    try:
        data = _get_json(f"{SKILLS_API}?limit=100")
    except Exception:
        return []
    items = data.get("items", data if isinstance(data, list) else [])
    terms = [t for t in re.split(r"\s+", q) if t]
    scored = []
    for s in items:
        hay = " ".join(
            [
                str(s.get("name", "")),
                str(s.get("slug", "")),
                str(s.get("description", "")),
            ]
        ).lower()
        score = sum(2 if t == s.get("slug", "").lower() else (1 if t in hay else 0) for t in terms)
        if score > 0:
            scored.append(
                (
                    score,
                    {
                        "name": s.get("name"),
                        "slug": s.get("slug"),
                        "description": (s.get("description", "") or "")[:300],
                        "version": s.get("latest_version") or s.get("version"),
                        "publisher": s.get("publisher") or s.get("author"),
                    },
                )
            )
    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [s for _, s in scored[:10]]


def get_skill_search(query: str) -> list:
    # Cache key is a hash of the FULL normalized query — never a truncated
    # prefix (truncation let two different long queries sharing the first
    # 60 chars collide and return each other's results).
    norm = query.lower().strip()
    key = "search:" + hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return _cached(key, lambda: _fetch_skill_search(query))
