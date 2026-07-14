variable "env" {
  type = string
}

variable "account_id" {
  type = string
}

variable "container_services" {
  description = "Services deployed as container images (one ECR repo each)"
  type        = list(string)
  default     = []
}
