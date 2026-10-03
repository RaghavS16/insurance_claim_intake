resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = `${local.name}-alb-5xx`
  alarm_description   = "ALB backend 5xx rate exceeded the configured threshold."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 5
  threshold           = var.alb_5xx_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.app.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  alarm_name          = `${local.name}-ecs-cpu`
  alarm_description   = "Backend ECS service CPU is above the configured threshold."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 5
  threshold           = var.ecs_cpu_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.app.name
    ServiceName = aws_ecs_service.app.name
  }

  tags = local.tags
}
