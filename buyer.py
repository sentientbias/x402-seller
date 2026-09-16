"""x402 buyer test script — completes a full paid request against server.py.

Flow:
  1. Generates an EPHEMERAL test key (in-memory only, never written to disk).
     Base Sepolia testnet ONLY. Worthless by design.
  2. Checks the wallet's testnet USDC balance on Base Sepolia.
     If unfunded, prints the address + faucet instructions and stops.
  3. GET /report with no payment  -> expects HTTP 402, prints requirements.
  4. GET /report via x402HttpxClient -> auto signs EIP-3009 authorization,
     retries with X-PAYMENT header, server verifies+settles via the
     x402.org facilitator -> expects HTTP 200 with the JSON payload.

Run:
    .venv/bin/python buyer.py
"""

import asyncio
import os
import secrets
import sys

# Same sandbox proxy fix as server.py (httpx chokes on "[::1]" in NO_PROXY).
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "localhost,127.0.0.1"

import httpx
from eth_account import Account

from x402 import x402Client
from x402.http.clients.httpx import x402HttpxClient
from x402.mechanisms.evm.exact import ExactEvmScheme

BASE_URL = os.environ.get("X402_BASE_URL", "http://127.0.0.1:4021")
RPC_URL = os.environ.get("X402_RPC_URL", "https://sepolia.base.org")
# Base Sepolia USDC (6 decimals) — from the x402 SDK's default asset list.
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

FAUCET_URL = "https://faucet.circle.com"


def usdc_balance_wei(address: str) -> int:
    """Raw eth_call balanceOf(address) — no web3 needed."""
    selector = "70a08231"  # balanceOf(address)
    data = "0x" + selector + address[2:].lower().zfill(64)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": USDC_BASE_SEPOLIA, "data": data}, "latest"],
    }
    r = httpx.post(RPC_URL, json=payload, timeout=30)
    r.raise_for_status()
    result = r.json()["result"]
    return int(result, 16)


async def main() -> int:
    # --- 0. --gen: print a fresh throwaway address for faucet funding -------
    if "--gen" in sys.argv:
        fresh = Account.from_key("0x" + secrets.token_hex(32))
        print(f"address: {fresh.address}")
        print(f"key:     {fresh.key.hex()}")
        print("TESTNET THROWAWAY — fund the address at https://faucet.circle.com")
        print("(Base Sepolia / USDC), then run: X402_BUYER_KEY=<key> .venv/bin/python buyer.py")
        return 0

    # --- 1. buyer key: X402_BUYER_KEY or ephemeral (never persisted) --------
    # WARNING: X402_BUYER_KEY must ONLY ever be a testnet throwaway key.
    # Never put a real/mainnet key here.
    env_key = os.environ.get("X402_BUYER_KEY", "").strip()
    private_key = env_key if env_key else "0x" + secrets.token_hex(32)
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    acct = Account.from_key(private_key)
    buyer = acct.address
    print(f"[buyer] test wallet: {buyer} ({'from X402_BUYER_KEY' if env_key else 'ephemeral, in-memory only'})")
    print("[buyer] TESTNET ONLY — never use a real key here.")

    # --- 2. check testnet USDC balance ------------------------------------
    try:
        balance = usdc_balance_wei(buyer)
    except Exception as e:  # noqa: BLE001
        print(f"[buyer] ERROR: could not read USDC balance: {e}")
        return 2
    print(f"[buyer] testnet USDC balance: {balance / 1e6:.6f} USDC")
    if balance < 10_000:  # need at least $0.01
        print()
        print("[buyer] NOT FUNDED — cannot complete a paid request.")
        print("[buyer] Fund this address, then re-run:")
        print(f"[buyer]   1. Open {FAUCET_URL}")
        print("[buyer]   2. Select network: Base Sepolia, token: USDC")
        print(f"[buyer]   3. Paste address: {buyer}")
        print("[buyer]   4. Send funds (free, no signup; may need a captcha)")
        print("[buyer]   5. Re-run: .venv/bin/python buyer.py")
        return 3

    # --- 3. unpaid request -> expect 402 -----------------------------------
    async with httpx.AsyncClient() as raw:
        r = await raw.get(f"{BASE_URL}/report", timeout=30)
    print(f"\n[buyer] unpaid GET /report -> HTTP {r.status_code}")
    if r.status_code != 402:
        print(f"[buyer] ERROR: expected 402, got body: {r.text[:300]}")
        return 4
    reqs = r.json().get("accepts", r.json())
    print(f"[buyer] 402 payment requirements: {str(reqs)[:220]}...")

    # --- 4. paid request via x402 client (402 -> sign -> retry) ------------
    client = x402Client()
    client.register("eip155:*", ExactEvmScheme(signer=acct))
    async with x402HttpxClient(client) as paid:
        r2 = await paid.get(f"{BASE_URL}/report", timeout=120)
    print(f"\n[buyer] paid GET /report -> HTTP {r2.status_code}")
    pay_resp = r2.headers.get("payment-response") or r2.headers.get("x-payment-response")
    if pay_resp:
        print(f"[buyer] PAYMENT-RESPONSE: {pay_resp[:220]}...")
    print(f"[buyer] body: {r2.text[:400]}")
    if r2.status_code == 200 and "demo-payload" in r2.text:
        print("\n[buyer] SUCCESS — full x402 purchase flow completed on Base Sepolia.")
        return 0
    print("\n[buyer] FAILED — paid request did not return the payload.")
    return 5


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
