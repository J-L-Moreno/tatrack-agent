terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.14"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

# Credentials come from the AWS CLI configuration (profile, SSO or environment variables).
provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project = "task-agent-workshop"
      Student = var.student_id
    }
  }
}
