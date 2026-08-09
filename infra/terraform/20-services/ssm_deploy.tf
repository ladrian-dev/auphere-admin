# Parámetros que el workflow de deploy (CI) necesita para run-task y
# update-service sin acoplarse al estado de Terraform. Todo no-secreto.

locals {
  deploy_params = {
    cluster            = aws_ecs_cluster.main.name
    private_subnet_ids = join(",", local.network.private_subnet_ids)
    migrate_task_def   = aws_ecs_task_definition.migrate.family
    migrate_sg_id      = local.network.service_security_group_ids["api"]
    services           = join(",", [for s in local.services : aws_ecs_service.service[s].name])
  }
}

resource "aws_ssm_parameter" "deploy" {
  for_each = local.deploy_params

  name  = "/nexus/${terraform.workspace}/deploy/${each.key}"
  type  = "String"
  value = each.value
}
