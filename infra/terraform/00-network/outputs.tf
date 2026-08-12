output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "service_security_group_ids" {
  description = "SG por servicio: api / runner / scheduler / egress"
  value       = { for k, sg in aws_security_group.service : k => sg.id }
}

output "aurora_security_group_id" {
  value = aws_security_group.aurora.id
}

output "pgbouncer_security_group_id" {
  value = aws_security_group.pgbouncer.id
}

output "valkey_security_group_id" {
  value = aws_security_group.valkey.id
}

output "grafana_security_group_id" {
  value = aws_security_group.grafana.id
}
