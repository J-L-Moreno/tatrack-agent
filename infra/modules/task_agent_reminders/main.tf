terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    archive = {
      source = "hashicorp/archive"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  function_name = "${var.name_prefix}-reminder"
}

# =============================================================================
# SNS topic + email subscription (the student must confirm the subscription email)
# =============================================================================

resource "aws_sns_topic" "reminders" {
  name              = "${var.name_prefix}-reminders"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.reminders.arn
  protocol  = "email"
  endpoint  = var.reminder_email
}

# =============================================================================
# Lambda
# =============================================================================

data "archive_file" "reminder" {
  type        = "zip"
  source_file = "${path.module}/lambda/reminder_function.py"
  output_path = "${path.module}/build/reminder_function.zip"
}

resource "aws_cloudwatch_log_group" "reminder" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 14
}

resource "aws_iam_role" "reminder" {
  name = "${var.name_prefix}-reminder-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "reminder" {
  name = "${var.name_prefix}-reminder-lambda"
  role = aws_iam_role.reminder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.reminder.arn}:*"
      },
      {
        Sid      = "ReadTasks"
        Effect   = "Allow"
        Action   = "dynamodb:Query"
        Resource = var.tasks_table_arn
      },
      {
        Sid      = "InvokeAgent"
        Effect   = "Allow"
        Action   = "bedrock-agentcore:InvokeAgentRuntime"
        Resource = [var.agent_runtime_arn, "${var.agent_runtime_arn}/*"]
      },
      {
        Sid      = "PublishReminder"
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = aws_sns_topic.reminders.arn
      }
    ]
  })
}

resource "aws_lambda_function" "reminder" {
  function_name    = local.function_name
  role             = aws_iam_role.reminder.arn
  runtime          = "python3.13"
  handler          = "reminder_function.lambda_handler"
  timeout          = 300
  memory_size      = 256
  filename         = data.archive_file.reminder.output_path
  source_code_hash = data.archive_file.reminder.output_base64sha256

  environment {
    variables = {
      AGENT_RUNTIME_ARN = var.agent_runtime_arn
      TASKS_TABLE_NAME  = var.tasks_table_name
      REMINDER_ACTOR_ID = var.reminder_actor_id
      REMINDER_TIMEZONE = var.timezone
      SNS_TOPIC_ARN     = aws_sns_topic.reminders.arn
      LOOKAHEAD_DAYS    = tostring(var.lookahead_days)
    }
  }

  depends_on = [aws_cloudwatch_log_group.reminder, aws_iam_role_policy.reminder]
}

# =============================================================================
# EventBridge Scheduler (runs in the student's timezone)
# =============================================================================

resource "aws_iam_role" "scheduler" {
  name = "${var.name_prefix}-reminder-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "${var.name_prefix}-reminder-scheduler"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.reminder.arn
    }]
  })
}

resource "aws_scheduler_schedule" "reminder" {
  name                         = "${var.name_prefix}-daily-reminder"
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.reminder.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
