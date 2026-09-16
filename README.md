# x402 Seller — demo API paywalled with USDC on Base Sepolia testnet

A working x402 (Coinbase) seller stack: a FastAPI server with two priced
endpoints, a buyer script that completes the full purchase flow, and
verifiers. Built with the official `x402` Python SDK (v2.23.0).

**Status: full purchase flow verified on-chain** — a funded test wallet
completed 402 → sign → settle → 200 for both `/report` and `/intel` on
Base Sepolia (testnet USDC, worthless play money). See "Verification results".

## Files

| File | What it is |
|---|---|
| `server.py` | FastAPI + x402 payment middleware. `GET /report` and `GET /intel` each cost $0.01 testnet USDC. Free: `GET /`, `GET /health`. |
| `intel.py` | Musebook intel feed fetchers (leaderboard, trending lobby, new skills) with 5-minute in-memory cache; upstreams failing returns `[]`, never 500s. |
| `buyer.py` | Full purchase flow for `/report`: 402 → sign EIP-3009 authorization → retry with `X-PAYMENT` → 200. Stops with faucet instructions if unfunded. |
| `verify_intel.py` | Full purchase flow for `/intel`: 402 → paid 200, asserts populated sections. Needs `X402_BUYER_KEY` (funded testnet throwaway). |
| `verify_dryrun.py` | Proves the signing path without spending: builds + signs the payment payload, runs facilitator `/verify`. |
| `requirements.txt` | `x402[fastapi,httpx,evm]` |
| `.env.example` | Config for mainnet migration. |

## Quick start

```bash
cd ~/workspace/goals/5k-online-income-project/x402-seller
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Terminal 1 — start the seller (uses placeholder pay_to, see below)
.venv/bin/python server.py

# Terminal 2 — dry-run (no funds needed): proves 402 -> sign -> facilitator verify
.venv/bin/python verify_dryrun.py

# Terminal 2 — full paid flow for /report (needs a funded test wallet):
.venv/bin/python buyer.py --gen        # prints a throwaway address+key
# fund the address at https://faucet.circle.com (Base Sepolia / USDC, free, no signup)
X402_BUYER_KEY=<key-from---gen> .venv/bin/python buyer.py

# Terminal 2 — full paid flow for /intel (needs a funded test wallet):
X402_BUYER_KEY=<key-from---gen> .venv/bin/python verify_intel.py
```

Optional env vars for `server.py`: `X402_PAY_TO`, `X402_PRICE` (default `$0.01`),
`X402_NETWORK` (default `eip155:84532` = Base Sepolia),
`X402_FACILITATOR_URL` (default `https://x402.org/facilitator`, no signup on testnet),
`PORT` (default `4021`).

## How the flow works

1. Buyer `GET /report` with no payment → server middleware returns **HTTP 402**,
   requirements in the `payment-required` header (base64 JSON): scheme `exact`,
   network `eip155:84532`, asset = Base Sepolia USDC
   `0x036CbD53842c5426634e7929541eC2318f3dCF7e`, amount `10000` ($0.01, 6 decimals).
2. Buyer signs an **EIP-3009 `transferWithAuthorization`** (gasless for the buyer —
   no ETH needed) authorizing `payTo` to pull $0.01 USDC, valid ~5 min.
3. Buyer retries with the `X-PAYMENT` header. Middleware asks the facilitator
   to **verify** the signature, runs the handler, then asks the facilitator to
   **settle** on-chain. Buyer gets **HTTP 200** + JSON, plus a `PAYMENT-RESPONSE`
   header containing the settlement tx hash.

## The /intel endpoint — Musebook intel feed

`GET /intel` — **$0.01 testnet USDC** via the same x402 middleware as
`/report`. It is the stack's first real data product: a structured feed of
what's happening in the Musebook muse town, aimed at agent buyers who can't
conveniently poll those sources themselves.

Response shape:

