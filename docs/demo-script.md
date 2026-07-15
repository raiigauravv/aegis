# AEGIS demo video script (2:30–3:00)

Format follows the Paires cadence. Record against the live endpoint.

## 0:00–0:30 — Problem & architecture
- "Support teams drown in multi-modal requests — email, PDFs, screenshots, voice notes — and every
  AI reply to a banking customer is a compliance risk."
- Show the architecture diagram (README). "Serverless, multi-agent, fully traced. Ten Lambdas,
  every message a typed contract."

## 0:30–1:30 — A messy ticket flows live
- Submit a ticket with an angry tone + PII: *"I was charged twice and I suspect fraud! My card is
  4111 1111 1111 1111, call me at 416-555-0134."*
- Watch the trace timeline populate: intake → enrich. Point out: **PII redacted to placeholders
  before storage**, sentiment negative, **risk tier 3**, routed to the human queue — not the bandit.
- Drop a PDF invoice and a voice note into the intake bucket; show both rejoining the same pipeline
  (OCR text / transcript), redacted and enriched.
- Switch to KB search tab: ask *"what are the e-transfer limits?"* → cited chunks with doc/section/
  version. Then ask something not in the KB → **"insufficient knowledge"** (fabrication defense).

## 1:30–2:00 — Governance
- POST to `/mcp` as the drafting agent trying to read customer data → **denied, −32001**, and show
  the `allowlist_denial` security event in the ticket's `/audit` trail.
- Invoke the moderation gate on a leaky, uncited draft → **blocked** with reasons.
- "This is the answer to 'how would you make this safe for a bank' — I show the audit endpoint and
  the adversarial suite instead of talking hypotheticals. 20 of 20 attack cases blocked."

## 2:00–2:45 — The learning loop + the eval gate
- Show the offline regret curve: **LinUCB beats random by 85.8%**. Then the online curve: reward
  climbing 0.53 → 0.72 over 298 episodes **on production infrastructure**.
- Show a CI run where a deliberately-broken index change drops hit@3 to 0.75 and the
  **eval gate blocks the deploy** (red X). Restore → green.

## 2:45–3:00 — Close
- Metrics slide (README table). "$0.45/month steady-state. Every number on screen is emitted by the
  system and regenerable by a script."

## The one honesty note to say out loud
"The three reasoning agents are scaffolded and waiting on a Bedrock quota unblock on my account —
everything they plug into is live. I built the hard, differentiated 90%: the governance, the RL, the
eval gate."
