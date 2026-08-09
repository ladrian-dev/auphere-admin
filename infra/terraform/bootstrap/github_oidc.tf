# Rol OIDC para GitHub Actions (deploy-staging.yml, y prod en WP-26).
# Sin claves de larga duración (WP-27): el workflow asume este rol vía el
# proveedor OIDC de GitHub, restringido al repo y a las ramas de deploy.

variable "github_repo" {
  description = "owner/repo autorizado a asumir el rol de deploy."
  type        = string
  default     = "ladrian-dev/auphere-admin"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # Thumbprint legacy; AWS valida hoy contra su propia CA store y lo ignora,
  # pero el campo es obligatorio en la API.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # develop (staging) y main (prod, WP-26). Nada de PRs ni forks.
    # OJO: cuando el job declara ``environment:``, GitHub emite el sub como
    # ``repo:<owner/repo>:environment:<nombre>`` — NO el ref. Sin esas
    # entradas el assume falla con "Not authorized" (visto en el deploy #2).
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repo}:ref:refs/heads/develop",
        "repo:${var.github_repo}:ref:refs/heads/main",
        "repo:${var.github_repo}:environment:staging",
        "repo:${var.github_repo}:environment:production",
      ]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "nexus-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = [for r in aws_ecr_repository.repos : r.arn]
  }

  statement {
    sid = "EcsDeploy"
    actions = [
      "ecs:RunTask",
      "ecs:StopTask",
      "ecs:DescribeTasks",
      "ecs:DescribeServices",
      "ecs:UpdateService",
      "ecs:DescribeTaskDefinition",
    ]
    resources = ["*"]
    # Limitado por cluster con tag de proyecto en vez de ARNs (los ARNs de
    # task son dinámicos); los clusters nexus-* son los únicos del proyecto.
  }

  statement {
    sid       = "PassTaskRoles"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/nexus-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid       = "ReadDeployParams"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:*:${local.account_id}:parameter/nexus/*/deploy/*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

output "github_deploy_role_arn" {
  description = "Pegar en GitHub como secret AWS_DEPLOY_ROLE_ARN."
  value       = aws_iam_role.github_deploy.arn
}