```json
{
  "generated_at": "2026-09-16T18:04:13.159756+00:00",
  "leaderboard": [
    {"muse": "Nimbus", "amount_usd": 294.0,
     "description": "cancelled the insurance, verified the refunds…", "post_id": 1274}
  ],
  "trending": [
    {"id": 1549, "name": "Zuckbot", "text": "skill exchange update: …",
     "created_at": "2026-09-16 18:01:02"}
  ],
  "new_skills": [
    {"name": "Series Engine", "slug": "series-engine",
     "description": "Turn a single topic into a multi-part serialized post series…",
     "version": "1.0.0"}
  ],
  "disclaimer": "Demo data only. Sold on Base Sepolia testnet for $0.01 testnet USDC."
}
```

Data sources (all fetched server-side by `intel.py`, cached in-memory for
5 minutes, each section degrading to `[]` if its upstream fails — a dead
upstream can never 500 the paid endpoint):

| Section | Source | What it is |
|---|---|---|
| `leaderboard` | `musebook.lol/api/latest.json?channel=musemoneychallenge` | Claim posts in `🏆 +$AMOUNT — description` format, parsed to `{muse, amount_usd, description, post_id}`, sorted by amount desc |
| `trending` | `musebook.lol/api/latest.json?channel=lobby` | 10 most recent lobby posts as `{id, name, text (200 chars), created_at}` |
| `new_skills` | `skill-exchange-api-hoev.onrender.com/api/v1/skills` | 10 newest registry skills as `{name, slug, description, version}`, newest first |

## Verification results (2026-09-16, all on Base Sepolia)

- [x] Server starts; `GET /health` → 200; `GET /` → endpoint index.
- [x] `GET /report` unpaid → **402** with spec-correct `payment-required` header
      (verified by decoding: exact / eip155:84532 / 10000 units / USDC).
- [x] `verify_dryrun.py`: ephemeral key signs the EIP-3009 authorization;
      facilitator `/verify` accepted the signature as cryptographically valid —
      it simulated the transfer and rejected ONLY with
      `invalid_exact_evm_insufficient_balance` ("transfer amount exceeds balance"),
      which is the expected result for an unfunded wallet. **The entire signing
      and facilitator path is proven.**
- [x] `buyer.py` correctly detects an unfunded wallet and prints faucet steps
      instead of attempting a doomed payment.
- [x] **Funded end-to-end purchase (2026-09-16 ~13:04 CDT):** the test wallet
      (funded with 20 testnet USDC from faucet.circle.com) completed
      402 → sign → on-chain settle → **200** for `GET /report`, `PAYMENT-RESPONSE`
      header carrying the settlement tx. Then `verify_intel.py` did the same
      for `GET /intel`: unpaid → **402**, paid → **200** with
      `leaderboard=3`, `trending=10`, `new_skills=10` sections populated and
      `PAYMENT-RESPONSE` present. Wallet balance 20.00 → 19.98 USDC
      ($0.02 testnet spent across both purchases).
- [ ] **Not yet done:** mainnet migration (needs Anthony — see below).

## What Anthony must provide to go mainnet

1. **A receiving wallet address** (`payTo`) on Base — any EVM wallet he controls
   (e.g. Coinbase Wallet). Set `X402_PAY_TO=0x...` / mainnet `eip155:8453`.
   This is the ONLY money-touching config, and it's just an address.
2. **CDP account + facilitator**: mainnet facilitator is
   `https://api.cdp.coinbase.com/platform/v2/x402` — requires a free Coinbase
   Developer Platform account and API key. (Testnet uses `x402.org`, no signup.)
3. **Hosting**: any always-on host with a public HTTPS URL (VPS, Railway,
   Fly.io, Cloudflare Tunnel…). The demo binds localhost; production needs a
   public origin so buyers (and the Bazaar indexer) can reach it.
4. **A real data product**: `/report` returns a static JSON; `/intel` is the
   first real one (Musebook intel feed — leaderboard, trending lobby, new
   skills). A sellable version needs an endpoint buyers actually want on
   mainnet — price it in the `RouteConfig` (`price="$0.05"` etc.).

No private keys are stored anywhere in this repo. The seller never touches keys
at all — it only needs the public `payTo` address.

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
