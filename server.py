"""x402-gated API server — runs on Base Sepolia testnet by default,

One priced endpoint (GET /report, $0.01 " + _usdc_label() + ") behind the official
x402 Python SDK's FastAPI payment middleware. Uses the no-signup public
or on Base mainnet with CDP facilitator auth (X402_NETWORK=eip155:8453).

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

# Bazaar discovery metadata (lets Coinbase Bazaar and other indexers list us)
from x402.extensions.bazaar.resource_service import (
    OutputConfig,
    declare_discovery_extension,
)

import intel
import watch

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


def _net_label() -> str:
    """Human label for the configured chain — mainnet wording on mainnet."""
    return "Base mainnet" if NETWORK == "eip155:8453" else "Base Sepolia testnet"


def _usdc_label() -> str:
    return "USDC" if NETWORK == "eip155:8453" else "testnet USDC"


def _disclaimer(price: str, premium: bool = False) -> str:
    """Network-aware sale disclaimer — no demo/testnet branding on mainnet."""
    kind = "Premium bundle" if premium else "Data feed"
    prefix = "" if NETWORK == "eip155:8453" else "Demo data only. "
    return f"{prefix}{kind}. Sold on {_net_label()} for {price} {_usdc_label()}."


def _facilitator_config():
    """CDP facilitator needs API-key auth; plain URL otherwise (x402.org testnet)."""
    key_id = os.environ.get("CDP_API_KEY_ID", "").strip()
    key_secret = os.environ.get("CDP_API_KEY_SECRET", "").strip()
    if key_id and key_secret:
        from cdp.x402 import create_facilitator_config

        return create_facilitator_config(key_id, key_secret)
    return FacilitatorConfig(url=FACILITATOR_URL)

app = FastAPI(title="x402 seller (" + _net_label() + ")")


@app.get("/", include_in_schema=False)
async def index():
    return {
        "name": "x402 seller",
        "network": NETWORK,
        "endpoints": {
            "GET /health": "free — liveness probe",
            "GET /report": f"paywalled — {PRICE} (" + _usdc_label() + ") via x402",
            "GET /intel": f"paywalled — {PRICE} (" + _usdc_label() + ") via x402",
            "GET /trending-topics": f"paywalled — {PRICE} (" + _usdc_label() + ") via x402",
            "GET /new-muses": f"paywalled — {PRICE} (" + _usdc_label() + ") via x402",
            "GET /skill-drops": f"paywalled — {PRICE} (" + _usdc_label() + ") via x402",
            "GET /check?url=...": f"paywalled — {PRICE} (" + _usdc_label() + ") via x402",
            "GET /mentions?muse=...": f"paywalled — {PRICE} (" + _usdc_label() + ") via x402",
            "GET /skill-bundle?pack=...": "paywalled — $0.05 (" + _usdc_label() + ") via x402",
            "GET /mega-bundle": "paywalled — $0.15 (" + _usdc_label() + ") via x402 — every curated skill in one payload",
        },
        "note": "Unpaid requests to paywalled routes return HTTP 402 with payment instructions.",
    }


@app.get("/health")
async def health():
    return {"ok": True, "network": NETWORK, "facilitator": FACILITATOR_URL}


facilitator = HTTPFacilitatorClient(_facilitator_config())
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
        description="Demo data report — a tiny JSON payload sold for $0.01 " + _usdc_label() + "",
        service_name="x402 seller",
        tags=["demo", "x402", "test"],
        extensions=declare_discovery_extension(
            output=OutputConfig(
                example={"report": "payload", "headline": "x402 sale complete"}
            )
        ),
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
        description="Musebook intel feed — money-challenge leaderboard, trending lobby posts, newest Skill Exchange skills. $0.01 " + _usdc_label() + "",
        service_name="Musebook intel feed",
        tags=["musebook", "leaderboard", "skills", "trending"],
        extensions=declare_discovery_extension(
            output=OutputConfig(
                example={
                    "generated_at": "2026-09-16T19:00:00+00:00",
                    "leaderboard": [{"muse": "example", "points": 42}],
                    "trending": [{"post": "example"}],
                    "new_skills": [{"slug": "example"}],
                }
            )
        ),
    ),
    "GET /trending-topics": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price=PRICE,
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Trending keyword topics across recent Musebook lobby posts, ranked by mentions. $0.01 " + _usdc_label() + "",
        service_name="Musebook trending topics",
        tags=["musebook", "trending", "topics"],
        extensions=declare_discovery_extension(
            output=OutputConfig(
                example={
                    "topics": [
                        {"topic": "example", "mentions": 12, "sample_post_ids": [1]}
                    ]
                }
            )
        ),
    ),
    "GET /new-muses": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price=PRICE,
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Newest voices on Musebook — muses first seen in the recent post window. $0.01 " + _usdc_label() + "",
        service_name="Musebook new muses",
        tags=["musebook", "new", "muses"],
        extensions=declare_discovery_extension(
            output=OutputConfig(
                example={
                    "new_muses": [
                        {
                            "muse": "example",
                            "first_seen_at": "2026-09-16T19:00:00+00:00",
                            "recent_posts": 3,
                        }
                    ]
                }
            )
        ),
    ),
    "GET /skill-drops": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price=PRICE,
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Newest Skill Exchange skill drops with publisher, version, and description. $0.01 " + _usdc_label() + "",
        service_name="Skill Exchange drops",
        tags=["skills", "musebook", "new"],
        extensions=declare_discovery_extension(
            output=OutputConfig(
                example={
                    "skill_drops": [
                        {
                            "name": "example",
                            "slug": "example",
                            "version": "1.0.0",
                            "publisher": "example",
                        }
                    ]
                }
            )
        ),
    ),
    "GET /check": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price=PRICE,
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Website change monitor — pass ?url= to detect whether a public page changed since the last check. $0.01 per check, " + _usdc_label(),
        service_name="Website change monitor",
        tags=["monitor", "website", "changedetection"],
        extensions=declare_discovery_extension(
            input={"url": "https://example.com"},
            input_schema={
                "properties": {"url": {"type": "string", "format": "uri"}},
                "required": ["url"],
            },
            output=OutputConfig(
                example={
                    "url": "https://example.com",
                    "changed": False,
                    "first_seen": True,
                    "sha256": "abc123",
                }
            ),
        ),
    ),
    "GET /mentions": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price=PRICE,
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Mention radar — pass ?muse=yourname to see recent Musebook lobby posts mentioning you. $0.01 per lookup",
        service_name="Mention radar",
        tags=["musebook", "mentions", "reputation"],
        extensions=declare_discovery_extension(
            input={"muse": "zuckbot"},
            input_schema={
                "properties": {"muse": {"type": "string"}},
                "required": ["muse"],
            },
            output=OutputConfig(
                example={
                    "muse": "zuckbot",
                    "mention_count": 2,
                    "mentions": [{"id": 1, "author": "example", "text": "example"}],
                }
            ),
        ),
    ),
    "GET /skill-bundle": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price="$0.05",
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Premium skill bundles — pass ?pack=creator, ?pack=operator, or ?pack=life for curated full-SKILL.md packs from the Skill Exchange. $0.05 per bundle",
        service_name="Premium skill bundles",
        tags=["skills", "bundle", "musebook"],
        extensions=declare_discovery_extension(
            input={"pack": "creator"},
            input_schema={
                "properties": {"pack": {"type": "string", "enum": ["creator", "operator", "life"]}},
                "required": ["pack"],
            },
            output=OutputConfig(
                example={
                    "pack": "creator",
                    "count": 4,
                    "skills": [{"slug": "series-engine", "chars": 1234}],
                }
            ),
        ),
    ),
    "GET /mega-bundle": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO,
                price="$0.15",
                network=NETWORK,
            )
        ],
        mime_type="application/json",
        description="Mega skill bundle — every curated Skill Exchange skill (creator + operator + life packs) in one payload. $0.15",
        service_name="Mega skill bundle",
        tags=["skills", "bundle", "musebook"],
        extensions=declare_discovery_extension(
            input={},
            input_schema={"properties": {}, "required": []},
            output=OutputConfig(
                example={
                    "pack": "mega",
                    "count": 12,
                    "skills": [{"slug": "series-engine", "chars": 1234}],
                }
            ),
        ),
    ),
}

app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=resource_server)


@app.get("/report")
async def report():
    # This only runs AFTER the middleware has verified + settled payment.
    return {
        "report": "payload",
        "headline": "x402 sale complete",
        "rows": [
            {"metric": "demo_mrr_usd", "value": 0.01},
            {"metric": "items_served", "value": 1},
        ],
        "disclaimer": _disclaimer(PRICE),
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
        "disclaimer": _disclaimer(PRICE),
    }


@app.get("/trending-topics")
async def trending_topics():
    # Paid route — middleware verifies + settles before this runs.
    return {
        "topics": intel.get_trending_topics(),
        "disclaimer": _disclaimer(PRICE),
    }


@app.get("/new-muses")
async def new_muses():
    # Paid route — middleware verifies + settles before this runs.
    return {
        "new_muses": intel.get_new_muses(),
        "disclaimer": _disclaimer(PRICE),
    }


@app.get("/skill-drops")
async def skill_drops():
    # Paid route — middleware verifies + settles before this runs.
    return {
        "skill_drops": intel.get_skill_drops(),
        "disclaimer": _disclaimer(PRICE),
    }


@app.get("/mentions")
async def mentions(muse: str = ""):
    # Paid route — middleware verifies + settles before this runs.
    name = muse.strip()
    if not name:
        return {"error": "missing ?muse=name query parameter"}
    from datetime import datetime, timezone

    hits = intel.get_mentions(name)
    return {
        "muse": name,
        "mention_count": len(hits),
        "mentions": hits,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": _disclaimer(PRICE),
    }


@app.get("/skill-bundle")
async def skill_bundle(pack: str = ""):
    # Paid route — middleware verifies + settles before this runs.
    name = pack.strip().lower()
    if name not in intel.BUNDLES:
        return {"error": "unknown pack", "available_packs": intel.list_bundles()}
    from datetime import datetime, timezone

    bundle = intel.get_skill_bundle(name)
    bundle["generated_at"] = datetime.now(timezone.utc).isoformat()
    bundle["disclaimer"] = _disclaimer("$0.05", premium=True)
    return bundle


@app.get("/mega-bundle")
async def mega_bundle():
    # Paid route — middleware verifies + settles before this runs.
    # Every curated skill in one payload, premium price.
    from datetime import datetime, timezone

    bundle = intel.get_mega_bundle()
    bundle["generated_at"] = datetime.now(timezone.utc).isoformat()
    bundle["disclaimer"] = _disclaimer("$0.15", premium=True)
    return bundle


@app.get("/check")
async def check(url: str):
    # Paid route — middleware verifies + settles before this runs.
    # watch.check_url never raises; failures come back as {"error": ...}.
    result = watch.check_url(url)
    result["disclaimer"] = _disclaimer(PRICE)
    return result


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "4021"))
    host = os.environ.get("HOST", "127.0.0.1")  # Render: HOST=0.0.0.0
    print(f"[seller] network={NETWORK} price={PRICE} pay_to={PAY_TO}")
    print(f"[seller] facilitator={FACILITATOR_URL}")
    print(f"[seller] listening on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
