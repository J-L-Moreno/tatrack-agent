variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "agent_runtime_arn" {
  description = "ARN of the AgentCore runtime that writes the digest."
  type        = string
}

variable "tasks_table_name" {
  type = string
}

variable "tasks_table_arn" {
  type = string
}

variable "reminder_email" {
  description = "Email subscribed to the reminder topic."
  type        = string
}

variable "reminder_actor_id" {
  description = "actor_id whose tasks are checked."
  type        = string
}

variable "timezone" {
  description = "IANA timezone used for the schedule and for 'today'."
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression."
  type        = string
}

variable "lookahead_days" {
  description = "Tasks due within this many days (plus overdue ones) trigger a reminder."
  type        = number
  default     = 1
}
