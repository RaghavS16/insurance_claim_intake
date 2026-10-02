output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_app_subnet_ids" {
  value = aws_subnet.private_app[*].id
}

output "private_data_subnet_ids" {
  value = aws_subnet.private_data[*].id
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "evidence_bucket" {
  value = aws_s3_bucket.evidence.bucket
}

output "data_kms_key_arn" {
  value = aws_kms_key.data.arn
}

output "app_iam_role_arn" {
  value = aws_iam_role.app.arn
}

output "alb_dns_name" {
  value = aws_lb.app.dns_name
}
