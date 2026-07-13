# AEGIS build log

One entry per phase. These entries become the demo-video script and interview stories.

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
**Pending for DoD:** GitHub repo pushed + OIDC role so CI runs green; budget-alarm email observed;
AWS support case **178397104900264** (filed 2026-07-13, Account → Other Account Issues) to lift
Bedrock/concurrency limits — needed by Phase 3, not before.
