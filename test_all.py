"""Paid end-to-end test for ALL x402 seller routes (testnet only)."""
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

ROUTES = [
    "/report",
    "/intel",
    "/trending-topics",
    "/new-muses",
    "/skill-drops",
    "/check?url=https://example.com",
    "/mentions?muse=zuckbot",
    "/skill-bundle?pack=creator",
]


def usdc_balance_wei(address: str) -> int:
    data = "0x70a08231" + address[2:].lower().zfill(64)
    r = httpx.post(
        RPC_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
              "params": [{"to": USDC_BASE_SEPOLIA, "data": data}, "latest"]},
        timeout=30,
    )
    r.raise_for_status()
    return int(r.json()["result"], 16)


async def main() -> int:
    key = os.environ.get("X402_BUYER_KEY", "").strip()
    if not key:
        print("X402_BUYER_KEY required (testnet throwaway only).")
        return 2
    acct = Account.from_key(key if key.startswith("0x") else "0x" + key)
    print(f"[test] wallet: {acct.address}")
    for _ in range(6):
        bal = usdc_balance_wei(acct.address)
        print(f"[test] balance: {bal / 1e6:.6f} USDC")
        if bal >= 10_000 * len(ROUTES):
            break
        await asyncio.sleep(15)
    else:
        print("[test] NOT FUNDED enough for all routes.")
        return 3

    client = x402Client()
    client.register("eip155:*", ExactEvmScheme(signer=acct))
    ok = 0
    async with x402HttpxClient(client) as paid:
        for route in ROUTES:
            try:
                r = await paid.get(f"{BASE_URL}{route}", timeout=120)
                body_ok = len(r.text) > 50 and "error" not in r.text[:60].lower()
                print(f"[test] paid {route} -> {r.status_code} ({len(r.text)} bytes)")
                if r.status_code == 200:
                    ok += 1
                else:
                    print(f"  body: {r.text[:200]}")
            except Exception as e:  # noqa: BLE001
                print(f"[test] paid {route} -> EXCEPTION {e}")
    print(f"\n[test] {ok}/{len(ROUTES)} paid routes returned 200.")
    return 0 if ok == len(ROUTES) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
