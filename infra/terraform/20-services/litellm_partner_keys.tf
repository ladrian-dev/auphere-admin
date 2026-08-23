# Mapping partner_id → virtual key de LiteLLM. Staging only.
# No vive en nexus/<ws>/app ni en nexus/<ws>/litellm (master/salt/vendor).
# El JSON entero es el mapa; ECS lo inyecta como LITELLM_PROXY_VIRTUAL_KEYS
# (valueFrom del ARN, sin :clave::). Keys no son proxy_admin.
# No apply de task defs / execution-proxy hasta que Luis rellene el JSON
# (ECS aborta si valueFrom no resuelve). Prod: count = 0.

locals {
  litellm_partner_keys_count = terraform.workspace == "staging" ? 1 : 0
}

resource "aws_secretsmanager_secret" "litellm_partner_keys" {
  count = local.litellm_partner_keys_count

  name        = "nexus/${terraform.workspace}/litellm-partner-keys"
  description = "JSON {partner_id: sk-…}. Env LITELLM_PROXY_VIRTUAL_KEYS en api/runner. Luis rellena tras /key/generate. No proxy_admin."
}

# Execution role solo para api+runner. El role compartido (egress,
# metering, scheduler, migrate) no recibe GetSecretValue de este ARN.

resource "aws_iam_role" "execution_proxy" {
  count = local.litellm_partner_keys_count

  name               = "${local.name}-ecs-execution-proxy"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_proxy_managed" {
  count = local.litellm_partner_keys_count

  role       = aws_iam_role.execution_proxy[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_proxy_secrets" {
  count = local.litellm_partner_keys_count

  statement {
    sid     = "ReadAppSecret"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      local.data.app_secret_arn,
      local.data.aurora_master_secret_arn,
    ]
  }

  statement {
    sid     = "ReadPartnerKeys"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.litellm_partner_keys[0].arn,
    ]
  }
}

resource "aws_iam_role_policy" "execution_proxy_secrets" {
  count = local.litellm_partner_keys_count

  name   = "read-app-and-partner-keys"
  role   = aws_iam_role.execution_proxy[0].id
  policy = data.aws_iam_policy_document.execution_proxy_secrets[0].json
}
