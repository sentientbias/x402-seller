"""Playbook / Exchange Pro SSO client (2026-09-21).

MuseFM (https://musefm.lol) is the identity provider. This module implements
the client side of the redirect-based SSO flow (see
~/workspace/global-login/SSO_PLAN.md):

  GET /auth/login    -> PKCE pair + state, signed state cookie, redirect to
                        the provider's /auth/authorize
  GET /auth/callback -> verify state, exchange code for ID token server-side,
                        verify the Ed25519 signature + claims, mint a local
                        session cookie (pb_session)
  GET /auth/logout   -> clear the local session cookie

Login is OPTIONAL: browsing the Playbook and buying over x402 work exactly
as before, with or without a session. The x402 payment middleware and the
Pro-pass verification are completely untouched by this module.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

PROVIDER = "https://musefm.lol"
CLIENT_ID = "playbook"
REDIRECT_URI = "https://x402-seller-a5et.onrender.com/auth/callback"

STATE_COOKIE = "sso_state"
STATE_TTL_SEC = 10 * 60
SESSION_COOKIE = "pb_session"
SESSION_TTL_SEC = 30 * 24 * 3600

# Simple in-memory throttle on /auth/callback (blunts brute force).
# {ip: [monotonic timestamps]} — best-effort, resets on process restart.
_THROTTLE: dict = {}
_THROTTLE_MAX = 20
_THROTTLE_WINDOW = 60.0


def _session_secret() -> str:
    return os.environ.get("SESSION_SECRET", "").strip()


_serializer = None


def _ser():
    """itsdangerous serializer, or None when SESSION_SECRET is unset."""
    global _serializer
    if _serializer is None and _session_secret():
        from itsdangerous import URLSafeTimedSerializer

        _serializer = URLSafeTimedSerializer(_session_secret(), salt="pb-sso-v1")
    return _serializer


def sso_configured() -> bool:
    return bool(_session_secret())


def throttled(ip: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _THROTTLE.get(ip, []) if now - t < _THROTTLE_WINDOW]
    _THROTTLE[ip] = hits
    if len(hits) >= _THROTTLE_MAX:
        return True
    hits.append(now)
    return False


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def begin_login() -> tuple:
    """Build the provider authorize URL + signed state-cookie value."""
    verifier = secrets.token_urlsafe(64)
    challenge = _b64u(hashlib.sha256(verifier.encode("ascii")).digest())
    state = secrets.token_urlsafe(32)
    ser = _ser()
    cookie_val = ser.dumps({"state": state, "verifier": verifier})
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    url = PROVIDER + "/auth/authorize?" + urllib.parse.urlencode(params)
    return url, cookie_val


def read_state_cookie(value: str) -> dict | None:
    ser = _ser()
    if not ser or not value:
        return None
    try:
        data = ser.loads(value, max_age=STATE_TTL_SEC)
    except Exception:
        return None
    if not isinstance(data, dict) or "state" not in data or "verifier" not in data:
        return None
    return data


# ---------------------------------------------------------------- provider I/O
# Separated into small functions so tests can stub the provider boundary
# while the real signature/claims verification path still runs.

_pubkey_cache: tuple = (0.0, None)  # (fetched_at, raw 32-byte key)


def _http_get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "playbook-sso/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "playbook-sso/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_provider_pubkey() -> bytes:
    """Provider Ed25519 public key (32 raw bytes), cached for 1 hour."""
    global _pubkey_cache
    now = time.monotonic()
    if _pubkey_cache[1] is not None and now - _pubkey_cache[0] < 3600:
        return _pubkey_cache[1]
    doc = _http_get_json(PROVIDER + "/auth/pubkey")
    if not doc.get("ok") or doc.get("scheme") != "ed25519":
        raise ValueError("bad pubkey document from provider")
    raw = _b64u_decode(doc["public_key"])
    if len(raw) != 32:
        raise ValueError("bad ed25519 key length from provider")
    _pubkey_cache = (now, raw)
    return raw


def post_token_request(code: str, verifier: str) -> dict:
    return _http_post_json(PROVIDER + "/auth/token", {
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT_URI,
    })


def verify_id_token(id_token: str) -> dict:
    """Verify signature + claims. Returns the payload claims or raises."""
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey

    parts = (id_token or "").split(".")
    if len(parts) != 3:
        raise ValueError("malformed id_token")
    header_b, payload_b, sig_b = parts
    pubkey = fetch_provider_pubkey()
    try:
        # PyNaCl verify() takes the signed message: signature + message.
        VerifyKey(pubkey).verify(
            _b64u_decode(sig_b) + (header_b + "." + payload_b).encode("ascii"))
    except BadSignatureError as e:
        raise ValueError("bad id_token signature") from e
    try:
        claims = json.loads(_b64u_decode(payload_b).decode("utf-8"))
    except Exception as e:
        raise ValueError("bad id_token payload") from e
    if claims.get("iss") != PROVIDER:
        raise ValueError("bad iss")
    if claims.get("aud") != CLIENT_ID:
        raise ValueError("bad aud")
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        raise ValueError("id_token expired")
    if not claims.get("sub") or not isinstance(claims.get("sub"), str):
        raise ValueError("bad sub")
    return claims


def exchange_code(code: str, verifier: str) -> dict:
    """Redeem an auth code; returns verified {fm_id, handle}."""
    doc = post_token_request(code, verifier)
    if not doc.get("ok") or not doc.get("id_token"):
        raise ValueError("token exchange failed: %s" % doc)
    claims = verify_id_token(doc["id_token"])
    return {"fm_id": claims["sub"], "handle": claims.get("handle", "")}


# ------------------------------------------------------------------ sessions


def make_session(fm_id: str, handle: str) -> str:
    ser = _ser()
    return ser.dumps({"fm_id": fm_id, "handle": handle, "iat": int(time.time())})


def read_session(value: str) -> dict | None:
    ser = _ser()
    if not ser or not value:
        return None
    try:
        data = ser.loads(value, max_age=SESSION_TTL_SEC)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("fm_id"):
        return None
    return data


def current_session(request) -> dict | None:
    return read_session(request.cookies.get(SESSION_COOKIE, ""))
