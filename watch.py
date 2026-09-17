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


def _ip_rejection(ip_str: str) -> str | None:
    """Return a rejection reason if the IP is not a public routable address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return "unparseable IP address"
    if ip.is_loopback:
        return "loopback addresses are not allowed"
    if ip.is_link_local:
        return "link-local addresses are not allowed"
    if ip.is_multicast:
        return "multicast addresses are not allowed"
    if ip.is_unspecified:
        return "unspecified (0.0.0.0) addresses are not allowed"
    if ip.is_private:
        return "private addresses are not allowed"
    if ip.is_reserved:
        return "reserved addresses are not allowed"
    if not ip.is_global:
        return "non-routable addresses are not allowed"
    return None


def validate_url(url: str) -> str | None:
    """Full SSRF validation. Returns an error string, or None if fetchable.

    Safe to call at quote time (before any 402 payment challenge) and again
    immediately before fetching — the second call closes the DNS-rebinding
    window between validation and the actual connection.
    """
    try:
        parts = urlparse(url)
    except Exception:
        return "unparseable URL"
    if parts.scheme not in ("http", "https"):
        return "only http(s) URLs are supported"
    if parts.username or parts.password:
        return "credentials in URL are not allowed"
    host = parts.hostname
    if not host:
        return "URL has no hostname"
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except Exception:
        return "hostname does not resolve"
    if not infos:
        return "hostname does not resolve"
    for info in infos:
        reason = _ip_rejection(info[4][0])
        if reason:
            return reason
    return None


# Backwards-compatible alias (older call sites).
def _validate_url(url: str) -> str | None:
    return validate_url(url)


def _extract_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


_MAX_REDIRECTS = 5


def _fetch_validated(url: str):
    """Fetch with manual redirect-following: every redirect target is
    SSRF-validated before following, so a 3xx can't bounce the fetcher
    onto an internal address."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        err = validate_url(current)
        if err:
            return None, {"url": url, "error": f"redirect target rejected: {err}"}
        try:
            r = httpx.get(
                current,
                timeout=20,
                follow_redirects=False,
                headers={"User-Agent": "x402-change-monitor/1.0"},
            )
        except Exception as e:
            return None, {"url": url, "error": f"fetch failed: {type(e).__name__}"}
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("location")
            if not loc:
                return None, {"url": url, "error": "redirect with no location"}
            # Resolve relative redirects against the current URL, then the
            # loop-top validate_url() re-checks the absolute target.
            from urllib.parse import urljoin

            current = urljoin(current, loc)
            continue
        try:
            r.raise_for_status()
        except Exception as e:
            return None, {"url": url, "error": f"fetch failed: {type(e).__name__}"}
        return r, None
    return None, {"url": url, "error": "too many redirects"}


def check_url(url: str) -> dict:
    err = validate_url(url)
    if err:
        return {"url": url, "error": err}

    now = time.time()
    if url in _fetch_cache and now - _fetch_cache[url][0] < CACHE_TTL:
        _, result = _fetch_cache[url]
        return result

    # Re-validate immediately before fetching: closes the DNS-rebinding
    # window between the quote-time check and the actual connection.
    # (Full IP pinning — dialing the vetted IP with a Host header — is the
    # remaining hardening step if this ever needs to be airtight.)
    err = validate_url(url)
    if err:
        return {"url": url, "error": err}

    r, fetch_err = _fetch_validated(url)
    if fetch_err:
        _fetch_cache[url] = (now, fetch_err)
        return fetch_err

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
