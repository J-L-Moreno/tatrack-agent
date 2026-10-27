variable "student_id" {
  description = "Unique, short identifier for this deployment. Used to name every AWS resource."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,20}$", var.student_id))
    error_message = "student_id must be 3-21 characters: lowercase letters, digits or '_' and start with a letter."
  }
}

variable "aws_region" {
  description = "AWS region where Kimi K2.5 on Bedrock and AgentCore are available."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use. Leave null to use the default credential chain."
  type        = string
  default     = null
}

variable "api_keys" {
  description = "Comma-separated API keys accepted by the API (x-api-key header)."
  type        = string
  sensitive   = true

  validation {
    condition     = alltrue([for key in split(",", var.api_keys) : length(trimspace(key)) >= 20])
    error_message = "Each API key must be at least 20 characters long."
  }
}

variable "model_id" {
  description = "Bedrock model ID used by the agent."
  type        = string
  default     = "moonshotai.kimi-k2.5"
}

variable "timezone" {
  description = "IANA timezone of the student (due dates, 'today' and reminder schedule), e.g. America/Mexico_City."
  type        = string
  default     = "America/Mexico_City"
}

variable "enable_long_term_memory" {
  description = "Enable AgentCore long-term memory (USER_PREFERENCE + SEMANTIC strategies)."
  type        = bool
  default     = true
}

variable "memory_event_expiry_days" {
  description = "Days AgentCore Memory keeps raw conversation events."
  type        = number
  default     = 30

  validation {
    condition     = var.memory_event_expiry_days >= 7 && var.memory_event_expiry_days <= 365
    error_message = "memory_event_expiry_days must be between 7 and 365."
  }
}

variable "reminder_actor_id" {
  description = "actor_id whose tasks are included in the daily reminder email. Use the same value in your API calls."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", var.reminder_actor_id))
    error_message = "reminder_actor_id may only contain letters, digits, '-' or '_' (max 64) and must start with a letter or digit."
  }
}

variable "reminder_email" {
  description = "Email that receives the daily reminder. Leave empty to disable reminders."
  type        = string
  default     = ""

  validation {
    condition     = var.reminder_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.reminder_email))
    error_message = "reminder_email must be a valid email address or empty."
  }
}

variable "reminder_schedule_expression" {
  description = "EventBridge Scheduler expression for the reminder, evaluated in var.timezone."
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "existing_subnet_ids" {
  description = "Public subnet IDs (2+ AZs) to reuse for the API. Leave empty to create a dedicated VPC."
  type        = list(string)
  default     = []
}

variable "vpc_cidr" {
  description = "CIDR for the dedicated VPC (only used when existing_subnet_ids is empty)."
  type        = string
  default     = "10.0.0.0/16"
}
