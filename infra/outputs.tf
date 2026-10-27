output "api_url" {
  description = "Base URL of the Task Agent API."
  value       = module.api.service_url
}

output "api_keys_secret_name" {
  description = "Secrets Manager secret that stores the API keys."
  value       = module.api.api_keys_secret_name
}

output "agent_runtime_arn" {
  description = "ARN of the AgentCore runtime."
  value       = module.runtime.agent_runtime_arn
}

output "memory_id" {
  description = "AgentCore Memory ID (short-term history + long-term strategies)."
  value       = module.runtime.memory_id
}

output "memory_namespaces" {
  description = "Namespaces where the long-term memory strategies store records ({actorId} = your actor_id)."
  value       = module.runtime.memory_namespaces
}

output "tasks_table_name" {
  description = "DynamoDB table with the tasks."
  value       = module.tables.tasks_table_name
}

output "responses_table_name" {
  description = "DynamoDB table with the API response tracking."
  value       = module.tables.responses_table_name
}

output "reminder_function_name" {
  description = "Lambda that sends the daily reminder (null when reminders are disabled)."
  value       = one(module.reminders[*].function_name)
}

output "reminder_topic_arn" {
  description = "SNS topic used for the reminder email (null when reminders are disabled)."
  value       = one(module.reminders[*].topic_arn)
}
