#!/usr/bin/env python3
"""memcli — tiny CLI for the Agentic Memory API.

Reads AGENT_MEMORY_BASE_URL and AGENT_MEMORY_KEY from the environment.
The raw key is used transiently and never written anywhere.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse


def _req(method, path, body=None, query=None):
    base = os.environ.get("AGENT_MEMORY_BASE_URL", "").rstrip("/")
    key = os.environ.get("AGENT_MEMORY_KEY", "")
    if not base or not key:
        sys.exit("set AGENT_MEMORY_BASE_URL and AGENT_MEMORY_KEY")
    url = base + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {"error": f"http {e.code}"}
        return e.code, payload


def main():
    ap = argparse.ArgumentParser(prog="memcli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("store")
    p.add_argument("owner"); p.add_argument("kind"); p.add_argument("key")
    p.add_argument("value"); p.add_argument("--confidence", type=float)

    p = sub.add_parser("recall")
    p.add_argument("owner"); p.add_argument("q", default="", nargs="?")
    p.add_argument("--kind"); p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("update")
    p.add_argument("owner"); p.add_argument("key")
    p.add_argument("--value"); p.add_argument("--confidence", type=float)
    p.add_argument("--kind")

    p = sub.add_parser("forget")
    p.add_argument("owner"); p.add_argument("key")

    p = sub.add_parser("list")
    p.add_argument("owner"); p.add_argument("--kind")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("decay")
    p.add_argument("owner")
    p.add_argument("--older-than-days", type=float, default=90)
    p.add_argument("--below-confidence", type=float, default=0.4)

    a = ap.parse_args()
    if a.cmd == "store":
        code, d = _req("POST", "/api/agent-memory/store",
                       {"owner": a.owner, "kind": a.kind, "key": a.key,
                        "value": a.value, "confidence": a.confidence})
    elif a.cmd == "recall":
        code, d = _req("GET", "/api/agent-memory/recall",
                       query={"owner": a.owner, "q": a.q,
                              "kind": a.kind or "", "limit": a.limit})
    elif a.cmd == "update":
        code, d = _req("PATCH", "/api/agent-memory/update",
                       {"owner": a.owner, "key": a.key, "value": a.value,
                        "confidence": a.confidence, "kind": a.kind})
    elif a.cmd == "forget":
        code, d = _req("DELETE", "/api/agent-memory/forget",
                       {"owner": a.owner, "key": a.key})
    elif a.cmd == "list":
        code, d = _req("GET", "/api/agent-memory/list",
                       query={"owner": a.owner, "kind": a.kind or "",
                              "limit": a.limit})
    elif a.cmd == "decay":
        code, d = _req("POST", "/api/agent-memory/decay",
                       {"owner": a.owner,
                        "older_than_days": a.older_than_days,
                        "below_confidence": a.below_confidence})
    print(json.dumps(d, indent=2))
    sys.exit(0 if code < 400 else 1)


if __name__ == "__main__":
    main()
