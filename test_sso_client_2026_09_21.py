#!/usr/bin/env python3
"""Playbook / Exchange Pro SSO client tests (2026-09-21).

Covers the client side of MuseFM global login:
  1. Landing + network pages render with orb + sign-in (no login needed)
  2. /auth/login redirects to the provider with PKCE S256 + state, sets a
     signed HttpOnly state cookie
  3. Happy path: callback verifies state, exchanges the code, verifies the
     REAL Ed25519 ID-token path against a stubbed provider key, mints a
     local pb_session, nav shows the handle
  4. State mismatch / missing state cookie -> 400
  5. Tampered ID token / wrong aud / expired token -> 400
  6. /auth/logout clears the session cookie
  7. Payment + Pro-pass flows unchanged without login: /report 402s
     unpaid, garbage X-Pro-Pass still 402s (falls through to payment)
  8. /auth/login without SESSION_SECRET -> clean 500, site still serves

The provider boundary (fetch_provider_pubkey, post_token_request) is
stubbed with a locally generated Ed25519 keypair; the signature and
claims verification code under test is the real one.

Run:  python3 test_sso_client_2026_09_21.py
"""
import base64
import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# SESSION_SECRET must be set before server import (sso reads it lazily,
# but the unconfigured test needs a clean slate first).
os.environ["SESSION_SECRET"] = "test-secret-not-real-" + "x" * 32

# --- x402 SDK stub -----------------------------------------------------------
# The x402 SDK is not installed in this sandbox (Render installs it from
# requirements.txt). Stub the modules server.py imports. The stand-in
# PaymentMiddlewareASGI is faithful to the ONE property these tests need:
# it 402s exactly the routes listed in the paid RouteConfig dict when no
# x-payment header is present — the same gating rule the real middleware
# applies before any payment verification.
import types as _types  # noqa: E402

_x402 = _types.ModuleType("x402")
_x402_http = _types.ModuleType("x402.http")
_x402_mid = _types.ModuleType("x402.http.middleware")
_x402_mid_fastapi = _types.ModuleType("x402.http.middleware.fastapi")
_x402_types = _types.ModuleType("x402.http.types")
_x402_mech = _types.ModuleType("x402.mechanisms")
_x402_mech_evm = _types.ModuleType("x402.mechanisms.evm")
_x402_mech_exact = _types.ModuleType("x402.mechanisms.evm.exact")
_x402_server = _types.ModuleType("x402.server")
_x402_ext = _types.ModuleType("x402.extensions")
_x402_bazaar = _types.ModuleType("x402.extensions.bazaar")
_x402_rs = _types.ModuleType("x402.extensions.bazaar.resource_service")


class _FacilitatorConfig:
    def __init__(self, *a, **k):
        pass


class _HTTPFacilitatorClient:
    def __init__(self, *a, **k):
        pass


class _PaymentOption:
    def __init__(self, *a, **k):
        pass


class _RouteConfig:
    def __init__(self, *a, **k):
        pass


class _ExactEvmServerScheme:
    pass


class _x402ResourceServer:
    def __init__(self, *a, **k):
        pass

    def register(self, *a, **k):
        pass


class _PaymentMiddlewareASGI:
    """Stand-in: 402 iff the route is in the paid set and unpaid."""

    def __init__(self, app, routes, server):
        self.app = app
        self.routes = routes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            key = "%s %s" % (scope.get("method", "GET"),
                             scope.get("path", ""))
            headers = dict(scope.get("headers", []))
            if key in self.routes and b"x-payment" not in headers:
                from starlette.responses import JSONResponse as _JR
                resp = _JR({"detail": "payment required"}, status_code=402)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


class _OutputConfig:
    def __init__(self, *a, **k):
        pass


def _declare_discovery_extension(*a, **k):
    return {}


_x402_http.FacilitatorConfig = _FacilitatorConfig
_x402_http.HTTPFacilitatorClient = _HTTPFacilitatorClient
_x402_http.PaymentOption = _PaymentOption
_x402_mid_fastapi.PaymentMiddlewareASGI = _PaymentMiddlewareASGI
_x402_types.RouteConfig = _RouteConfig
_x402_mech_exact.ExactEvmServerScheme = _ExactEvmServerScheme
_x402_server.x402ResourceServer = _x402ResourceServer
_x402_rs.OutputConfig = _OutputConfig
_x402_rs.declare_discovery_extension = _declare_discovery_extension

sys.modules.update({
    "x402": _x402,
    "x402.http": _x402_http,
    "x402.http.middleware": _x402_mid,
    "x402.http.middleware.fastapi": _x402_mid_fastapi,
    "x402.http.types": _x402_types,
    "x402.mechanisms": _x402_mech,
    "x402.mechanisms.evm": _x402_mech_evm,
    "x402.mechanisms.evm.exact": _x402_mech_exact,
    "x402.server": _x402_server,
    "x402.extensions": _x402_ext,
    "x402.extensions.bazaar": _x402_bazaar,
    "x402.extensions.bazaar.resource_service": _x402_rs,
})
# -----------------------------------------------------------------------------

