variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "source_dir" {
  description = "Absolute path to the agent_api source directory."
  type        = string
}

variable "aws_profile" {
  description = "AWS CLI profile used by the build and deployment commands."
  type        = string
  default     = null
}

variable "agent_runtime_arn" {
  description = "ARN of the AgentCore runtime to invoke."
  type        = string
}

variable "api_keys" {
  description = "Comma-separated API keys accepted by the API."
  type        = string
  sensitive   = true
}

variable "allowed_origins" {
  description = "Comma-separated list of allowed CORS origins."
  type        = string
  default     = "*"
}

variable "rate_limit" {
  description = "Per-IP rate limit for authenticated endpoints (slowapi syntax)."
  type        = string
  default     = "10/minute"
}

variable "cpu" {
  description = "CPU units for the ECS task."
  type        = string
  default     = "256"
}

variable "memory" {
  description = "Memory (MiB) for the ECS task."
  type        = string
  default     = "512"
}

variable "max_instances" {
  description = "Maximum number of tasks for auto-scaling."
  type        = number
  default     = 1
}

variable "subnet_ids" {
  description = "Public subnet IDs (at least 2 AZs) for ECS Express Mode."
  type        = list(string)
}

variable "responses_table_name" {
  type = string
}

variable "responses_table_arn" {
  type = string
}

variable "tasks_table_name" {
  type = string
}

variable "tasks_table_arn" {
  type = string
}
