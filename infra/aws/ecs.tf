resource "aws_ecr_repository" "app" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  tags                 = local.tags

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.data.arn
  }
}

resource "aws_ecs_cluster" "app" {
  name = local.name
  tags = local.tags
}

resource "aws_ecs_cluster_capacity_providers" "app" {
  cluster_name       = aws_ecs_cluster.app.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 1
    capacity_provider = "FARGATE"
  }
}

resource "aws_iam_role" "execution" {
  name = "${local.name}-execution-role"

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

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  count = length(var.secrets_manager_secret_arns) > 0 ? 1 : 0
  role  = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.secrets_manager_secret_arns
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = aws_kms_key.data.arn
      },
    ]
  })
}

resource "aws_iam_role_policy" "execution_kms" {
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = aws_kms_key.data.arn
      }
    ]
  })
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.app_cpu)
  memory                   = tostring(var.app_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.app.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = var.container_image
      essential = true

      portMappings = [
        {
          name          = "http"
          containerPort = var.app_container_port
          hostPort      = var.app_container_port
          protocol      = "tcp"
        },
      ]

      environment = [
        for key, value in merge(
          {
            ENVIRONMENT                      = var.environment
            DEBUG                            = "false"
            AWS_REGION                       = var.aws_region
            S3_BUCKET                        = aws_s3_bucket.evidence.bucket
            S3_SERVER_SIDE_ENCRYPTION        = "aws:kms"
            S3_KMS_KEY_ID                    = aws_kms_key.data.arn
            REDIS_URL                        = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
            VOICE_PROVIDER                   = "pipecat_local"
            AI_ALLOW_LOCAL_FALLBACK          = "false"
            REQUIRE_REDIS_IN_PRODUCTION      = "true"
            REQUIRE_S3_IN_PRODUCTION         = "true"
            REQUIRE_MALWARE_SCAN             = "true"
            REQUIRE_MIGRATIONS_IN_PRODUCTION = "true"
            FORWARDED_ALLOW_IPS              = join(",", aws_subnet.public[*].cidr_block)
          },
          var.app_environment
          ) : {
          name  = key
          value = value
        }
      ]

      secrets = [
        for env_name, secret_arn in var.secret_environment : {
          name      = env_name
          valueFrom = secret_arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }

      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:${var.app_container_port}${var.health_path}', timeout=3)\""
        ]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 30
      }
    },
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.ecs_cpu_architecture
  }

  tags = local.tags
}

resource "aws_ecs_service" "app" {
  name                               = local.name
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.app.arn
  desired_count                      = var.app_desired_count
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  health_check_grace_period_seconds  = 120
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  enable_ecs_managed_tags            = true
  propagate_tags                     = "SERVICE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = false
    security_groups  = [aws_security_group.app.id]
    subnets          = aws_subnet.private_app[*].id
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "backend"
    container_port   = var.app_container_port
  }

  depends_on = [
    aws_lb_listener.https,
    aws_iam_role_policy_attachment.execution,
  ]

  tags = local.tags
}

resource "aws_ecs_task_definition" "outbox" {
  family                   = "${local.name}-outbox"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.outbox_cpu)
  memory                   = tostring(var.outbox_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.app.arn

  container_definitions = jsonencode([
    {
      name      = "outbox-worker"
      image     = var.container_image
      essential = true
      command   = ["python", "-m", "src.services.outbox_worker"]

      environment = [
        for key, value in merge(
          {
            ENVIRONMENT                 = var.environment
            DEBUG                       = "false"
            AWS_REGION                  = var.aws_region
            S3_BUCKET                   = aws_s3_bucket.evidence.bucket
            S3_SERVER_SIDE_ENCRYPTION   = "aws:kms"
            S3_KMS_KEY_ID               = aws_kms_key.data.arn
            REDIS_URL                   = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
            AI_ALLOW_LOCAL_FALLBACK     = "false"
            REQUIRE_REDIS_IN_PRODUCTION = "true"
            REQUIRE_S3_IN_PRODUCTION    = "true"
          },
          var.app_environment
          ) : {
          name  = key
          value = value
        }
      ]

      secrets = [
        for env_name, secret_arn in var.secret_environment : {
          name      = env_name
          valueFrom = secret_arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "outbox"
        }
      }

      stopTimeout = 30
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.ecs_cpu_architecture
  }

  tags = local.tags
}

resource "aws_ecs_service" "outbox" {
  name                               = "${local.name}-outbox"
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.outbox.arn
  desired_count                      = var.outbox_desired_count
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  enable_ecs_managed_tags            = true
  propagate_tags                     = "SERVICE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = false
    security_groups  = [aws_security_group.app.id]
    subnets          = aws_subnet.private_app[*].id
  }

  depends_on = [aws_iam_role_policy_attachment.execution]

  tags = local.tags
}

# =============================================================================
# One-off database migration task definition
# Run before each backend deployment using:
#   aws ecs run-task \
#     --cluster <cluster-name> \
#     --task-definition <project-name>-migrate \
#     --launch-type FARGATE \
#     --network-configuration "awsvpcConfiguration={subnets=[<private-subnet-ids>],securityGroups=[<app-sg-id>],assignPublicIp=DISABLED}"
# =============================================================================
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.app_cpu)
  memory                   = tostring(var.app_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.app.arn

  container_definitions = jsonencode([
    {
      name      = "migrate"
      image     = var.container_image
      essential = true
      command   = ["alembic", "upgrade", "head"]

      environment = [
        for key, value in merge(
          {
            ENVIRONMENT                      = var.environment
            DEBUG                            = "false"
            DATABASE_URL                     = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}/${var.db_name}"
            REQUIRE_MIGRATIONS_IN_PRODUCTION = "false"
          },
          var.app_environment
        ) : {
          name  = key
          value = value
        }
      ]

      secrets = [
        for env_name, secret_arn in var.secret_environment : {
          name      = env_name
          valueFrom = secret_arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "migrate"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.ecs_cpu_architecture
  }

  tags = local.tags
}

# =============================================================================
# Frontend Next.js Service and Task Definition
# =============================================================================
resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name}-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.frontend_cpu)
  memory                   = tostring(var.frontend_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.app.arn

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = coalesce(var.frontend_container_image, var.container_image)
      essential = true

      portMappings = [
        {
          name          = "http"
          containerPort = var.frontend_container_port
          hostPort      = var.frontend_container_port
          protocol      = "tcp"
        },
      ]

      environment = [
        {
          name  = "NODE_ENV"
          value = "production"
        },
        {
          name  = "INTERNAL_API_URL"
          value = "http://${aws_lb.app.dns_name}:8000"
        },
        {
          name  = "NEXT_PUBLIC_API_URL"
          value = ""
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "frontend"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.ecs_cpu_architecture
  }

  tags = local.tags
}

resource "aws_ecs_service" "frontend" {
  name                               = "${local.name}-frontend"
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.frontend.arn
  desired_count                      = var.frontend_desired_count
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  enable_ecs_managed_tags            = true
  propagate_tags                     = "SERVICE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = false
    security_groups  = [aws_security_group.app.id]
    subnets          = aws_subnet.private_app[*].id
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = var.frontend_container_port
  }

  depends_on = [
    aws_lb_listener.https,
    aws_iam_role_policy_attachment.execution,
  ]

  tags = local.tags
}

