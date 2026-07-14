# Governance

The layer that makes AEGIS auditable. Everything here is ENFORCED in code, not
requested in prompts.

## Tool allowlists (enforced in mcp_tools, server-side)

Source of truth: `services/mcp_tools/allowlists.yaml` (baked into the deploy artifact;
changes go through PR review).

| Agent | search_knowledge_base | get_ticket_history | extract_entities | check_customer_context |
|---|---|---|---|---|
| triage_agent | ✗ | ✗ | ✓ | ✗ |
| research_agent | ✓ | ✓ | ✓ | ✓ |
| drafting_agent | ✗ | ✗ | ✗ | ✗ (drafts ONLY from its ResearchBundle) |
| approval_ui | ✗ | ✓ | ✗ | ✗ |

A denial returns JSON-RPC error −32001 AND writes an `allowlist_denial` security event to the
ticket trace with agent + tool attribution.

## Moderation gate (before any draft is released)

Deterministic checks in `moderation_gate` (Presidio stack, same image as enrich):
1. **PII leakage** — detection re-run on the OUTPUT; any hit blocks.
2. **Unsupported claims** — fact-bearing sentences (amounts, timelines, limits) without a
   `[n]` citation marker block.
3. **Policy phrases** — guarantees / legal-advice language block.
Verdicts land in the trace; a blocked draft is an auditable event.

## Risk-tiered approval

| Tier | Trigger | Path |
|---|---|---|
| 1 | default | auto-flow (bandit-routed once agents ship) |
| 2 | sentiment ≤ −0.6 | bandit may choose escalate_human |
| 3 | fraud/legal/account-closure keywords | **mandatory human approval; bypasses the bandit entirely** |

Tier assignment is currently the deterministic floor in enrich_nlp; the LLM triage agent
(pending Bedrock) becomes the primary signal with this floor kept as backstop.
Approval decisions are FEEDBACK items → they ARE the bandit's reward signal (ADR-004).

## Audit trail

`GET /tickets/{id}/audit` returns the complete decision chain: every pipeline step with
latency and detail, routing decision, moderation verdict, and every human action.

## PII handling

Redact-before-persist; numbered placeholders; reversible map in a separate SSE table whose
IAM policy allows exactly one writer (enrich_nlp) and zero readers. Raw uploads expire from
the intake bucket after 14 days. Privacy-by-design informed by PIPEDA principles — no formal
compliance claim.
