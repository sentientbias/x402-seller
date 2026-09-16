"""Exchange Pro pass verification (seller side).

Pro passes are ed25519-signed bearer tokens minted by the Skill Exchange API
(see core/propass.py there). Format: ``sp1.<b64url(payload)>.<b64url(sig)>``,
where the signature covers the ASCII bytes of the middle segment.

The seller only ever holds the PUBLIC key (PROPASS_VERIFY_KEY env var, with a
hardcoded default below). A valid, unexpired signature means the Exchange API
issued this pass -- it cannot be forged without the private key, which never
leaves the Exchange host.

v1 semantics: signature + expiry is enough. The handle is bound inside the
signed payload (sharing the token shares the identity -- non-transferable by
design). No revocation list in v1; passes live 90 days.
"""
from __future__ import annotations

import base64
import binascii
import json
import time

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

TOKEN_PREFIX = "sp1"


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def verify_pro_pass(token: str, verify_key_hex: str) -> dict | None:
    """Verify a pro-pass token. Returns the payload dict, or None if the
    token is malformed, has a bad signature, or is expired."""
    try:
        prefix, payload_b64, sig_b64 = (token or "").strip().split(".")
        if prefix != TOKEN_PREFIX:
            return None
        verify_key = VerifyKey(bytes.fromhex(verify_key_hex.strip()))
        verify_key.verify(payload_b64.encode("ascii"), _b64d(sig_b64))
        payload = json.loads(_b64d(payload_b64))
    except (BadSignatureError, ValueError, binascii.Error, KeyError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("v") != 1:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(time.time()):
        return None
    if not payload.get("handle") or not payload.get("pid"):
        return None
    return payload