from nacl.signing import SigningKey  # noqa: E402

import sso as ssomod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import server as servermod  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name +
          (f" -- {detail}" if detail and not cond else ""))


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


STUB_SIGNING = SigningKey.generate()
STUB_PUBKEY = STUB_SIGNING.verify_key.encode()


def stub_id_token(aud="playbook", exp_offset=600, key=STUB_SIGNING,
                  sub="fm_test123", handle="ssohuman"):
    now = int(time.time())
    h = b64u(json.dumps({"alg": "EdDSA", "typ": "JWT", "kid": "sso-v1"},
                        separators=(",", ":")).encode())
    p = b64u(json.dumps({"iss": "https://musefm.lol", "aud": aud,
                         "sub": sub, "handle": handle,
                         "iat": now, "exp": now + exp_offset},
                        separators=(",", ":"), sort_keys=True).encode())
    sig = b64u(key.sign((h + "." + p).encode("ascii")).signature)
    return h + "." + p + "." + sig


# Stub the provider boundary; keep the real verify path.
ssomod.fetch_provider_pubkey = lambda: STUB_PUBKEY  # noqa: E731
ssomod.post_token_request = lambda code, verifier: {  # noqa: E731
    "ok": True, "id_token": stub_id_token(),
    "fm_id": "fm_test123", "handle": "ssohuman",
    "expires_in": 600,
}

client = TestClient(servermod.app, raise_server_exceptions=False)
ssomod._THROTTLE.clear()


def login_flow():
    """Run /auth/login, return (state_cookie_value, state)."""
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 302, r.status_code
    loc = r.headers["location"]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    state_cookie = r.cookies.get(ssomod.STATE_COOKIE)
    assert state_cookie, "no sso_state cookie"
    return state_cookie, q


def test_unconfigured():
    # SESSION_SECRET unset -> clean 500, site still serves.
    old = os.environ.pop("SESSION_SECRET", None)
    ssomod._serializer = None
    try:
        r = client.get("/auth/login", follow_redirects=False)
        check("unconfigured /auth/login -> 500", r.status_code == 500,
              f"got {r.status_code}")
        r = client.get("/")
        check("site still serves without SESSION_SECRET",
              r.status_code == 200)
    finally:
        if old:
            os.environ["SESSION_SECRET"] = old
        ssomod._serializer = None


