# AEGIS build log

One entry per phase. These entries become the demo-video script and interview stories.

> Phases 3-9 were built out of playbook order while AWS support case 178397104900264
> (Bedrock quota zeroed on this account) resolves. Everything below is Bedrock-free;
> each entry lists what remains gated on the LLM path.

## Phase 5 — Knowledge base & RAG (2026-07-13) · tag `v0.2-knowledge`

16 NorthStar Banking docs (auth, payments, cards, fees, mortgage, wires, release notes), heading-aware
chunking (43 chunks with doc/section/version/effective_date provenance), MiniLM embeddings via
fastembed/ONNX, FAISS index versioned+immutable in S3 (`index/v<N>/`), kb_query container Lambda
(arm64) behind GET /kb/search with score-threshold → `insufficient_knowledge` fabrication defense.
**Measured:** hit@3 0.938, MRR 0.893 on 65 golden pairs (28 written in casual user voice, no shared
vocabulary). Warm search 229ms; cold ~3s after swapping torch→ONNX (torch import alone blew the 60s
budget — good war story) and 2048→3008MB. **Pending Bedrock:** nothing.

## Phase 4 — Text analysis & PII redaction, non-LLM scope (2026-07-13) · tag `v0.3-enrichment`

enrich_nlp container: langdetect + VADER sentiment + Presidio(spaCy sm, pinned — the default lg tried
to pip-install at runtime inside Lambda, second war story) with custom Canadian recognizers: SIN with
real Luhn validation, postal codes. Redaction to numbered placeholders BEFORE persistence; reversible
map in a separate SSE table writable by exactly one role, readable by none. Deterministic risk-tier
floor (fraud/legal keywords → tier 3 → awaiting_approval). Voice path: faster-whisper small/int8
container, transcript rejoins the text flow. **Measured:** redaction P/R = 1.00/1.00 on the 50-case
suite (structured PII: SIN/postal/phone/email/card; Luhn kills the decoys). Live multimodal proof:
text+PII ticket fully redacted with tier-3 route; TTS voice note transcribed near-verbatim.
**Pending Bedrock:** intent classification (slot reserved, `intent=pending_bedrock`).

## Phase 3 — Extraction, classical half (2026-07-13) · tag `v0.4-extraction-ocr`

extract_text container: pdfplumber for born-digital PDFs (text-layer heuristic), Tesseract for
images/scans, confidence recorded per doc. Benchmark harness pushes labeled synthetic invoices
through the LIVE pipeline and scores field accuracy from what actually persisted.
**Measured (20 docs):** pdf_text 100% fields @ 72ms median; Tesseract OCR 100% @ 1.1s median —
clean synthetics; noisy-scan set and the Nova Lite multimodal column are the Bedrock-gated half,
harness ready to add the column.

## Phase 7 — Governance (2026-07-14) · tag `v0.6-governance`

