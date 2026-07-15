# Cost model

Steady-state target: **$0/month** within AWS always-free limits. The account has no promotional
credits, so the only out-of-pocket line is Bedrock once the agent layer (Phase 6) unblocks.

## Measured per-service footprint

Compute/storage/queueing all sit inside always-free allowances at demo and portfolio-review volume:

| Service | AWS free allowance | AEGIS usage | Cost |
|---|---|---|---|
| Lambda (10 functions) | 1M req + 400K GB-s / mo | ~a few K req/mo | $0 |
| DynamoDB (tickets + pii-map) | 25 GB + 25 RCU/WCU | provisioned 10/10 + 2/2 | $0 |
| SQS (ingest + 4 stage + DLQ) | 1M req / mo | thousands / mo | $0 |
| S3 (knowledge, intake, tfstate) | 5 GB | < 100 MB | $0 |
| API Gateway HTTP API | 1M req / mo (first 12 mo) | thousands / mo | ~$0 |
| CloudWatch (logs + 1 dashboard + alarms) | 5 GB logs, 3 dashboards, 10 alarms | 1 dashboard, 2 alarms | $0 |
| ECR (5 container images) | 500 MB (first 12 mo) | ~4.5 GB* | see note |
| Bedrock Nova Micro/Lite | none | **pending quota** | est. below |

\* ECR is the one line that can exceed free tier: five arm64 images (kb_query, enrich_nlp,
extract_text, transcribe_audio share layers) total ~4.5 GB. At $0.10/GB-mo that's **~$0.45/mo** —
lifecycle policy keeps only the 2 newest tags per repo. This is the real steady-state cost today.

## Projected Bedrock cost (when Phase 6 lands)

Nova pricing: Micro $0.035/1M input + $0.14/1M output; Lite $0.06/1M input + $0.24/1M output.
A governed ticket ≈ triage (Micro, ~1K in / 0.2K out) + research (Lite, ~4K in / 0.5K out) +
drafting (Lite, ~3K in / 0.5K out) ≈ **~$0.0007 / ticket**.

| Volume | Bedrock cost |
|---|---|
| 1,000 tickets | ~$0.70 |
| 10,000 tickets | ~$7 |
| whole build (dev + evals + 2K episodes) | **< $15 total** |

The eval suite's LLM-judge calls are cached by (draft-hash, chunk-hash) and the full suite runs only
on merge, so eval cost stays a rounding error.

## Scaling thresholds (where the architecture changes)

- **FAISS → OpenSearch Serverless** when the KB exceeds ~200 MB / ~100K chunks or updates must be
  visible in < minutes (ADR-002). Adds ~$350/mo — deliberately deferred.
- **DynamoDB provisioned → on-demand** past ~200M req/mo.
- **Lambda → Fargate** for the container stages if sustained throughput makes cold starts unacceptable
  (ADR-001); today the async pipeline absorbs them.

## Budget guardrail

AWS Budgets alarms at $5 and $20 (Phase 1) plus a $1 zero-spend budget. Any real spend emails within
a day — the tripwire that keeps "$0/mo" honest.
