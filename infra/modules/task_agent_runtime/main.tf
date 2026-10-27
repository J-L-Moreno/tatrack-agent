terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    null = {
      source = "hashicorp/null"
    }
    time = {
      source = "hashicorp/time"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region

  # Inference profile IDs (us./eu./apac./global.) point to the foundation model with the bare ID.
  foundation_model_id = replace(var.model_id, "/^(us|eu|apac|global)\\./", "")

  source_files = sort(concat(
    tolist(fileset(var.source_dir, "*.py")),
    tolist(fileset(var.source_dir, "{requirements.txt,Dockerfile,.dockerignore}")),
    tolist(fileset(var.source_dir, "{middlewares,prompts,tools}/**/*.py")),
    tolist(fileset(var.source_dir, "skills/**/SKILL.md")),
  ))
  # A new tag per source change makes the runtime pick up the new image without replacement.
  image_tag = substr(sha1(join("", [for f in local.source_files : filesha1("${var.source_dir}/${f}")])), 0, 12)
  image_uri = "${aws_ecr_repository.agent.repository_url}:${local.image_tag}"

  memory_namespaces = {
    semantic    = "/${var.memory_namespace_prefix}/user/{actorId}/semantic/"
    preferences = "/${var.memory_namespace_prefix}/user/{actorId}/preferences/"
  }
}

# =============================================================================
# Container image (AgentCore Runtime requires linux/arm64)
# =============================================================================

resource "aws_ecr_repository" "agent" {
  name                 = "${var.name_prefix}-runtime"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "null_resource" "build_and_push" {
  triggers = {
    image_uri = local.image_uri
  }

  provisioner "local-exec" {
    environment = var.aws_profile == null ? {} : { AWS_PROFILE = var.aws_profile }
    command     = <<-EOT
      set -e
      aws ecr get-login-password --region ${local.region} | docker login --username AWS --password-stdin ${local.account_id}.dkr.ecr.${local.region}.amazonaws.com
      docker buildx build --platform linux/arm64 --provenance=false --build-arg AWS_REGION=${local.region} -t ${local.image_uri} --push "${var.source_dir}"
    EOT
  }
}

# =============================================================================
# IAM execution role
# =============================================================================

resource "aws_iam_role" "runtime" {
  name = "${var.name_prefix}-runtime-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:*" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "runtime" {
  name = "${var.name_prefix}-runtime-policy"
  role = aws_iam_role.runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ECRImageAccess"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
        Resource = [aws_ecr_repository.agent.arn]
      },
      {
        Sid      = "ECRTokenAccess"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid      = "RuntimeLogGroups"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogStreams", "logs:CreateLogGroup"]
        Resource = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"]
      },
      {
        Sid      = "DescribeLogGroups"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogGroups"]
        Resource = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:*"]
      },
      {
        Sid      = "RuntimeLogStreams"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
        Resource = "*"
      },
      {
        Sid       = "Metrics"
        Effect    = "Allow"
        Action    = "cloudwatch:PutMetricData"
        Resource  = "*"
        Condition = { StringEquals = { "cloudwatch:namespace" = "bedrock-agentcore" } }
      },
      {
        Sid    = "WorkloadIdentity"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetWorkloadAccessToken",
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:workload-identity-directory/default",
          "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:workload-identity-directory/default/workload-identity/*"
        ]
      },
      {
        Sid    = "BedrockModelInvocation"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/${local.foundation_model_id}",
          "arn:aws:bedrock:${local.region}:${local.account_id}:inference-profile/${var.model_id}"
        ]
      },
      {
        Sid       = "MarketplaceSubscribeOnFirstCall"
        Effect    = "Allow"
        Action    = ["aws-marketplace:ViewSubscriptions", "aws-marketplace:Subscribe"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:CalledViaLast" = "bedrock.amazonaws.com" } }
      },
      {
        Sid    = "AgentCoreMemory"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:CreateEvent",
          "bedrock-agentcore:GetEvent",
          "bedrock-agentcore:ListEvents",
          "bedrock-agentcore:DeleteEvent",
          "bedrock-agentcore:ListSessions",
          "bedrock-agentcore:ListActors",
          "bedrock-agentcore:GetMemory",
          "bedrock-agentcore:GetMemoryRecord",
          "bedrock-agentcore:ListMemoryRecords",
          "bedrock-agentcore:RetrieveMemoryRecords",
          "bedrock-agentcore:DeleteMemoryRecord"
        ]
        Resource = [aws_bedrockagentcore_memory.this.arn]
      },
      {
        Sid      = "TasksTable"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:Query"]
        Resource = [var.tasks_table_arn]
      },
      {
        Sid      = "ResponsesTable"
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = [var.responses_table_arn]
      }
    ]
  })
}

# =============================================================================
# AgentCore Memory: short-term history + long-term strategies
# =============================================================================

resource "aws_bedrockagentcore_memory" "this" {
  name                  = "${var.agent_name}_memory"
  description           = "Conversation history and long-term memory for ${var.agent_name}"
  event_expiry_duration = var.memory_event_expiry_days
}

# Prevents "Memory is in transitional state UPDATING" when adding strategies right after creation.
resource "time_sleep" "memory_ready" {
  count           = var.enable_long_term_memory ? 1 : 0
  create_duration = "15s"
  depends_on      = [aws_bedrockagentcore_memory.this]
}

resource "aws_bedrockagentcore_memory_strategy" "semantic" {
  count               = var.enable_long_term_memory ? 1 : 0
  name                = "${var.agent_name}_semantic"
  memory_id           = aws_bedrockagentcore_memory.this.id
  type                = "SEMANTIC"
  description         = "Facts and context extracted from the student's conversations"
  namespace_templates = [local.memory_namespaces.semantic]

  depends_on = [time_sleep.memory_ready]
}

resource "aws_bedrockagentcore_memory_strategy" "user_preference" {
  count               = var.enable_long_term_memory ? 1 : 0
  name                = "${var.agent_name}_user_pref"
  memory_id           = aws_bedrockagentcore_memory.this.id
  type                = "USER_PREFERENCE"
  description         = "Preferences of the student (format, default priority, schedule, tone)"
  namespace_templates = [local.memory_namespaces.preferences]

  depends_on = [time_sleep.memory_ready]
}

# =============================================================================
# AgentCore Runtime
# =============================================================================

resource "aws_bedrockagentcore_agent_runtime" "this" {
  agent_runtime_name = var.agent_name
  description        = "Task tracker agent for ${var.agent_name}"
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = local.image_uri
    }
  }

  environment_variables = {
    TASK_AGENT_NAME             = var.agent_name
    BEDROCK_MODEL_ID            = var.model_id
    BEDROCK_AGENTCORE_MEMORY_ID = aws_bedrockagentcore_memory.this.id
    ENABLE_LONG_TERM_MEMORY     = tostring(var.enable_long_term_memory)
    MEMORY_NAMESPACE_PREFIX     = var.memory_namespace_prefix
    TASKS_TABLE_NAME            = var.tasks_table_name
    DYNAMODB_TABLE_NAME         = var.responses_table_name
    USER_TIMEZONE               = var.user_timezone
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  depends_on = [
    null_resource.build_and_push,
    aws_iam_role_policy.runtime,
    aws_bedrockagentcore_memory_strategy.semantic,
    aws_bedrockagentcore_memory_strategy.user_preference,
  ]
}
