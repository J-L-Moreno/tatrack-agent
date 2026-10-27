terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    null = {
      source = "hashicorp/null"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  src_hash   = substr(sha1(join("", [for f in sort(fileset(var.source_dir, "{*.py,requirements.txt,Dockerfile,.dockerignore}")) : filesha1("${var.source_dir}/${f}")])), 0, 12)
  cli_env    = var.aws_profile == null ? {} : { AWS_PROFILE = var.aws_profile }
}

# =============================================================================
# ECR Repository + image
# =============================================================================

resource "aws_ecr_repository" "api" {
  name                 = "${var.name_prefix}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "null_resource" "build_and_push" {
  triggers = {
    src_hash = local.src_hash
  }

  provisioner "local-exec" {
    environment = local.cli_env
    command     = <<-EOT
      set -e
      aws ecr get-login-password --region ${local.region} | docker login --username AWS --password-stdin ${local.account_id}.dkr.ecr.${local.region}.amazonaws.com
      docker buildx build --platform linux/amd64 --provenance=false -t ${aws_ecr_repository.api.repository_url}:${local.src_hash} -t ${aws_ecr_repository.api.repository_url}:latest --push "${var.source_dir}"
    EOT
  }
}

# =============================================================================
# Secrets Manager - API Keys
# =============================================================================

resource "aws_secretsmanager_secret" "api_keys" {
  name        = "${var.name_prefix}/api-keys"
  description = "API keys accepted by the Task Agent API"
  # Immediate deletion so the workshop stack can be destroyed and re-created with the same name.
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "api_keys" {
  secret_id     = aws_secretsmanager_secret.api_keys.id
  secret_string = var.api_keys
}

# =============================================================================
# IAM - ECS Task Execution Role (pulls images from ECR, writes logs)
# =============================================================================

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.name_prefix}-api-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# =============================================================================
# IAM - ECS Infrastructure Role (manages ALB, scaling, networking)
# =============================================================================

resource "aws_iam_role" "ecs_infrastructure" {
  name = "${var.name_prefix}-api-ecs-infrastructure"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowAccessInfrastructureForECSExpressServices"
      Effect    = "Allow"
      Principal = { Service = "ecs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_infrastructure" {
  role       = aws_iam_role.ecs_infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}

# =============================================================================
# IAM - ECS Task Role (invoke AgentCore, read API keys, DynamoDB)
# =============================================================================

resource "aws_iam_role" "ecs_task_role" {
  name = "${var.name_prefix}-api-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_permissions" {
  name = "${var.name_prefix}-api-ecs-permissions"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeAgentRuntime"
        Effect   = "Allow"
        Action   = "bedrock-agentcore:InvokeAgentRuntime"
        Resource = [var.agent_runtime_arn, "${var.agent_runtime_arn}/*"]
      },
      {
        Sid      = "ReadApiKeys"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.api_keys.arn
      },
      {
        Sid      = "ResponsesTable"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = [var.responses_table_arn]
      },
      {
        Sid      = "TasksTableReadOnly"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = [var.tasks_table_arn]
      }
    ]
  })
}

# =============================================================================
# ECS Express Gateway Service
# =============================================================================

resource "aws_ecs_express_gateway_service" "api" {
  service_name            = "${var.name_prefix}-api"
  execution_role_arn      = aws_iam_role.ecs_task_execution.arn
  infrastructure_role_arn = aws_iam_role.ecs_infrastructure.arn
  task_role_arn           = aws_iam_role.ecs_task_role.arn

  cpu    = var.cpu
  memory = var.memory

  health_check_path     = "/health"
  wait_for_steady_state = true

  primary_container {
    image          = "${aws_ecr_repository.api.repository_url}:latest"
    container_port = 8000

    environment {
      name  = "AGENT_RUNTIME_ARN"
      value = var.agent_runtime_arn
    }

    environment {
      name  = "API_KEYS_SECRET_NAME"
      value = aws_secretsmanager_secret.api_keys.name
    }

    environment {
      name  = "ALLOWED_ORIGINS"
      value = var.allowed_origins
    }

    environment {
      name  = "DYNAMODB_TABLE_NAME"
      value = var.responses_table_name
    }

    environment {
      name  = "TASKS_TABLE_NAME"
      value = var.tasks_table_name
    }

    environment {
      name  = "RATE_LIMIT"
      value = var.rate_limit
    }
  }

  network_configuration {
    subnets = var.subnet_ids
  }

  scaling_target {
    min_task_count            = 1
    max_task_count            = var.max_instances
    auto_scaling_metric       = "AVERAGE_CPU"
    auto_scaling_target_value = 60
  }

  depends_on = [
    null_resource.build_and_push,
    aws_secretsmanager_secret_version.api_keys,
    aws_iam_role_policy_attachment.ecs_task_execution,
    aws_iam_role_policy_attachment.ecs_infrastructure,
    aws_iam_role_policy.ecs_task_permissions,
  ]
}

# The service always runs :latest, so force a new deployment when the image changes.
resource "null_resource" "force_ecs_update" {
  triggers = {
    src_hash = local.src_hash
  }

  provisioner "local-exec" {
    environment = local.cli_env
    command     = <<-EOT
      aws ecs update-service \
        --cluster default \
        --service ${aws_ecs_express_gateway_service.api.service_name} \
        --force-new-deployment \
        --region ${local.region} > /dev/null
    EOT
  }

  depends_on = [
    aws_ecs_express_gateway_service.api,
    null_resource.build_and_push,
  ]
}
