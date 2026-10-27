locals {
  # AgentCore resource names only allow letters, digits and underscores.
  agent_name = "${var.student_id}_task_agent"
  # Everything else uses hyphens.
  name_prefix = "${replace(var.student_id, "_", "-")}-task-agent"

  # Must match MEMORY_NAMESPACE_PREFIX read by agent_core/middlewares/memory.py.
  memory_namespace_prefix = "tasks"

  create_vpc = length(var.existing_subnet_ids) == 0
  subnet_ids = local.create_vpc ? module.vpc[0].ecs_public_subnet_ids : var.existing_subnet_ids
}

module "vpc" {
  source = "./modules/vpc"
  count  = local.create_vpc ? 1 : 0

  prefix   = local.name_prefix
  vpc_cidr = var.vpc_cidr
}

module "tables" {
  source = "./modules/task_agent_tables"

  name_prefix = local.name_prefix
}

module "runtime" {
  source = "./modules/task_agent_runtime"

  agent_name               = local.agent_name
  name_prefix              = local.name_prefix
  source_dir               = abspath("${path.root}/../agent_core")
  aws_profile              = var.aws_profile
  model_id                 = var.model_id
  user_timezone            = var.timezone
  tasks_table_name         = module.tables.tasks_table_name
  tasks_table_arn          = module.tables.tasks_table_arn
  responses_table_name     = module.tables.responses_table_name
  responses_table_arn      = module.tables.responses_table_arn
  enable_long_term_memory  = var.enable_long_term_memory
  memory_event_expiry_days = var.memory_event_expiry_days
  memory_namespace_prefix  = local.memory_namespace_prefix
}

module "api" {
  source = "./modules/task_agent_api"

  name_prefix          = local.name_prefix
  source_dir           = abspath("${path.root}/../agent_api")
  aws_profile          = var.aws_profile
  agent_runtime_arn    = module.runtime.agent_runtime_arn
  api_keys             = var.api_keys
  subnet_ids           = local.subnet_ids
  responses_table_name = module.tables.responses_table_name
  responses_table_arn  = module.tables.responses_table_arn
  tasks_table_name     = module.tables.tasks_table_name
  tasks_table_arn      = module.tables.tasks_table_arn
}

module "reminders" {
  source = "./modules/task_agent_reminders"
  count  = var.reminder_email != "" ? 1 : 0

  name_prefix         = local.name_prefix
  agent_runtime_arn   = module.runtime.agent_runtime_arn
  tasks_table_name    = module.tables.tasks_table_name
  tasks_table_arn     = module.tables.tasks_table_arn
  reminder_email      = var.reminder_email
  reminder_actor_id   = var.reminder_actor_id
  timezone            = var.timezone
  schedule_expression = var.reminder_schedule_expression
}
