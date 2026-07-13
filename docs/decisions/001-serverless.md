# ADR-001: Serverless (Lambda + Step Functions) over containers/Kubernetes

**Status:** Accepted · 2026-07-13

## Context

AEGIS processes support tickets — a spiky, event-driven workload (bursts on ticket arrival, idle
otherwise). Budget target is $0/month steady-state on AWS always-free limits. The team is one person
who also owns infra, so operational surface must stay small. A prior project (NEXUS-AI) already
demonstrates Docker Compose / long-running-service depth, so this project should add range, not repeat it.

## Decision

All compute runs on Lambda (container images for heavy paths: OCR, Whisper, embeddings). Multi-agent
orchestration uses Step Functions Standard. Public endpoints use Lambda Function URLs (free) instead of
API Gateway where auth needs allow.

## Consequences

- Free tier covers the workload: 1M Lambda requests + 400K GB-s and 4K state transitions/month.
- Zero idle cost, zero server patching; per-service IAM roles give least-privilege by construction.
- Cold starts on container Lambdas (Whisper/OCR ≈ 10–15 s) are acceptable in an async pipeline and
  documented; provisioned concurrency is the at-scale answer, deliberately not used here.
- Step Functions free tier (~8–10 transitions/ticket ⇒ ~400 free tickets/month) means load tests use
  Express workflows or batched demos.
- 15-minute Lambda cap bounds any single step; long work must decompose into states — which also makes
  every step visible in the trace.

## Scaling path (interview answer)

Sustained high throughput → move hot paths to Fargate behind SQS; keep Step Functions as the
orchestrator. The typed Pydantic contracts make services transplantable.
