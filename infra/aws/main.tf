terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}
provider "aws" { region = var.aws_region }
variable "aws_region" { type = string default = "ap-south-1" }
variable "db_name" { type = string default = "insurance_claims" }
variable "db_username" { type = string sensitive = true }
variable "db_password" { type = string sensitive = true }
variable "redis_node_type" { type = string default = "cache.t4g.small" }

resource "aws_db_instance" "postgres" {
  identifier = "insurance-claim-intake-postgres"
  engine = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.medium"
  allocated_storage = 100
  max_allocated_storage = 500
  storage_encrypted = true
  db_name = var.db_name
  username = var.db_username
  password = var.db_password
  backup_retention_period = 35
  deletion_protection = true
  multi_az = true
  publicly_accessible = false
  skip_final_snapshot = false
  copy_tags_to_snapshot = true
  auto_minor_version_upgrade = true
  apply_immediately = false
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "insurance-claim-intake-redis"
  description = "HA Redis for sessions, rate limits and voice coordination"
  node_type = var.redis_node_type
  num_cache_clusters = 2
  automatic_failover_enabled = true
  multi_az_enabled = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

resource "aws_s3_bucket" "evidence" {
  bucket = "insurance-claim-intake-evidence"
}
resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}