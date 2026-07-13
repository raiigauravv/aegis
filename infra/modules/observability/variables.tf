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
