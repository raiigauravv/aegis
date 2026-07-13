# Cost model

<!-- Phase 10 fills this with MEASURED numbers: cost per 1,000 tickets from real token counts,
     plus the scaling thresholds where the architecture would change. -->

Target: $0/month steady-state within AWS always-free limits. The account has no promotional
credits, so Bedrock is the only out-of-pocket line: at Nova Micro ($0.035/1M input, $0.14/1M
output) and Nova Lite ($0.06/1M input, $0.24/1M output) pricing, the full build's development
traffic (~10–20M tokens) is estimated under $15 total. Budget alarms at $5 and $20 are the
tripwire; Phase 10 replaces this estimate with measured token counts.

Public endpoints use API Gateway HTTP API (ADR-003): $1.00/M requests after the 12-month free
tier — rounding error at demo volume.
