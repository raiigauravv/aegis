# Ingestion spine: SQS (+DLQ with redrive), the single-table ticket store,
# and the S3 intake bucket for file drops (consumed in Phase 3).

resource "aws_sqs_queue" "dlq" {
  name                      = "aegis-${var.env}-ingest-dlq"
  message_retention_seconds = 1209600 # 14 days to inspect failures
}

resource "aws_sqs_queue" "ingest" {
  name                       = "aegis-${var.env}-ingest"
  visibility_timeout_seconds = 60 # > 6x lambda timeout guidance for retries
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# Per-stage work queues; all poison messages funnel to the one alarmed DLQ.
resource "aws_sqs_queue" "stage" {
  for_each                   = toset(["enrich", "extract", "transcribe"])
  name                       = "aegis-${var.env}-${each.value}"
  visibility_timeout_seconds = each.value == "enrich" ? 120 : 360 # containers are slower
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# Reversible PII mapping lives in its OWN table so IAM can fence it off:
# exactly one writer (enrich_nlp); no service holds read access.
resource "aws_dynamodb_table" "pii_map" {
  name           = "aegis-${var.env}-pii-map"
  billing_mode   = "PROVISIONED"
  read_capacity  = 2
  write_capacity = 2
  hash_key       = "PK"

  attribute {
    name = "PK"
    type = "S"
  }

  server_side_encryption {
    enabled = true # AWS-owned key; KMS CMK is the at-scale answer
  }
}

# Alarm #1 of the 10 free: anything in the DLQ is a bug worth looking at.
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "aegis-${var.env}-dlq-not-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

# Single-table design (docs/architecture.md). Provisioned 10/10 stays inside the
# always-free 25 RCU/25 WCU; on-demand billing is NOT in the always-free tier.
resource "aws_dynamodb_table" "tickets" {
  name           = "aegis-${var.env}-tickets"
  billing_mode   = "PROVISIONED"
  read_capacity  = 10
  write_capacity = 10
  hash_key       = "PK"
  range_key      = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }
}

resource "aws_s3_bucket" "intake" {
  bucket = "aegis-${var.env}-intake-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "intake" {
  bucket                  = aws_s3_bucket.intake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Raw uploads are transient: extraction output is what we keep (Phase 4 tightens this).
resource "aws_s3_bucket_lifecycle_configuration" "intake" {
  bucket = aws_s3_bucket.intake.id
  rule {
    id     = "expire-raw-uploads"
    status = "Enabled"
    filter {}
    expiration {
      days = 14
    }
  }
}

data "aws_iam_policy_document" "s3_to_sqs" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.intake.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "ingest" {
  queue_url = aws_sqs_queue.ingest.id
  policy    = data.aws_iam_policy_document.s3_to_sqs.json
}

resource "aws_s3_bucket_notification" "intake" {
  bucket     = aws_s3_bucket.intake.id
  depends_on = [aws_sqs_queue_policy.ingest]
  queue {
    queue_arn = aws_sqs_queue.ingest.arn
    events    = ["s3:ObjectCreated:*"]
  }
}
