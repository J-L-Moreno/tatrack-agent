output "agent_runtime_arn" {
  description = "ARN of the AgentCore runtime."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn
}

output "execution_role_arn" {
  description = "ARN of the runtime execution role."
  value       = aws_iam_role.runtime.arn
}

output "memory_id" {
  description = "AgentCore Memory ID."
  value       = aws_bedrockagentcore_memory.this.id
}

output "memory_namespaces" {
  description = "Long-term memory namespaces ({actorId} is replaced by the student's actor_id)."
  value       = var.enable_long_term_memory ? local.memory_namespaces : null
}
