resource "aws_db_instance" "postgres" {
  identifier="${local.name}-postgres" engine="postgres" engine_version="16" instance_class=var.db_instance_class
  allocated_storage=100 max_allocated_storage=500 storage_encrypted=true kms_key_id=aws_kms_key.data.arn
  db_name=var.db_name username=var.db_username password=var.db_password backup_retention_period=35
  deletion_protection=true multi_az=true publicly_accessible=false skip_final_snapshot=false
  copy_tags_to_snapshot=true auto_minor_version_upgrade=true apply_immediately=false
  db_subnet_group_name=aws_db_subnet_group.postgres.name vpc_security_group_ids=[aws_security_group.db.id]
  enabled_cloudwatch_logs_exports=["postgresql","upgrade"] tags=local.tags
}
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id=replace("${local.name}-redis","_","-")
  description="HA Redis for sessions rate limits and voice coordination"
  node_type=var.redis_node_type num_cache_clusters=2 automatic_failover_enabled=true multi_az_enabled=true
  at_rest_encryption_enabled=true transit_encryption_enabled=true kms_key_id=aws_kms_key.data.arn
  subnet_group_name=aws_elasticache_subnet_group.redis.name security_group_ids=[aws_security_group.redis.id] tags=local.tags
}
