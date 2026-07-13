# AEGIS architecture

<!-- Phase 6 adds: Step Functions state machine diagram. -->

## Ingestion spine (Phase 2)

```
POST /tickets ──> ticket_api ──> SQS aegis-<env>-ingest ──> intake_router ──> DynamoDB
S3 intake bucket (file drops) ──┘        │ (3 strikes)
                                         └──> DLQ ──> CloudWatch alarm
GET /tickets/{id} ──> ticket_api ──────────────────────────> DynamoDB (query PK)
```

The API only enqueues (async write path); `intake_router` owns persistence. SQS absorbs bursts
beyond the account's Lambda concurrency cap, retries transient failures with backoff, and
dead-letters poison messages after 3 attempts.

## DynamoDB single-table design

Table `aegis-<env>-tickets` — `PK` (hash), `SK` (range), provisioned 10/10 RCU/WCU (always-free).

| Item | PK | SK | Body |
|---|---|---|---|
| Ticket state | `TICKET#<id>` | `META` | `TicketMeta` (status, channel, modality, text, source) |
| Decision chain | `TICKET#<id>` | `TRACE#<iso-ts>#<nonce>` | `TraceEvent` (service, step, latency_ms, detail) |
| Human feedback | `TICKET#<id>` | `FEEDBACK#<iso-ts>` | Phase 7/8 |

Access patterns:

1. **Get ticket + full trace** — `Query PK = TICKET#<id>` (one RCU-cheap query returns META and
   all TRACE items in SK order; the trace timeline is free).
2. **Create ticket idempotently** — conditional `PutItem` on `attribute_not_exists(SK)`; SQS
   at-least-once redelivery cannot duplicate a ticket.
3. **Append trace step** — plain `PutItem`; ts+nonce in SK prevents collisions.

No GSIs yet: list-by-status arrives with the approval queue (Phase 7) and will be a sparse GSI.

## Conventions established in Phase 1

- **Compute:** everything is a Lambda; one directory per service under `services/`.
- **Contracts:** every inter-service message is a Pydantic model in `shared/aegis_core/models.py`.
  `aegis_core` is the only cross-service import — services never import each other.
- **Tracing:** every log line is structured JSON with `ticket_id`, `service`, `step`, `latency_ms`
  (see `aegis_core/tracing.py`); log groups follow `/aegis/<env>/<service>`.
- **IAM:** one role per Lambda, least privilege, zero long-lived keys (CI uses GitHub OIDC).
- **State:** Terraform remote state in S3 + DynamoDB lock (see `infra/bootstrap/`).
