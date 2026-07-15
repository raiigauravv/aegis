variable "env" {
  type = string
}

variable "service_names" {
  description = "Every Lambda service gets a log group under the /aegis/<env>/ convention"
  type        = list(string)
}

variable "retention_days" {
  type    = number
  default = 14
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "dashboard" {
  description = "Dashboard config: Lambda function names, queue names, DLQ name. null = no dashboard."
  type = object({
    functions = list(string)
    queues    = list(string)
    dlq       = string
  })
  default = null
}
