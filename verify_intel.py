"""Verify the paid GET /intel flow end to end on Base Sepolia testnet.

1. Unpaid GET /intel -> expect HTTP 402.
2. Paid GET /intel via x402 client (X402_BUYER_KEY must be a funded
   testnet throwaway key) -> expect HTTP 200 with populated sections.

Run: X402_BUYER_KEY=<testnet-throwaway-key> .venv/bin/python verify_intel.py
"""

import asyncio
import os
import sys

os.environ["no_proxy"] = os.environ["NO_PROXY"] = "localhost,127.0.0.1"

import httpx
from eth_account import Account

from x402 import x402Client
from x402.http.clients.httpx import x402HttpxClient
from x402.mechanisms.evm.exact import ExactEvmScheme

BASE_URL = os.environ.get("X402_BASE_URL", "http://127.0.0.1:4021")
RPC_URL = os.environ.get("X402_RPC_URL", "https://sepolia.base.org")
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def usdc_balance_wei(address: str) -> int:
    selector = "70a08231"
    data = "0x" + selector + address[2:].lower().zfill(64)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": USDC_BASE_SEPOLIA, "data": data}, "latest"],
    }
    r = httpx.post(RPC_URL, json=payload, timeout=30)
    r.raise_for_status()
    return int(r.json()["result"], 16)


async def main() -> int:
    env_key = os.environ.get("X402_BUYER_KEY", "").strip()
    if not env_key:
        print("[verify] ERROR: X402_BUYER_KEY not set (testnet throwaway only).")
        return 2
    key = env_key if env_key.startswith("0x") else "0x" + env_key
    acct = Account.from_key(key)
    print(f"[verify] test wallet: {acct.address}")
    bal = usdc_balance_wei(acct.address)
    print(f"[verify] testnet USDC balance: {bal / 1e6:.6f} USDC")
    if bal < 10_000:
        print("[verify] ERROR: wallet unfunded — cannot run paid verification.")
        return 3

    async with httpx.AsyncClient() as raw:
        r = await raw.get(f"{BASE_URL}/intel", timeout=30)
    print(f"[verify] unpaid GET /intel -> HTTP {r.status_code}")
    if r.status_code != 402:
        print(f"[verify] ERROR: expected 402, got: {r.text[:300]}")
        return 4

    client = x402Client()
    client.register("eip155:*", ExactEvmScheme(signer=acct))
    async with x402HttpxClient(client) as paid:
        r2 = await paid.get(f"{BASE_URL}/intel", timeout=120)
    print(f"[verify] paid GET /intel -> HTTP {r2.status_code}")
    if r2.status_code != 200:
        print(f"[verify] ERROR: paid request failed: {r2.text[:400]}")
        return 5
    body = r2.json()
    lb = body.get("leaderboard", [])
    tr = body.get("trending", [])
    sk = body.get("new_skills", [])
    print(f"[verify] sections: leaderboard={len(lb)} trending={len(tr)} new_skills={len(sk)}")
    print(f"[verify] generated_at: {body.get('generated_at')}")
    if lb:
        print(f"[verify] top claim: {lb[0]['muse']} +${lb[0]['amount_usd']}")
    pay_resp = r2.headers.get("payment-response") or r2.headers.get("x-payment-response")
    print(f"[verify] PAYMENT-RESPONSE present: {bool(pay_resp)}")
    print("[verify] SUCCESS — full paid /intel purchase completed on Base Sepolia.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
