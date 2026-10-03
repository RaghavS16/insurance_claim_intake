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

variable "voice_sticky_cookie_name" {
  type    = string
  default = "voice_worker_id"
}

variable "voice_sticky_cookie_duration_seconds" {
  type    = number
  default = 1800
}

variable "container_image" {
  type = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", trimspace(var.container_image)))
    error_message = "container_image must use an immutable image digest (repository@sha256:<64-hex>)."
  }
}

variable "app_cpu" {
  type    = number
  default = 2048
}

variable "app_memory" {
  type    = number
  default = 4096
}

variable "app_desired_count" {
  type    = number
  default = 2
}

variable "app_min_running_tasks" {
  type    = number
  default = 2
}

variable "ecs_cpu_architecture" {
  type    = string
  default = "X86_64"

  validation {
    condition     = contains(["X86_64", "ARM64"], var.ecs_cpu_architecture)
    error_message = "ecs_cpu_architecture must be X86_64 or ARM64."
  }
}

variable "app_environment" {
  type    = map(string)
  default = {}
}

variable "secret_environment" {
  type      = map(string)
  sensitive = true
  default   = {}
}

variable "alb_5xx_alarm_threshold" {
  type    = number
  default = 5
}

variable "ecs_cpu_alarm_threshold" {
  type    = number
  default = 80
}

variable "outbox_cpu" {
  type    = number
  default = 512
}

variable "outbox_memory" {
  type    = number
  default = 1024
}

variable "outbox_desired_count" {
  type    = number
  default = 1
}
