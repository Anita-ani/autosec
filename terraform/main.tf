terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "autosec-tfstate"
    key            = "autosec/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "autosec-tfstate-lock"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.app_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}



data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
