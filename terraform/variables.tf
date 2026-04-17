variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "app_name" {
  description = "Application name — used as a prefix for all resources"
  type        = string
  default     = "autosec"
}

variable "ecr_image_uri" {
  description = "Full ECR image URI including tag, e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com/autosec-backend:abc123"
  type        = string
}

variable "backend_port" {
  description = "Port the FastAPI backend listens on"
  type        = number
  default     = 8000
}

variable "backend_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Number of ECS task replicas"
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "rate_limit_alarm_threshold" {
  description = "Number of 429 responses per minute that triggers the RateLimit alarm"
  type        = number
  default     = 50
}
