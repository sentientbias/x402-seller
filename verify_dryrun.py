"""Dry-run: prove the signing path without spending.

1. GET /report -> 402, parse payment-required header.
2. Build + EIP-712-sign the EIP-3009 authorization with an ephemeral key (offline).
3. POST {paymentPayload, paymentRequirements} to the facilitator /verify.
4. Report verify result. (No /settle: the wallet holds no testnet USDC.)

This validates everything except on-chain settlement.
"""

import asyncio
import base64
import json
import os
import secrets
import sys

os.environ["no_proxy"] = os.environ["NO_PROXY"] = "localhost,127.0.0.1"

import httpx
from eth_account import Account

from x402 import x402Client
from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.schemas import PaymentRequired

BASE_URL = os.environ.get("X402_BASE_URL", "http://127.0.0.1:4021")
FACILITATOR_URL = os.environ.get("X402_FACILITATOR_URL", "https://x402.org/facilitator")


async def main() -> int:
    acct = Account.from_key("0x" + secrets.token_hex(32))
    print(f"[dryrun] ephemeral signer: {acct.address} (in-memory only)")

    async with httpx.AsyncClient() as http:
        r = await http.get(f"{BASE_URL}/report", timeout=30)
    assert r.status_code == 402, f"expected 402, got {r.status_code}"
    header = r.headers["payment-required"]
    required = PaymentRequired.model_validate(json.loads(base64.b64decode(header)))
    req = required.accepts[0]
    print(f"[dryrun] 402 parsed: {req.scheme} {req.network} amount={req.amount} asset={req.asset}")

    client = x402Client()
    client.register("eip155:*", ExactEvmScheme(signer=acct))
    payload = await client.create_payment_payload(required)
    sig = payload.payload["signature"] if isinstance(payload.payload, dict) else payload.payload.signature
    print(f"[dryrun] signed payload built (sig {str(sig)[:18]}...)")

    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
    try:
        result = await facilitator.verify(
            payload,  # PaymentPayload
            req,      # PaymentRequirements
        )
    except Exception as e:  # noqa: BLE001
        print(f"[dryrun] facilitator /verify ERROR: {e}")
        return 2
    print(f"[dryrun] facilitator /verify -> isValid={result.is_valid} payer={result.payer}")
    print(f"[dryrun] invalid_reason={result.invalid_reason} invalid_message={result.invalid_message}")
    print(f"[dryrun] extra={result.extra}")
    if result.is_valid:
        print("[dryrun] SUCCESS — signature path fully valid; only on-chain settlement (needs funded wallet) remains.")
        return 0
    print("[dryrun] FAILED — facilitator rejected the payment payload.")
    return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
