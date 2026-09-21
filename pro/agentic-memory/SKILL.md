---
name: agentic_memory
description: "Gives an AI agent durable cross-task memory: store facts, preferences, outcomes, and lessons; recall them before acting; update, forget, and decay old memories. Use when an agent needs to remember things across tasks or sessions instead of starting blank every time."
---

# Agentic Memory

## Purpose

Task-local history dies when the task ends. This skill gives an agent a
persistent memory: a namespaced key-value store of facts, preferences,
outcomes, lessons, and goals with confidence scores, keyword recall, and
stale-memory decay. The agent stores what it learns, recalls it before
acting, and prunes what no longer holds. Triggers on "remember this,"
"agent memory," "cross-task memory," "what did I learn," or when an agent
needs continuity across tasks.

## Tooling

The memory service is an HTTP API. Two namespaces exist per agent:
your own handle (private) and `shared` (readable by every agent).

- `POST /api/agent-memory/store` — upsert one memory.
  `{owner, kind, key, value, confidence?}` where kind ∈
  fact | preference | outcome | lesson | goal, confidence ∈ [0,1].
- `GET /api/agent-memory/recall?owner=&q=&kind=&limit=` — keyword
  search; every query token must appear in key+value; newest first.
- `PATCH /api/agent-memory/update` — `{owner, key, value?, confidence?,
  kind?}` on an existing memory (404 if missing).
- `DELETE /api/agent-memory/forget` — `{owner, key}` (404 if missing).
- `GET /api/agent-memory/list?owner=&kind=&limit=` — dump a namespace.
- `POST /api/agent-memory/decay` —
  `{owner, older_than_days?=90, below_confidence?=0.4}` — prunes memories
  that are BOTH stale and low-confidence. Returns `{pruned: n}`.

Full endpoint table with curl examples: `references/api-reference.md`.
A `bin/memcli` helper wraps the calls; it reads `AGENT_MEMORY_BASE_URL`
and `AGENT_MEMORY_KEY` from the environment.

## Auth

Bearer <redacted> in the `Authorization` header (a per-agent pilot key), or a
human web session. A key for handle H may read/write owner H and owner
`shared`; touching another agent's namespace returns 403. Humans may
access all owners. Rate limits are per-key; a 429 means back off.

## Operating Rules

1. **Recall before you act.** At the start of a task, recall your own
   namespace and `shared` with 2–3 query terms relevant to the task.
   Memory you never read is write-only cost.
2. **Store small, store true.** One fact per key (`deploy-freeze`,
   `user-tz`, `pref-brief-replies`). Values ≤ a sentence or two.
   Never store secrets, credentials, or full PII.
3. **Confidence is a promise.** 1.0 = verified by observation; 0.5–0.8 =
   inferred or told once; below 0.5 = guess — decay will eat it.
   Downgrade confidence when contradicted; don't delete and rewrite.
4. **Shared is for everyone.** Put genuinely reusable lessons in
   `shared` (rate-limit behavior, API quirks). Keep user-specific or
   tentative things in your own namespace.
5. **Update, don't duplicate.** If a memory exists and the fact changed,
   PATCH it. Duplicate keys across slightly different names are recall
   poison — check `list` before inventing a new key.
6. **Decay on a schedule.** Run decay monthly (or when the namespace
   passes ~200 memories). Never decay someone else's namespace.
7. **Forget on request, immediately.** A human's "forget that" is a
   DELETE, not a confidence change. Confirm once, then do it.
