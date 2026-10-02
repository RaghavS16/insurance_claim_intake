variable "project_name" {
  type    = string
  default = "insurance-claim-intake"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["ap-south-1a", "ap-south-1b"]
}

variable "db_name" {
  type    = string
  default = "insurance_claims"
}

variable "db_username" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "acm_certificate_arn" {
  type = string

  validation {
    condition     = length(trimspace(var.acm_certificate_arn)) > 0
    error_message = "acm_certificate_arn is required for TLS."
  }
}

variable "secrets_manager_secret_arns" {
  type    = list(string)
  default = []
}

variable "app_container_port" {
  type    = number
  default = 8000
}

variable "health_path" {
  type    = string
  default = "/ready"
}

variable "allowed_ingress_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "tags" {
  type    = map(string)
  default = {}
}
