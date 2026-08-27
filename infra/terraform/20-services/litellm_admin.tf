# Master recortado para POST /key/block|/key/unblock (OSS).
# Staging only. El proceso API hace GetSecretValue (task role).
# No valueFrom: execution-proxy, runner, Next y nexus/<ws>/app no lo ven.
# JSON: { "LITELLM_MASTER_KEY": "…" }. Luis rellena. Sin SALT/DB/vendor.

locals {
  litellm_admin_count = terraform.workspace == "staging" ? 1 : 0
}

resource "aws_secretsmanager_secret" "litellm_admin" {
  count = local.litellm_admin_count

  name        = "nexus/${terraform.workspace}/litellm-admin"
  description = "Solo LITELLM_MASTER_KEY. Block/unblock OSS. No SALT, no DATABASE_URL, no vendor, no VIRTUAL_KEYS."
}

data "aws_iam_policy_document" "api_litellm_admin" {
  count = local.litellm_admin_count

  statement {
    sid     = "ReadLitellmAdminMaster"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.litellm_admin[0].arn,
    ]
  }
}

resource "aws_iam_role_policy" "api_litellm_admin" {
  count = local.litellm_admin_count

  name   = "read-litellm-admin"
  role   = aws_iam_role.task["api"].id
  policy = data.aws_iam_policy_document.api_litellm_admin[0].json
}

output "litellm_admin_secret_arn" {
  description = "ARN del master recortado. Rellenar a mano. Null fuera de staging."
  value       = local.litellm_admin_count == 1 ? aws_secretsmanager_secret.litellm_admin[0].arn : null
}
