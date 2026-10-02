resource "aws_iam_role" "app" {
  name = "${local.name}-app-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "app" {
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
        Resource = "${aws_s3_bucket.evidence.arn}/claims/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.evidence.arn}/knowledge/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
        Resource = aws_kms_key.data.arn
      },
      ]
      dynamic "Statement" {
        for_each = length(var.secrets_manager_secret_arns) > 0 ? [1] : []
        content = {
          Effect   = "Allow"
          Action   = ["secretsmanager:GetSecretValue"]
          Resource = var.secrets_manager_secret_arns
        }
      }
  })
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/${local.name}/app"
  retention_in_days = 30
  tags              = local.tags
}
