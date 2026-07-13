# Observability conventions for every AEGIS service:
# - one log group per service, named /aegis/<env>/<service>
# - short retention (free-tier friendly, tickets are also traced in DynamoDB)
# Services log structured JSON via aegis_core.tracing, so CloudWatch Logs Insights
# can query any ticket's timeline: filter @message like /tkt_.../

resource "aws_cloudwatch_log_group" "service" {
  for_each          = toset(var.service_names)
  name              = "/aegis/${var.env}/${each.value}"
  retention_in_days = var.retention_days
}
