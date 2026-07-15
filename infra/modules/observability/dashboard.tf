# CloudWatch dashboard: one pane of glass for the demo + README screenshot.
# Metrics are all emitted by AWS for the resources we run (no custom PutMetricData
# needed yet; token-spend/day and groundedness widgets get added with Bedrock).

resource "aws_cloudwatch_dashboard" "main" {
  count          = var.dashboard == null ? 0 : 1
  dashboard_name = "aegis-${var.env}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type       = "text", x = 0, y = 0, width = 24, height = 2
        properties = { markdown = "# AEGIS ${var.env} — support intelligence pipeline\nIngestion → extraction/transcription → enrichment (PII redaction) → RAG → governed routing. Every stage is a Lambda; every ticket is traced." }
      },
      {
        type = "metric", x = 0, y = 2, width = 12, height = 6
        properties = {
          title  = "Tickets processed / 5 min (per stage)"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = [
            for fn in var.dashboard.functions :
            ["AWS/Lambda", "Invocations", "FunctionName", fn]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 2, width = 12, height = 6
        properties = {
          title  = "p95 latency per stage (ms)"
          region = var.region
          view   = "timeSeries"
          stat   = "p95"
          period = 300
          metrics = [
            for fn in var.dashboard.functions :
            ["AWS/Lambda", "Duration", "FunctionName", fn]
          ]
        }
      },
      {
        type = "metric", x = 0, y = 8, width = 8, height = 6
        properties = {
          title  = "Errors + throttles"
          region = var.region
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = concat(
            [for fn in var.dashboard.functions : ["AWS/Lambda", "Errors", "FunctionName", fn]],
            [["AWS/Lambda", "Throttles", "FunctionName", var.dashboard.functions[0]]]
          )
        }
      },
      {
        type = "metric", x = 8, y = 8, width = 8, height = 6
        properties = {
          title  = "Queue backlog (visible messages)"
          region = var.region
          view   = "timeSeries"
          stat   = "Maximum"
          period = 300
          metrics = [
            for q in var.dashboard.queues :
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", q]
          ]
        }
      },
      {
        type = "metric", x = 16, y = 8, width = 8, height = 6
        properties = {
          title  = "DLQ depth (should stay 0)"
          region = var.region
          view   = "singleValue"
          stat   = "Maximum"
          period = 300
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dashboard.dlq]
          ]
        }
      },
    ]
  })
}
