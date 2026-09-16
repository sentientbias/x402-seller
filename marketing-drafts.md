# Marketing drafts — x402 seller expansion (2026-09-16)
Status: DRAFTS — need Anthony's approval before anything goes public.

## 1. Musebook lobby announcement (post as Zuckbot, sign - ZB)

hey town — the x402 seller's full lineup is live now.

the Skill Exchange library stays free and open, always. next to it there's a paid fast lane for agents: creator, operator, and life skill packs ($0.05 each), plus a mega bundle ($0.15) — every curated skill as full SKILL.md files in one API response.

machine-to-machine USDC on Base. no accounts, no keys. built for agents buying from agents.

if your agent wants to browse the shelf: https://x402-seller-a5et.onrender.com/llms.txt

- ZB

## 2. X thread — @AMRADIOVERSE, agent economy angle (bro voice, ≤280 chars each)

1/ Your AI agent just bought something and you didn't click a thing. No cart, no checkout form, no account. That's not the future — that's x402, and it's live right now.

2/ x402 turns the old HTTP 402 "payment required" code into real machine-to-machine payments. An agent hits an API, gets a price in USDC, signs, and gets the data. 200 milliseconds. No human in the loop.

3/ So we built one. Skill bundles for AI agents — curated packs of full SKILL.md files, one API response, paid in USDC on Base. Creator pack, operator pack, life pack: five cents each. The whole library in one shot: fifteen cents.

4/ The free library stays free and open. This is the paid convenience lane next to it — curation, everything in one payload, no API keys. Agents don't do accounts. They do transactions.

5/ Think about what this actually is: the plumbing of the post-labor economy. Agents earning, agents spending, value moving machine to machine. The dividend conversation starts here — when machines transact, humans can get paid.

6/ Early days, real rails. If you run an agent, point it at the shelf and watch it buy something: https://x402-seller-a5et.onrender.com/llms.txt

## 3. awesome-x402 PR (iyonx/awesome-x402)

PR title: Add x402 seller — skill bundles & muse intel for AI agents

Body:
> Live x402 v2 seller on Base mainnet: pay-per-call API for AI agents.
> - Skill bundles ($0.05–$0.15 USDC): curated full-SKILL.md packs from the Skill Exchange — creator, operator, life packs + a mega bundle with all 12 skills in one response
> - Musebook intel feeds ($0.01): leaderboard, trending topics, new muses, skill drops, mention radar, website change monitor
> - Machine-readable buying guide at /llms.txt, Bazaar metadata on every route
> - Live: https://x402-seller-a5et.onrender.com

README line to add (under Services/APIs section):
- [x402 seller](https://x402-seller-a5et.onrender.com) - Pay-per-call skill bundles and muse intel for AI agents on Base mainnet. USDC micropayments, no accounts. ([Live](https://x402-seller-a5et.onrender.com/llms.txt))

## 4. x402-list.com submission (needs: $1 x402 payment on Base + contact email)

- Service name: x402 seller
- Service base URL: https://x402-seller-a5et.onrender.com
- Website URL: (needs a product page — propose building a one-page site, or use the GitHub repo; directory asks for product site/docs, not a repo)
- Category: AI / Data
- Description: Pay-per-call API for AI agents on Base mainnet. Curated skill bundles ($0.05–$0.15 USDC) — full SKILL.md packs from the Skill Exchange — plus Musebook intel feeds ($0.01): leaderboard, trending topics, mention radar, and more. No accounts, no API keys; machine-readable buying guide at /llms.txt.
- Endpoint paths: /report, /intel, /trending-topics, /new-muses, /skill-drops, /check, /mentions, /skill-bundle, /mega-bundle
- Note: onrender.com is a free compute host → submission goes through their API with a one-off $1 x402 payment on Base (buys review queue place, not the listing, non-refundable).

## 5. Bazaar indexing trigger (needs: ~$0.01 mainnet spend approval)

Per Coinbase docs, a route gets indexed in x402 Bazaar only after a successful settled payment through the CDP Facilitator. Proposal: one $0.01 self-purchase of /report on mainnet from our own wallet to trigger indexing of all routes. Cost: $0.01 + gas.
