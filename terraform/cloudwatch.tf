# ── Log group ─────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/${var.app_name}/backend"
  retention_in_days = var.log_retention_days

  tags = { Name = "${var.app_name}-backend-logs" }
}

# ── SNS topic for alarms ──────────────────────────────────────────────────────

resource "aws_sns_topic" "alarms" {
  name = "${var.app_name}-alarms"
  tags = { Name = "${var.app_name}-alarms" }
}

# ── Metric filters ────────────────────────────────────────────────────────────
# The backend emits structured JSON logs. These filters extract HTTP status
# codes from the access log entries written by RequestLoggerMiddleware.

resource "aws_cloudwatch_log_metric_filter" "http_4xx" {
  name           = "${var.app_name}-http-4xx"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.status_code >= 400 && $.status_code < 500 }"

  metric_transformation {
    name          = "Http4xxCount"
    namespace     = "AutoSecOps/Backend"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "http_5xx" {
  name           = "${var.app_name}-http-5xx"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.status_code >= 500 }"

  metric_transformation {
    name          = "Http5xxCount"
    namespace     = "AutoSecOps/Backend"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "http_429" {
  name           = "${var.app_name}-http-429"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.status_code = 429 }"

  metric_transformation {
    name          = "RateLimitedCount"
    namespace     = "AutoSecOps/Backend"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

# ── Alarms ────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "rate_limit" {
  alarm_name          = "${var.app_name}-rate-limit-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "RateLimitedCount"
  namespace           = "AutoSecOps/Backend"
  period              = 60
  statistic           = "Sum"
  threshold           = var.rate_limit_alarm_threshold
  alarm_description   = "More than ${var.rate_limit_alarm_threshold} rate-limited (429) responses in 1 minute — possible attack or misconfigured client"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]

  tags = { Name = "${var.app_name}-rate-limit-alarm" }
}

resource "aws_cloudwatch_metric_alarm" "http_5xx" {
  alarm_name          = "${var.app_name}-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Http5xxCount"
  namespace           = "AutoSecOps/Backend"
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "More than 10 5xx responses in 2 consecutive minutes"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]

  tags = { Name = "${var.app_name}-5xx-alarm" }
}
