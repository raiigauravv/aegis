output "queue_url" {
  value = aws_sqs_queue.ingest.url
}

output "queue_arn" {
  value = aws_sqs_queue.ingest.arn
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}

output "table_name" {
  value = aws_dynamodb_table.tickets.name
}

output "table_arn" {
  value = aws_dynamodb_table.tickets.arn
}

output "intake_bucket" {
  value = aws_s3_bucket.intake.bucket
}
