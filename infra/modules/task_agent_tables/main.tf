# Tasks: one partition per student (actor_id), one item per task.
resource "aws_dynamodb_table" "tasks" {
  name         = "${var.name_prefix}-tasks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "actor_id"
  range_key    = "task_id"

  attribute {
    name = "actor_id"
    type = "S"
  }

  attribute {
    name = "task_id"
    type = "S"
  }
}

# Pending/final responses for synchronous API calls; expired items are removed by TTL.
resource "aws_dynamodb_table" "responses" {
  name         = "${var.name_prefix}-responses"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
