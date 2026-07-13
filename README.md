# AEGIS — Agentic Evaluation-Gated Intelligent Support

> AEGIS is a serverless multi-agent platform that ingests support requests in any modality — email text, PDF
> attachments, screenshots, and voice notes — extracts and redacts sensitive information, retrieves grounded
> context from a versioned knowledge base, and drafts cited responses through a governed agent pipeline with
> human approval gates. A contextual-bandit reinforcement learning policy continuously learns the best routing
> strategy from human feedback, and every deployment is gated by an automated evaluation suite that blocks
> releases if groundedness or retrieval quality regresses.

**Status:** Phase 1 — Foundations & guardrails (in progress)

## Quick start

```bash
make setup      # create venv, install deps + pre-commit hooks
make test       # ruff + mypy + pytest
make package    # build the Lambda deployment artifact
make deploy     # terraform apply (requires AWS credentials + bootstrap)
make destroy    # tear everything down
```

<!-- Phase 11 will replace this stub with: architecture diagram, verified metrics table,
     demo GIF, differentiators, cost model, AI-103 syllabus mapping. -->

## Architecture

See [docs/architecture.md](docs/architecture.md) and the ADRs in [docs/decisions/](docs/decisions/).

## Build log

Phase-by-phase progress with metrics lives in [docs/build-log.md](docs/build-log.md).
