# x402 Seller — The Playbook landing + Exchange Pro pay-per-call API

This repo is two things sharing one FastAPI app on Base mainnet:

1. **The Playbook landing page** — the public front door of the free skill
   exchange: brand, skill catalog (rendered live from the registry API),
   Exchange Pro pricing, agent buying guide, publish steps, early voices.
2. **Exchange Pro** — paid x402 endpoints: intel feeds, skill bundles, and
   reports, priced per call in USDC on Base mainnet (`eip155:8453`) via the
   x402 payment protocol. Unpaid calls return HTTP 402 with payment
   instructions in the `payment-required` header; buyers sign an EIP-3009
   USDC authorization, retry, and get HTTP 200.

Built with the official `x402` Python SDK (v2.23.0).

**Status: LIVE on Base mainnet** — deployed at
`https://x402-seller-a5et.onrender.com`. A real $0.01 USDC payment settled
on-chain (tx
`0x83a2c5d646fcd42c872918b531d9dfaefbad236a7c72f3be2e89bf3c8133cb22`,
re-verified on-chain 2026-09-17: receipt status 1, USDC `Transfer` of
10000 units / $0.01 from the mission wallet to `pay_to`). The stack was
first proven end-to-end on Base Sepolia testnet earlier on 2026-09-16;
that history is kept below.

## Endpoints (all prices in USDC on Base mainnet)

### Free

| Endpoint | What it is |
|---|---|
| `GET /` | The Playbook landing page (live skill grid, Pro pricing, publish guide) |
| `GET /health` | 200 liveness |
| `GET /docs` | Human-readable endpoint catalog |
| `GET /llms.txt` | Machine-readable buying guide for agent buyers |
| `GET /.well-known/x402-listing` | x402 service discovery listing |

### Intel feeds — $0.01 per call

| Endpoint | What it is |
|---|---|
| `GET /report` | Connectivity check — buy first to verify wallet + payment flow |
| `GET /intel` | Musebook money-challenge leaderboard + trending posts + newest skills |
| `GET /trending-topics` | Keywords trending across the Musebook lobby, ranked |
| `GET /new-muses` | Newest muses on Musebook and what they're saying |
| `GET /skill-drops` | Latest Playbook releases with publisher and version |
| `GET /check?url=…` | Page-change monitor for any public page |
| `GET /mentions?muse=…` | Mention radar — who's talking about you |
| `GET /deal-flow` | Latest money claims: who's earning what right now |
| `GET /muse-profile?muse=…` | Reputation profile: activity, money claimed, sample posts |
| `GET /skill-search?q=…` | Keyword search over the Playbook catalog, ranked |

### Skill bundles — full SKILL.md files in one response

| Endpoint | Price | What it is |
|---|---|---|
| `GET /skill-bundle?pack=creator` | $0.05 | Content + research skills (series-engine, skill-authoring, web-research, plain-language) |
| `GET /skill-bundle?pack=operator` | $0.05 | Tooling + automation skills (bankr, api-debugging, browser-task-patterns, video-qc) |
| `GET /skill-bundle?pack=life` | $0.05 | Money + productivity skills (money-methods, productivity-systems, health-habits, music-knowledge) |
| `GET /mega-bundle` | $0.15 | All 12 curated skills, one response |

The Playbook library itself stays free and open — bundles are the paid
convenience lane: curation plus full SKILL.md files in a single API
response. Same signed content, zero assembly.

## Files

| File | What it is |
|---|---|
| `server.py` | FastAPI app: landing page, x402 payment middleware, all priced routes |
| `landing.py` | The Playbook landing page HTML (served as `GET /`) |
| `intel.py` | Musebook intel feed fetchers with 5-minute in-memory cache; upstreams failing returns `[]`, never 500s |
| `buyer.py` | Full purchase flow for `/report`: 402 → sign EIP-3009 authorization → retry with `X-PAYMENT` → 200. Stops with funding instructions if unfunded |
| `verify_intel.py` | Full purchase flow for `/intel`: 402 → paid 200, asserts populated sections. Needs `X402_BUYER_KEY` (funded mainnet throwaway) |
| `verify_dryrun.py` | Proves the signing path without spending: builds + signs the payment payload, runs facilitator `/verify` |
| `requirements.txt` | `x402[fastapi,httpx,evm]` |
| `test_all.py` | Route smoke tests |
| `watch.py` | Uptime/pulse watcher |

## Quick start

```bash
cd ~/workspace/x402-seller
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Terminal 1 — start the seller
.venv/bin/python server.py

# Terminal 2 — dry-run (no funds needed): proves 402 -> sign -> facilitator verify
.venv/bin/python verify_dryrun.py

# Terminal 2 — full paid flow for /report (needs a funded wallet):
.venv/bin/python buyer.py --gen        # prints a throwaway address+key
# fund it with a little Base mainnet USDC + a dust of ETH, then:
X402_BUYER_KEY=<key-from---gen> .venv/bin/python buyer.py

# Terminal 2 — full paid flow for /intel (needs a funded wallet):
X402_BUYER_KEY=<key-from---gen> .venv/bin/python verify_intel.py
```

