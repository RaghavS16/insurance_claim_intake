resource "aws_kms_key" "data" {
  description="Encryption for claim evidence and database"
  deletion_window_in_days=30 enable_key_rotation=true tags=local.tags
}
resource "aws_kms_alias" "data" { name="alias/${local.name}-data" target_key_id=aws_kms_key.data.key_id }
resource "aws_s3_bucket" "evidence" { bucket="${local.name}-evidence-${data.aws_caller_identity.current.account_id}" tags=local.tags }
resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket=aws_s3_bucket.evidence.id block_public_acls=true block_public_policy=true ignore_public_acls=true restrict_public_buckets=true
}
resource "aws_s3_bucket_versioning" "evidence" { bucket=aws_s3_bucket.evidence.id versioning_configuration { status="Enabled" } }
resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket=aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default { kms_master_key_id=aws_kms_key.data.arn sse_algorithm="aws:kms" }
    bucket_key_enabled=true
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  bucket=aws_s3_bucket.evidence.id
  rule { id="quarantine-retention" status="Enabled" filter { prefix="quarantine/" } expiration { days=7 } noncurrent_version_expiration { noncurrent_days=7 } }
  rule { id="claims-noncurrent" status="Enabled" filter { prefix="claims/" } noncurrent_version_expiration { noncurrent_days=30 } }
  rule { id="knowledge-noncurrent" status="Enabled" filter { prefix="knowledge/" } noncurrent_version_expiration { noncurrent_days=90 } }
}
