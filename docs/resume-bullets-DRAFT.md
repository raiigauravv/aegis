# Resume bullets — DRAFT (review against ground-truth before shipping)

⚠️ Per the build protocol: these are drafts. Bring them back against your ground-truth metrics
file before anything goes on the resume. Every number below is system-emitted and reproducible, but
you own the final wording and the honesty pass (no leading numbers, no repeated opening verbs, fresh
build per role).

## Candidate bullets (pick 4–5, tailor per role)

- Engineered a serverless multi-agent support platform on AWS (Lambda, DynamoDB, SQS, API Gateway,
  Bedrock) processing text, PDF, image, and voice tickets through a fully-traced pipeline, sustaining
  a 1,000-ticket load at 1.37 s end-to-end p95 with zero dropped messages.

- Built an online contextual-bandit (LinUCB, from scratch) that learns ticket-routing policy from
  human feedback in production, cutting cumulative regret 85.8% versus random routing across 40,000
  simulated decisions and improving live reward 0.53 → 0.72 over 298 real episodes.

- Shipped a governance layer for LLM safety — server-side tool allowlists, a moderation gate
  re-screening every draft for PII leakage and uncited claims, and provenance-tagged audit trails —
  blocking 20 of 20 adversarial cases including document-borne prompt injection.

- Implemented privacy-by-design PII redaction (Microsoft Presidio + custom Canadian SIN/postal
  recognizers with Luhn validation) achieving 1.00 precision/recall on a 50-case suite, with
  reversible mappings fenced to a single IAM principal.

- Delivered evaluation-gated CI/CD that blocks any deploy regressing retrieval, redaction, or safety
  below threshold, with grounded RAG retrieval at 0.94 hit@3 over a hand-labeled golden set.

- Benchmarked classical OCR against a multimodal path on identical documents through the production
  pipeline, reporting measured field accuracy, latency, and cost-per-document rather than opinion.

## Talking points these unlock (15+)

single-table DynamoDB design · SQS partial-batch failures + DLQ + idempotent writes · container vs
zip Lambda tradeoffs · FAISS-vs-OpenSearch scaling threshold · fastembed/ONNX vs torch cold-start
war story · redact-before-persist + fenced re-identification map (PIPEDA-informed) · LinUCB reward
design tradeoffs · exploration safety (tier-3 bypass) · MCP allowlist enforcement · eval-gate
philosophy · GitHub OIDC keyless deploys · FinOps cost model · new-account restriction diagnosis
(Function URL 403 → API Gateway, ADR-003).
