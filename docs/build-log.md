# AEGIS build log

One entry per phase. These entries become the demo-video script and interview stories.

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