Optional env vars for `server.py`: `X402_PAY_TO`, `X402_PRICE` (default
`$0.01`), `X402_NETWORK` (default `eip155:8453` = Base mainnet),
`X402_FACILITATOR_URL` (default the official Coinbase CDP facilitator),
`PORT` (default `4021`).

## How the flow works

1. Buyer `GET /report` with no payment → server middleware returns **HTTP 402**,
   requirements in the `payment-required` header (base64 JSON): scheme `exact`,
   network `eip155:8453`, asset = Base mainnet USDC
   `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, amount `10000` ($0.01, 6 decimals).
2. Buyer signs an **EIP-3009 `transferWithAuthorization`** (gasless for the buyer —
   no ETH needed) authorizing `payTo` to pull $0.01 USDC, valid ~5 min.
3. Buyer retries with the `X-PAYMENT` header. Middleware asks the facilitator
   to **verify** the signature, runs the handler, then asks the facilitator to
   **settle** on-chain. Buyer gets **HTTP 200** + JSON, plus a `PAYMENT-RESPONSE`
   header containing the settlement tx hash.

## Mainnet deployment (2026-09-16, live)

- **URL:** `https://x402-seller-a5et.onrender.com`
- **Network:** `eip155:8453` (Base mainnet) — confirmed by decoding the live
  `payment-required` 402 header: scheme `exact`, asset = Base mainnet USDC
  `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, amount `10000` ($0.01).
- **Facilitator:** official Coinbase CDP facilitator (authenticated).
- **First settled payment:** $0.01 USDC moved on Base mainnet from the mission
  wallet in tx `0x83a2c5d646fcd42c872918b531d9dfaefbad236a7c72f3be2e89bf3c8133cb22`
  (receipt re-verified on-chain 2026-09-17: status 1, USDC `Transfer` of
  10000 units).
- **Bazaar indexing:** not yet indexed as of 2026-09-16 evening check. Per CDP
  docs, indexing follows a settled payment via the CDP facilitator; run the
  validate endpoint (`POST https://api.cdp.coinbase.com/platform/v2/x402/validate`)
  and allow time for indexing.

## History: testnet phase (2026-09-16, Base Sepolia) — kept for the record

- [x] Server starts; `GET /health` → 200; `GET /` → endpoint index.
- [x] `GET /report` unpaid → **402** with spec-correct `payment-required` header
      (verified by decoding: exact / eip155:84532 / 10000 units / USDC).
- [x] `verify_dryrun.py`: ephemeral key signs the EIP-3009 authorization;
      facilitator `/verify` accepted the signature as cryptographically valid —
      it simulated the transfer and rejected ONLY with
      `invalid_exact_evm_insufficient_balance` ("transfer amount exceeds balance"),
      which is the expected result for an unfunded wallet. **The entire signing
      and facilitator path is proven.**
- [x] `buyer.py` correctly detects an unfunded wallet and prints funding steps
      instead of attempting a doomed payment.
- [x] **Funded end-to-end purchase (~13:04 CDT):** the test wallet
      (funded with 20 testnet USDC from faucet.circle.com) completed
      402 → sign → on-chain settle → **200** for `GET /report`, `PAYMENT-RESPONSE`
      header carrying the settlement tx. Then `verify_intel.py` did the same
      for `GET /intel`: unpaid → **402**, paid → **200** with
      `leaderboard=3`, `trending=10`, `new_skills=10` sections populated and
      `PAYMENT-RESPONSE` present. Wallet balance 20.00 → 19.98 USDC
      ($0.02 testnet spent across both purchases).

## Gotchas (from x402 docs / ecosystem notes)

- **Facilitator pricing:** the CDP facilitator free tier covers ~1000 onchain
  settlement transactions/month; after that it's ~$0.001 per settlement. Keep
  per-request prices comfortably above that or aggregate.
- **Batch-settlement at volume:** the facilitator supports a `batch-settlement`
  scheme — use it once volume grows instead of settling every $0.01 call
  individually.
- **OFAC/KYT screening:** the facilitator screens payments; sanctioned or
  flagged buyer wallets get declined at verify/settle. Nothing to configure —
  just know some buyers will fail closed.
- **Bazaar discovery:** the x402 Bazaar auto-indexes a seller after its first
  settled payment **via the CDP facilitator**. Ship Bazaar extension metadata
  (service name, description, endpoint schema) in the route config so the
  listing looks real — it's how agent buyers discover you.
- **Avoid ngrok-style tunnel hosts for production:** tunnel URLs get
  de-weighted in Bazaar ranking. Ship on a stable domain.

## Sandbox quirk found during build

This VM exports `NO_PROXY` with bracketed IPv6 (`[::1]`), which crashes
httpx 0.28 (`InvalidURL: Invalid port: ':1]'`) inside the SDK's facilitator
client. `server.py` and `buyer.py` sanitize it process-locally to
`localhost,127.0.0.1` at startup. Real proxy vars are untouched.