mcp_tools server (JSON-RPC tools/list + tools/call, patterns from OpenHive PRs #6963/#6818) with
YAML allowlists enforced SERVER-SIDE: drafting_agent calling check_customer_context gets error
−32001 AND an `allowlist_denial` security event in the ticket trace (verified live). Moderation
gate (same image as enrich, CMD override): PII-on-output + uncited-claim heuristic + policy
phrases — verified catching all three on a hostile draft. Risk-tiered approval queue in the
frontend; decisions are FEEDBACK items feeding the bandit. `GET /tickets/{id}/audit` returns the
full decision chain. **Adversarial suite: 20/20 blocked** (3 text injections + 1 PDF-carried
injection inert; 4 PII baits redacted; 4 contract rejects; tier-3 human-only + bandit bypass;
3 MCP allowlist cases; moderation block). Found+fixed: DynamoDB Scan Limit pre-filters (approval
queue pagination). **Pending Bedrock:** the agents these guardrails wrap.

## Phase 8 (online half) — bandit in production (2026-07-14) · tag `v0.5-bandit`

bandit_policy Lambda serves LinUCB from DynamoDB sufficient statistics (PK=BANDIT SK=ARM#i);
feedback queue → reward updates; nightly EventBridge snapshot to S3 (replayable policy history).
Tier-3 bypass enforced at the policy layer. **Measured: 298 live episodes through the production
pipeline** (real Lambdas/DynamoDB/SQS, synthetic user with the ADR-004 preference model): mean
reward 0.53 (first 50) → 0.72 (last 50), cumulative 192 — the deployed policy learned online.
Curves: `bandit/notebooks/online_learning.png`.

## Phase 9 — Evaluation-gated CI (2026-07-14) · tag `v0.7-eval-gate`

`eval-gate` CI job: retrieval + redaction recomputed from scratch each run; extraction +
adversarial from their latest live-infra runs; ANY metric below `evals/thresholds.yaml` blocks
the terraform deploy job (needs: [quality, eval-gate]). Nightly cron re-runs the gate.
**Demonstrated block:** a simulated ingestion bug (headings-only index) dropped hit@3 to 0.754 →
`EVAL GATE FAILED [retrieval.hit_at_3, retrieval.mrr]`, deploy refused; restore → green. Also
notable: 8-word chunk truncation did NOT break the gate (hit@3 0.92) — the golden set caught the
severity difference correctly. **Pending Bedrock:** groundedness LLM-judge, fabrication canaries.

## Phase 8 (offline half) — LinUCB bandit (2026-07-13)

LinUCB from scratch (~70 lines, disjoint linear models, DynamoDB-serializable sufficient
statistics), unit-tested (convergence, exploration bonus, state round-trip). Simulator with
structured context-dependent rewards mapped to the ADR-004 feedback levels.
**Measured (2,000 rounds × 20 seeds):** cumulative regret 84.6 (LinUCB) vs 330.3 (ε-greedy 0.1)
vs 595.6 (random) — 85.8% regret reduction, clearly sublinear curve committed as
`bandit/notebooks/regret_curves.png`. Online serving loop lands with governance below.

## Phase 2 — Ingestion spine (2026-07-13) · tag `v0.1-ingestion`

Text tickets flow POST /tickets → SQS → intake_router → DynamoDB single-table (PK=TICKET#id,
SK=META|TRACE#ts) with idempotent conditional writes; S3 file drops enter the same queue and park
as `awaiting_extraction` for Phase 3. DLQ + depth alarm wired (alarm #1). Frontend submits and
renders the live trace timeline. New reusable Terraform `lambda_service` module (role-per-function,
least privilege).

**Load test (500 tickets, measured):** POST p50 117ms / p95 1.46s; end-to-end (submit→persisted)
p50 118ms / p95 1.26s / max 3.0s; **zero DLQ entries**; 151 client retries against the account's
10-concurrent-execution cap at 8 parallel submitters (~28 tickets/s sustained) — SQS absorbed the
burst, nothing dropped. 2,080 items in the table after ~1,000 test tickets.

## Phase 1 — Foundations & guardrails (started 2026-07-13)

Repo scaffolded with the full module layout, `aegis_core` (typed contracts + structured JSON tracing,
unit-tested), Terraform bootstrap + observability module + hello-world Lambda, CI (ruff → mypy →
pytest → terraform plan/apply via OIDC), ADR-001/002 committed.

Deployed to account 490004650850 (existing account, no credits): budgets at $5/$20 created alongside
the pre-existing $1 zero-spend budget; `make bootstrap` + `make deploy` succeeded; live endpoint
`GET /hello` returns 200 with a full structured trace in CloudWatch (`/aegis/dev/hello_world`).
Two real bugs found and fixed en route: macOS-native wheels in the Lambda zip (fixed with
`pip --platform manylinux2014_x86_64`), and account-level 403s on ALL public Function URLs — this
account is under new-account abuse controls (Bedrock quotas 0 TPM, Lambda concurrency capped at 10),
so public endpoints moved to API Gateway HTTP API (ADR-003).
Repo pushed to github.com/raiigauravv/aegis; CI green end-to-end (quality + terraform jobs), with
deploys via OIDC role `aegis-ci-deploy` (trust scoped to this repo; PowerUserAccess + IAM limited
to `aegis-*` roles). Tagged `v0.0-foundations`.
**Carried forward:** budget-alarm email will be observed when the first cent bills (zero-spend
budget covers this); AWS support case **178397104900264** (filed 2026-07-13, Account → Other
Account Issues) to lift Bedrock 0-TPM quotas / Lambda concurrency 10 — needed by Phase 3, not before.
