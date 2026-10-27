output "tasks_table_name" {
  value = aws_dynamodb_table.tasks.name
}

output "tasks_table_arn" {
  value = aws_dynamodb_table.tasks.arn
}

output "responses_table_name" {
  value = aws_dynamodb_table.responses.name
}

output "responses_table_arn" {
  value = aws_dynamodb_table.responses.arn
}
