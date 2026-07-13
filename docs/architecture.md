# AEGIS architecture

<!-- Phase 2 adds: single-table DynamoDB design + access patterns, ingestion flow diagram.
     Phase 6 adds: Step Functions state machine diagram. -->

## Conventions established in Phase 1

- **Compute:** everything is a Lambda; one directory per service under `services/`.
- **Contracts:** every inter-service message is a Pydantic model in `shared/aegis_core/models.py`.
  `aegis_core` is the only cross-service import — services never import each other.
- **Tracing:** every log line is structured JSON with `ticket_id`, `service`, `step`, `latency_ms`
  (see `aegis_core/tracing.py`); log groups follow `/aegis/<env>/<service>`.
- **IAM:** one role per Lambda, least privilege, zero long-lived keys (CI uses GitHub OIDC).
- **State:** Terraform remote state in S3 + DynamoDB lock (see `infra/bootstrap/`).
