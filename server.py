"""x402-gated demo API server — Base Sepolia testnet.

One priced endpoint (GET /report, $0.01 testnet USDC) behind the official
x402 Python SDK's FastAPI payment middleware. Uses the no-signup public
testnet facilitator at https://x402.org/facilitator.

Run:
    .venv/bin/python server.py
    # or: X402_PAY_TO=0xYourAddress .venv/bin/python server.py

Then in another terminal:
    .venv/bin/python buyer.py
"""

import os

# --- sandbox proxy fix -----------------------------------------------------
# This VM exports NO_PROXY with bracketed IPv6 entries (e.g. "[::1]") that
# httpx 0.28 cannot parse ("Invalid port: ':1]'"), which crashes the x402
# SDK's facilitator client at request time. Scope the fix to this process
# only: keep the real proxy vars, simplify no_proxy to plain IPv4 hosts.
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "localhost,127.0.0.1"
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer

import intel

# Base Sepolia (testnet). Mainnet Base is eip155:8453.
NETWORK = os.environ.get("X402_NETWORK", "eip155:84532")
FACILITATOR_URL = os.environ.get(
    "X402_FACILITATOR_URL", "https://x402.org/facilitator"
)

# !!! PLACEHOLDER — NOT a real wallet !!!
# On mainnet this MUST be replaced with Anthony's own receiving address.
# Testnet demo payments sent here are unrecoverable (burn address).
PAY_TO = os.environ.get(
    "X402_PAY_TO", "0x000000000000000000000000000000000000dEaD"
)
PRICE = os.environ.get("X402_PRICE", "$0.01")

app = FastAPI(title="x402 demo seller (testnet)")


@app.get("/", include_in_schema=False)
async def index():
    return {
        "name": "x402 demo seller",
        "network": NETWORK,
        "endpoints": {
            "GET /health": "free — liveness probe",
            "GET /report": f"paywalled — {PRICE} (testnet USDC) via x402",
            "GET /intel": f"paywalled — {PRICE} (testnet USDC) via x402",
        },
        "note": "Unpaid requests to /report and /intel return HTTP 402 with payment instructions.",
    }


@app.get("/health")
async def health():
    return {"ok": True, "network": NETWORK, "facilitator": FACILITATOR_URL}


facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
resource_server = x402ResourceServer(facilitator)
resource_server.register(NETWORK, ExactEvmServerScheme())

routes = {
    "GET /report": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price=PRICE,
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Demo data report — a tiny JSON payload sold for $0.01 testnet USDC",
    ),
    "GET /intel": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price=PRICE,
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Musebook intel feed — money-challenge leaderboard, trending lobby posts, newest Skill Exchange skills. $0.01 testnet USDC",
    ),
}

app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=resource_server)


@app.get("/report")
async def report():
    # This only runs AFTER the middleware has verified + settled payment.
    return {
        "report": "demo-payload",
        "headline": "x402 testnet sale complete",
        "rows": [
            {"metric": "demo_mrr_usd", "value": 0.01},
            {"metric": "items_served", "value": 1},
        ],
        "disclaimer": "Demo data only. Sold on Base Sepolia testnet for $0.01 testnet USDC.",
    }


@app.get("/intel")
async def intel_feed():
    # This only runs AFTER the middleware has verified + settled payment.
    # Each fetcher caches upstream results for 5 minutes and returns []
    # on upstream failure — never raises.
    from datetime import datetime, timezone

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leaderboard": intel.get_leaderboard(),
        "trending": intel.get_trending(),
        "new_skills": intel.get_new_skills(),
        "disclaimer": "Demo data only. Sold on Base Sepolia testnet for $0.01 testnet USDC.",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "4021"))
    host = os.environ.get("HOST", "127.0.0.1")  # Render: HOST=0.0.0.0
    print(f"[seller] network={NETWORK} price={PRICE} pay_to={PAY_TO}")
    print(f"[seller] facilitator={FACILITATOR_URL}")
    print(f"[seller] listening on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
