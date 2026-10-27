output "topic_arn" {
  value = aws_sns_topic.reminders.arn
}

output "function_name" {
  value = aws_lambda_function.reminder.function_name
}

output "schedule_name" {
  value = aws_scheduler_schedule.reminder.name
}
