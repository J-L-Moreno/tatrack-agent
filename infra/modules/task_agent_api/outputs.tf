output "service_url" {
  description = "HTTPS URL of the ECS Express Mode service."
  value       = try(aws_ecs_express_gateway_service.api.ingress_paths[0].endpoint, "")
}

output "service_arn" {
  description = "ARN of the ECS Express service."
  value       = aws_ecs_express_gateway_service.api.service_arn
}

output "api_keys_secret_name" {
  description = "Secrets Manager secret with the API keys."
  value       = aws_secretsmanager_secret.api_keys.name
}
