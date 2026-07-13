# Governance

<!-- Phase 7 fills this in: per-agent tool allowlists (enforced by the MCP server),
     moderation thresholds, risk-tiered approval policy, audit-trail contract. -->

## In force since Phase 1

- One IAM role per Lambda, scoped to exactly the resources it touches.
- No long-lived credentials anywhere (local: SSO/short-lived keys; CI: GitHub OIDC).
- AWS Budgets alarms at $5 and $20 precede all other infrastructure.
