variable "name" {
  description = "Service name, matching its directory under services/"
  type        = string
}

variable "env" {
  type = string
}

variable "zip_path" {
  type    = string
  default = null
}

variable "image_uri" {
  description = "ECR image URI for container-based services; null for zip"
  type        = string
  default     = null
}

variable "architectures" {
  type    = list(string)
  default = ["x86_64"]
}

variable "image_command" {
  description = "Override the image CMD (share one image across handlers)"
  type        = list(string)
  default     = null
}

variable "log_group_name" {
  type = string
}

variable "log_group_arn" {
  type = string
}

variable "attach_policy" {
  description = "Set true when passing policy_json (must be a literal: count needs plan-time values)"
  type        = bool
  default     = false
}

variable "policy_json" {
  description = "Service-specific IAM policy document (JSON); null for logs-only"
  type        = string
  default     = null
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "timeout" {
  type    = number
  default = 10
}

variable "memory_mb" {
  type    = number
  default = 128
}
