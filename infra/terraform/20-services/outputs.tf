output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "alb_arn_suffix" {
  value = aws_lb.main.arn_suffix
}

output "api_target_group_arn_suffix" {
  value = aws_lb_target_group.api.arn_suffix
}

output "service_names" {
  value = { for k, s in aws_ecs_service.service : k => s.name }
}

output "migrate_task_definition_family" {
  value = aws_ecs_task_definition.migrate.family
}
