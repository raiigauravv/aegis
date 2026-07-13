# ADR-003: API Gateway HTTP API over Lambda Function URLs

**Status:** Accepted · 2026-07-13

## Context

The playbook allowed either Function URLs (free) or API Gateway HTTP API for public endpoints, and
preferred Function URLs on cost. In practice, this AWS account (490004650850) is under new-account
abuse controls: Bedrock on-demand quotas are 0 TPM, Lambda account concurrency is capped at 10
(default is 1,000), and **all Function URL invocations return 403 AccessDeniedException** — verified
with a minimal repro function carrying a textbook-correct public-invoke resource policy, for both
anonymous and SigV4-signed requests. A parallel repro through API Gateway HTTP API returned 200.

## Decision

All public endpoints go through one API Gateway HTTP API (`$default` stage, auto-deploy) with
`AWS_PROXY` integrations per route. Function URLs are not used.

## Consequences

- Cost: HTTP API is $1.00/M requests after the 12-month free tier — effectively $0 at demo volume;
  noted in `docs/cost-model.md`.
- Bonus over Function URLs: routes, throttling, and per-stage metrics come free, which Phase 2's
  `POST /tickets` and Phase 7's audit endpoint will use anyway.
- A support case to lift the account restrictions is open/pending; even if Function URLs start
  working, we stay on HTTP API for the route/throttle features.
