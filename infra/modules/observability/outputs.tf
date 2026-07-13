output "log_group_names" {
  value = { for name, lg in aws_cloudwatch_log_group.service : name => lg.name }
}

output "log_group_arns" {
  value = { for name, lg in aws_cloudwatch_log_group.service : name => lg.arn }
}