def main():
    test_unconfigured()
    ssomod._THROTTLE.clear()

    # 1. landing renders, no login needed
    r = client.get("/")
    body = r.text
    check("GET / -> 200", r.status_code == 200, f"got {r.status_code}")
    check("landing has sign-in link", 'href="/auth/login">Sign in with MuseFM</a>' in body)
    check("landing includes orb script",
          '<script src="/static/js/muse-orb.js" defer></script>' in body)
    check("landing has orb anchor", "data-muse-orb-anchor" in body)
    check("orb js is served", client.get("/static/js/muse-orb.js").status_code == 200)

    r = client.get("/network")
    check("GET /network -> 200 with orb + sign-in",
          r.status_code == 200 and "muse-orb.js" in r.text
          and "/auth/login" in r.text, f"got {r.status_code}")

    # 2. /auth/login
    state_cookie, q = login_flow()
    loc_q = q
    check("login redirects to provider authorize",
          True)  # location checked below
    r = client.get("/auth/login", follow_redirects=False)
    loc = r.headers["location"]
    check("authorize URL is the provider",
          loc.startswith("https://musefm.lol/auth/authorize?"), loc[:80])
    qq = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    check("client_id=playbook", qq.get("client_id") == ["playbook"])
    check("exact registered redirect_uri",
          qq.get("redirect_uri") == [ssomod.REDIRECT_URI])
    check("PKCE S256 challenge present",
          qq.get("code_challenge_method") == ["S256"]
          and 43 <= len(qq["code_challenge"][0]) <= 128)
    check("state present", bool(qq.get("state", [""])[0]))
    set_cookie = r.headers.get("set-cookie", "")
    check("state cookie is HttpOnly", "httponly" in set_cookie.lower(),
          set_cookie[:120])
    check("state cookie is SameSite=Lax", "samesite=lax" in set_cookie.lower())

    # 3. happy path
    state_cookie, qq = login_flow()
    state = qq["state"][0]
    r = client.get("/auth/callback",
                   params={"code": "stub-code", "state": state},
                   cookies={ssomod.STATE_COOKIE: state_cookie},
                   follow_redirects=False)
    check("callback happy path -> 302 /",
          r.status_code == 302 and r.headers["location"] == "/",
          f"got {r.status_code} {r.text[:120]}")
    sess_cookie = r.cookies.get(ssomod.SESSION_COOKIE)
    check("pb_session cookie minted", bool(sess_cookie))
    set_cookie = r.headers.get("set-cookie", "")
    check("session cookie is HttpOnly+Secure+Lax",
          "httponly" in set_cookie.lower()
          and "secure" in set_cookie.lower()
          and "samesite=lax" in set_cookie.lower(),
          set_cookie[:160])

    # nav shows the handle when logged in
    r = client.get("/", cookies={ssomod.SESSION_COOKIE: sess_cookie})
    check("nav shows handle + sign-out when logged in",
          "@ssohuman · Sign out" in r.text)

    # tampered session cookie -> treated as logged out
    r = client.get("/", cookies={ssomod.SESSION_COOKIE: sess_cookie + "x"})
    check("tampered session cookie -> logged-out nav",
          'href="/auth/login">Sign in with MuseFM</a>' in r.text)

    # 4. state mismatch / missing
    state_cookie, qq = login_flow()
    r = client.get("/auth/callback",
                   params={"code": "stub-code", "state": "wrong-state"},
                   cookies={ssomod.STATE_COOKIE: state_cookie},
                   follow_redirects=False)
    check("state mismatch -> 400", r.status_code == 400,
          f"got {r.status_code}")
    state_cookie, qq = login_flow()
    r = client.get("/auth/callback",
                   params={"code": "stub-code", "state": qq["state"][0]},
                   follow_redirects=False)  # no cookie at all
    check("missing state cookie -> 400", r.status_code == 400,
          f"got {r.status_code}")
    # consent denied at provider
    state_cookie, qq = login_flow()
    r = client.get("/auth/callback",
                   params={"error": "access_denied", "state": qq["state"][0]},
                   cookies={ssomod.STATE_COOKIE: state_cookie},
                   follow_redirects=False)
    check("provider deny -> 400 with message",
          r.status_code == 400 and "not approved" in r.text.lower(),
          f"got {r.status_code}")

    # 5. bad ID tokens
    def callback_with_token(tok):
        ssomod.post_token_request = lambda code, verifier: {  # noqa: E731
            "ok": True, "id_token": tok, "fm_id": "fm_x", "handle": "x"}
        sc, qq2 = login_flow()
        try:
            return client.get("/auth/callback",
                              params={"code": "c", "state": qq2["state"][0]},
                              cookies={ssomod.STATE_COOKIE: sc},
                              follow_redirects=False)
        finally:
            ssomod.post_token_request = lambda code, verifier: {  # noqa: E731
                "ok": True, "id_token": stub_id_token(),
                "fm_id": "fm_test123", "handle": "ssohuman"}

    r = callback_with_token(stub_id_token(key=SigningKey.generate()))
    check("token signed by unknown key -> 400", r.status_code == 400,
          f"got {r.status_code}")
    r = callback_with_token(stub_id_token(aud="arena"))
    check("wrong aud -> 400", r.status_code == 400, f"got {r.status_code}")
    r = callback_with_token(stub_id_token(exp_offset=-10))
    check("expired token -> 400", r.status_code == 400,
          f"got {r.status_code}")
    r = callback_with_token("not.a.jwt")
    check("malformed token -> 400", r.status_code == 400,
          f"got {r.status_code}")

    # 6. logout clears the cookie
    r = client.get("/auth/logout",
                   cookies={ssomod.SESSION_COOKIE: sess_cookie},
                   follow_redirects=False)
    sc = r.headers.get("set-cookie", "")
    check("logout -> 302 and clears pb_session",
          r.status_code == 302 and ssomod.SESSION_COOKIE in sc
          and ("expires=" in sc.lower() or '""' in sc or "Max-Age=0" in sc),
          sc[:120])

    # 7. payment + pro-pass untouched without login
    paid_keys = set(getattr(servermod, "routes", {}).keys())
    check("no /auth route is in the paid RouteConfig set",
          not any(k.split(" ", 1)[1].startswith("/auth") for k in paid_keys),
          str(sorted(paid_keys)[:4]))
    r = client.get("/auth/login", follow_redirects=False)
    check("/auth/login is never 402d",
          r.status_code in (301, 302, 303, 307, 500),
          f"got {r.status_code}")
    r = client.get("/report", follow_redirects=False)
    check("unpaid /report still 402s (payment untouched)",
          r.status_code == 402, f"got {r.status_code}")
    r = client.get("/report", headers={"X-Pro-Pass": "garbage-token"},
                   follow_redirects=False)
    check("garbage X-Pro-Pass still falls through to 402",
          r.status_code == 402, f"got {r.status_code}")
    r = client.get("/health")
    check("GET /health still 200", r.status_code == 200 and r.json()["ok"])

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
