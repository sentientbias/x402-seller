# Playbook/Exchange Pro SSO client — build plan (2026-09-21)

## Recon findings
- App: FastAPI in `server.py`; landing HTML in `landing.py` (`LANDING_HTML`,
  `NETWORK_HTML`); static files served at `/static` from `static/`.
- Payment: x402 middleware only 402s routes listed in the `routes`
  (RouteConfig) dict. New `/auth/*` routes are NOT listed → free by default.
- ProPassMiddleware: only bypasses payment on a VALID Ed25519 X-Pro-Pass;
  everything else falls through to the 402 flow. Untouched by SSO.
- Brand anchor: `landing.py:236` (`LANDING_HTML`) and `_NETWORK_NAV`
  (`NETWORK_HTML`).
- `</body>` injection point: `server.py` `index()`/`network()` handlers can
  string-replace (same pattern `_with_sidebar` uses).

## Changes
1. **New `sso.py`**: all SSO logic — PKCE pair, signed state cookie
   (`sso_state`, itsdangerous, holds {state, verifier}, 10 min), token
   exchange via urllib (threaded), Ed25519 ID-token verify via PyNaCl
   (pubkey from provider /auth/pubkey, cached), claims check
   (iss/aud/exp), local session cookie `pb_session` (30 days),
   in-memory per-IP throttle on /auth/callback.
2. **`server.py`**: `GET /auth/login`, `GET /auth/callback`,
   `GET /auth/logout`; `index()`/`network()` inject orb `<script>` and
   replace `<!--SSO_NAV-->` with Sign-in or Hi @handle/Sign-out.
3. **`landing.py`**: `data-muse-orb-anchor` on both brand links;
   `<!--SSO_NAV-->` placeholder in both navs.
4. **`static/js/muse-orb.js`**: copied from musefm-townsquare.
5. **`requirements.txt`**: add `itsdangerous`.
6. **`test_sso_client_2026_09_21.py`**: TestClient tests — happy path
   (stubbed provider, REAL Ed25519 verify path), state mismatch,
   tampered token, wrong aud, logout clears cookie, 402 on unpaid route
   (payment untouched), landing 200 without login.

## Non-goals / guards
- x402 payment routes, Pro-pass verification, pricing: zero changes.
- Login is optional; browsing never requires it.
- SESSION_SECRET from env; /auth/login 500s cleanly if unset (documented).
- No push, no deploy. Branch: global-login-2026-09-21.
