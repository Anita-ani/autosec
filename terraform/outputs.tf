output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "alb_arn" {
  description = "ARN of the ALB (needed to set up HTTPS listener later)"
  value       = aws_lb.main.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name — used in CI deploy step"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name — used in CI deploy step"
  value       = aws_ecs_service.backend.name
}

output "ecr_repository_url" {
  description = "ECR repository URL (without tag) for the backend image"
  value       = "Set AWS_ACCOUNT_ID and push to: ${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/autosec-backend"
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name for backend container logs"
  value       = aws_cloudwatch_log_group.backend.name
}

output "sns_alarm_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms — subscribe an email or PagerDuty endpoint"
  value       = aws_sns_topic.alarms.arn
}
