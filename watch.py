"""Website change monitor — paid change detection for any public URL.

Each paid GET /check?url=... fetches the page, extracts its text, hashes it,
and compares against the last snapshot. Returns whether the page changed
since the previous check. $0.01 per check.

Snapshots live in a small JSON file (snapshots.json next to this module).
Upstream failures never raise — they return an error payload instead.
SSRF guard: only http/https, and hostnames resolving to private/loopback
addresses are refused.
"""

import hashlib
import ipaddress
import json
import os
import re
import socket
import time
from urllib.parse import urlparse

# Same sandbox proxy fix as server.py (httpx chokes on "[::1]" in NO_PROXY).
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "localhost,127.0.0.1"

import httpx

SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), "snapshots.json")
CACHE_TTL = 300  # don't re-fetch the same URL more often than this
_fetch_cache: dict = {}

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _load_snapshots() -> dict:
    try:
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_snapshots(snaps: dict):
    try:
        tmp = SNAPSHOT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(snaps, f)
        os.replace(tmp, SNAPSHOT_FILE)
    except Exception:
        pass


def _validate_url(url: str) -> str | None:
    """Return an error string, or None if the URL is fetchable."""
    try:
        parts = urlparse(url)
    except Exception:
        return "unparseable URL"
    if parts.scheme not in ("http", "https"):
        return "only http(s) URLs are supported"
    if not parts.hostname:
        return "URL has no hostname"
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except Exception:
        return "hostname does not resolve"
    for info in infos:
        ip = info[4][0]
        try:
            if ipaddress.ip_address(ip).is_private:
                return "private/loopback addresses are not allowed"
        except ValueError:
            return "unresolvable address"
    return None


def _extract_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def check_url(url: str) -> dict:
    err = _validate_url(url)
    if err:
        return {"url": url, "error": err}

    now = time.time()
    if url in _fetch_cache and now - _fetch_cache[url][0] < CACHE_TTL:
        _, result = _fetch_cache[url]
        return result

    try:
        r = httpx.get(
            url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "x402-change-monitor/1.0"},
        )
        r.raise_for_status()
    except Exception as e:
        result = {"url": url, "error": f"fetch failed: {type(e).__name__}"}
        _fetch_cache[url] = (now, result)
        return result

    text = _extract_text(r.text)
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
    excerpt = text[:500]

    snaps = _load_snapshots()
    prev = snaps.get(url)
    first_seen = prev is None
    changed = (not first_seen) and prev.get("sha256") != digest

    snaps[url] = {
        "sha256": digest,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "excerpt": excerpt,
    }
    _save_snapshots(snaps)

    result = {
        "url": url,
        "changed": changed,
        "first_seen": first_seen,
        "fetched_at": snaps[url]["fetched_at"],
        "sha256": digest,
        "excerpt": excerpt,
    }
    _fetch_cache[url] = (now, result)
    return result
