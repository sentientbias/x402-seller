# Agentic Memory API — Reference

Base URL is deployment-specific (pilot: the MuseFM app origin).
All calls: `Authorization: Bearer <AGENT_MEMORY_KEY>`,
`Content-Type: application/json`.

## Endpoints

| Method | Path | Body / params | Success | Errors |
|---|---|---|---|---|
| POST | /api/agent-memory/store | `{owner, kind, key, value, confidence?}` | 200 `{ok, memory}` | 400 validation, 403 scope, 401 auth |
| GET | /api/agent-memory/recall | `?owner=&q=&kind=&limit=` (def 20, max 100) | 200 `{ok, owner, memories[]}` | 400, 403, 401 |
| PATCH | /api/agent-memory/update | `{owner, key, value?, confidence?, kind?}` | 200 `{ok, memory}` | 400, 403, 401, 404 |
| DELETE | /api/agent-memory/forget | `{owner, key}` | 200 `{ok: true}` | 400, 403, 401, 404 |
| GET | /api/agent-memory/list | `?owner=&kind=&limit=` (def 50, max 200) | 200 `{ok, owner, memories[]}` | 400, 403, 401 |
| POST | /api/agent-memory/decay | `{owner, older_than_days?=90, below_confidence?=0.4}` | 200 `{ok, pruned}` | 400, 403, 401 |

`kind` ∈ `fact | preference | outcome | lesson | goal`.
`owner` ∈ your handle | `shared` (lowercase `[a-z0-9][a-z0-9_-]{0,39}`).
`confidence` ∈ [0,1], default 1.0. `key` ≤ 120 chars, `value` ≤ 4000 chars.
Banned-word filter applies to values. Every mutation is audit-logged.

## Memory object

```json
{
  "id": 12, "owner": "pebble", "kind": "lesson",
  "key": "rate-limit-backoff",
  "value": "On 429, wait 60s before retrying the same bucket.",
  "confidence": 0.9,
  "created_at": 1758326400, "updated_at": 1758326400
}
```

## curl examples

Store:
```bash
curl -s -X POST "$BASE/api/agent-memory/store" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"owner":"pebble","kind":"lesson","key":"rate-limit-backoff",
       "value":"On 429, wait 60s before retrying the same bucket.",
       "confidence":0.9}'
```

Recall before a task:
```bash
curl -s -G "$BASE/api/agent-memory/recall" \
  -H "Authorization: Bearer $KEY" \
  --data-urlencode "owner=pebble" --data-urlencode "q=deploy friday" \
  --data-urlencode "limit=5"
```

Update confidence after a contradiction:
```bash
curl -s -X PATCH "$BASE/api/agent-memory/update" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"owner":"pebble","key":"rate-limit-backoff","confidence":0.4}'
```

Forget on request:
```bash
curl -s -X DELETE "$BASE/api/agent-memory/forget" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"owner":"pebble","key":"rate-limit-backoff"}'
```

Monthly decay:
```bash
curl -s -X POST "$BASE/api/agent-memory/decay" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"owner":"pebble","older_than_days":90,"below_confidence":0.4}'
```

## Using bin/memcli

```bash
export AGENT_MEMORY_BASE_URL="https://your-app.example"
export AGENT_MEMORY_KEY="wrp_..."
python3 bin/memcli.py store pebble lesson rate-limit-backoff \
  "On 429, wait 60s before retrying." --confidence 0.9
python3 bin/memcli.py recall pebble "deploy friday" --limit 5
python3 bin/memcli.py update pebble rate-limit-backoff --confidence 0.4
python3 bin/memcli.py forget pebble rate-limit-backoff
python3 bin/memcli.py decay pebble --older-than-days 90 --below-confidence 0.4
```
