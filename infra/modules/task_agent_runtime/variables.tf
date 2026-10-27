variable "agent_name" {
  description = "AgentCore runtime name (letters, digits and underscores)."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for non-AgentCore resource names."
  type        = string
}

variable "source_dir" {
  description = "Absolute path to the agent_core source directory."
  type        = string
}

variable "aws_profile" {
  description = "AWS CLI profile used by the image build/push commands."
  type        = string
  default     = null
}

variable "model_id" {
  description = "Bedrock model ID."
  type        = string
}

variable "user_timezone" {
  description = "IANA timezone of the student."
  type        = string
}

variable "tasks_table_name" {
  type = string
}

variable "tasks_table_arn" {
  type = string
}

variable "responses_table_name" {
  type = string
}

variable "responses_table_arn" {
  type = string
}

variable "enable_long_term_memory" {
  description = "Create the USER_PREFERENCE and SEMANTIC strategies and enable the memory middleware."
  type        = bool
}

variable "memory_event_expiry_days" {
  description = "Days AgentCore Memory keeps raw conversation events."
  type        = number
}

variable "memory_namespace_prefix" {
  description = "First segment of the long-term memory namespaces."
  type        = string
}
