# ── ECS Cluster

resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# ── IAM — task execution role (ECR pull + CloudWatch logs) ───────────────────

resource "aws_iam_role" "ecs_execution" {
  name = "${var.app_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow the execution role to read Secrets Manager secrets
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${var.app_name}-ecs-execution-secrets"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "kms:Decrypt",
      ]
      Resource = [
        aws_secretsmanager_secret.mongo_password.arn,
        aws_secretsmanager_secret.api_key.arn,
        aws_secretsmanager_secret.n8n_password.arn,
        aws_secretsmanager_secret.mongo_uri.arn,
      ]
    }]
  })
}

# ── IAM — task role (runtime permissions, least-privilege) ───────────────────

resource "aws_iam_role" "ecs_task" {
  name = "${var.app_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# ── Task definition 

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.app_name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "autosec-backend"
      image     = var.ecr_image_uri
      essential = true

      portMappings = [
        {
          containerPort = var.backend_port
          protocol      = "tcp"
        }
      ]

      # Secrets injected at runtime from Secrets Manager
      secrets = [
        {
          name      = "MONGO_URI"
          valueFrom = aws_secretsmanager_secret.mongo_uri.arn
        },
        {
          name      = "MONGO_PASSWORD"
          valueFrom = aws_secretsmanager_secret.mongo_password.arn
        },
        {
          name      = "API_KEY"
          valueFrom = aws_secretsmanager_secret.api_key.arn
        },
        {
          name      = "N8N_PASSWORD"
          valueFrom = aws_secretsmanager_secret.n8n_password.arn
        },
      ]

      environment = [
        { name = "MONGO_USER", value = "autosec" },
        { name = "MONGO_DB", value = "autosecops" },
        { name = "N8N_WEBHOOK_BASE", value = "http://n8n:5678/webhook" },
        { name = "RATE_LIMIT_REQUESTS", value = "60" },
        { name = "RATE_LIMIT_WINDOW_SECONDS", value = "60" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }

      # Mirror docker-compose hardening
      readonlyRootFilesystem = true

      linuxParameters = {
        capabilities = {
          drop = ["ALL"]
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.backend_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }
    }
  ])

  tags = { Name = "${var.app_name}-backend-task" }
}

# ── ECS Service (rolling deploy) ─────────────────────────────────────────────

resource "aws_ecs_service" "backend" {
  name                               = "${var.app_name}-backend"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.backend.arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  health_check_grace_period_seconds  = 30
  force_new_deployment               = true

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "autosec-backend"
    container_port   = var.backend_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_controller {
    type = "ECS"
  }

  depends_on = [aws_lb_listener.http]

  tags = { Name = "${var.app_name}-backend-service" }

  lifecycle {
    # CI updates the task definition image on every deploy — ignore drift here
    ignore_changes = [task_definition]
  }
}
