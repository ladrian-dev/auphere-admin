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

output "certificate_arn" {
  description = "Cert ACM del ALB (gestionado aquí o el override de var.certificate_arn)."
  value       = local.certificate_arn
}

# Los CNAME que hay que crear a mano en el DNS de auphere.com para que ACM
# emita. Un dominio y su comodín comparten registro, así que staging suele
# devolver UNO solo.
output "certificate_validation_records" {
  description = "Registros CNAME de validación DNS del cert ACM."
  value = local.manage_certificate ? [
    for opt in aws_acm_certificate.public[0].domain_validation_options : {
      domain = opt.domain_name
      name   = opt.resource_record_name
      type   = opt.resource_record_type
      value  = opt.resource_record_value
    }
  ] : []
}

output "public_hostname" {
  description = "Hostname público del entorno — CNAME a alb_dns_name."
  value       = local.dns_cfg.hostname
}

output "https_enabled" {
  value = local.https_enabled
}

# Lo consume 30-observability para colgar la regla de host de Grafana del
# listener que ya existe, en vez de levantar un segundo ALB. Es null
# mientras HTTPS esté apagado: sin 443 no hay dónde colgarla, y ese caso
# se comprueba explícitamente allí en vez de fallar con un error de tipos.
output "https_listener_arn" {
  description = "ARN del listener 443 del ALB, o null si https_enabled = false."
  value       = one(aws_lb_listener.https[*].arn)
}
