# ─ Secrets Manager 
# Secrets are created empty — populate them manually or via CI after apply.
# The ECS execution role is granted GetSecretValue on each ARN (see ecs.tf).

resource "aws_secretsmanager_secret" "mongo_password" {
  name                    = "/${var.app_name}/${var.environment}/MONGO_PASSWORD"
  description             = "MongoDB root password for AutoSecOps"
  recovery_window_in_days = 7

  tags = { Name = "${var.app_name}-mongo-password" }
}

resource "aws_secretsmanager_secret" "api_key" {
  name                    = "/${var.app_name}/${var.environment}/API_KEY"
  description             = "Shared API key for X-API-Key header"
  recovery_window_in_days = 7

  tags = { Name = "${var.app_name}-api-key" }
}

resource "aws_secretsmanager_secret" "n8n_password" {
  name                    = "/${var.app_name}/${var.environment}/N8N_PASSWORD"
  description             = "n8n dashboard password"
  recovery_window_in_days = 7

  tags = { Name = "${var.app_name}-n8n-password" }
}

# Imported manually — created outside Terraform to hold the Atlas URI
resource "aws_secretsmanager_secret" "mongo_uri" {
  name                    = "/${var.app_name}/${var.environment}/MONGO_URI"
  description             = "Full MongoDB Atlas connection URI"
  recovery_window_in_days = 7

  tags = { Name = "${var.app_name}-mongo-uri" }

  lifecycle {
    prevent_destroy = true
  }
}



output "secret_arns" {
  description = "ARNs of all Secrets Manager secrets"
  value = {
    mongo_password = aws_secretsmanager_secret.mongo_password.arn
    api_key        = aws_secretsmanager_secret.api_key.arn
    n8n_password   = aws_secretsmanager_secret.n8n_password.arn
    mongo_uri      = aws_secretsmanager_secret.mongo_uri.arn
  }
  sensitive = true
}

