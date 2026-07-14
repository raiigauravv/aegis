# ADR-004: Bandit problem formulation and reward design

**Status:** Accepted · 2026-07-14

## Why a contextual bandit, not full RL

Routing a ticket is a single decision with (near-)immediate feedback — approve/edit/reject
arrives within one episode and the next ticket's state does not depend on this ticket's action.
No credit-assignment over trajectories ⇒ a contextual bandit is the honest formulation; a full
MDP would be résumé-driven over-modeling.

## Arms

`fast_draft` (cheap model, k=3 retrieval) · `deep_research` (bigger model, k=8 + history tool) ·
`clarify_first` (ask the customer) · `escalate_human`.

## Reward (from human feedback on the outcome)

| Outcome | Reward |
|---|---|
| approved unedited | +1.0 |
| approved with light edit | +0.5 |
| heavy edit before send | 0.0 |
| rejected | −0.5 |
| escalation after auto-send | −1.0 |

Design tradeoffs: the reward measures *human trust in the draft*, not resolution time — optimizing
speed alone would teach the bandit to always fast-draft. The asymmetry (−1 for bad auto-send vs
−0.5 for rejection) prices reputational risk above wasted work. A small latency penalty is applied
at learning time so equal-quality arms prefer the cheaper path.

## Safety constraints on exploration

- **Tier-3 tickets bypass the bandit entirely** (governance > optimization).
- α=1.0 initially; exploration narrows as sufficient statistics accumulate — no ε floor that
  would randomly route angry customers forever.
- Policy state snapshots nightly to S3 (versioned) so any decision is replayable and the policy
  can be rolled back like code.
