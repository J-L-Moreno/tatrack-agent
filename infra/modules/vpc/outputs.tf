output "vpc_id" {
  value = aws_vpc.main.id
}

output "ecs_public_subnet_ids" {
  description = "Public subnet IDs for ECS Express Mode services"
  value       = aws_subnet.ecs_public[*].id
}
