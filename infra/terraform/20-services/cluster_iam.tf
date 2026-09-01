# Cluster ECS + IAM por servicio (permiso mínimo, WP-27 adelantado: sin
# claves de larga duración — los servicios asumen su task role).

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  lifecycle {
    precondition {
      condition     = contains(["staging", "prod"], terraform.workspace)
      error_message = "Workspace inválido '${terraform.workspace}': terraform workspace select staging|prod."
    }
  }
}

# ── Execution role (compartida): pull ECR + logs + leer el secreto ─────

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid     = "ReadAppSecret"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      local.data.app_secret_arn,
      # PgBouncer lee la password cruda del secreto gestionado por RDS.
      local.data.aurora_master_secret_arn,
    ]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-app-secret"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# ── Task roles por servicio ────────────────────────────────────────────

locals {
  services = ["api", "runner", "scheduler", "egress", "metering"]

  # Qué servicios tocan S3 media: la API presigna y sirve, el runner
  # descarga media entrante (WP-11), egress adjunta salientes. El
  # scheduler no toca media.
  s3_media_services = ["api", "runner", "egress"]
}

resource "aws_iam_role" "task" {
  for_each = toset(local.services)

  name               = "${local.name}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# El sidecar ADOT escribe métricas EMF vía CloudWatch Logs y traces a X-Ray.
data "aws_iam_policy_document" "adot" {
  statement {
    sid = "EmfAndTraces"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "task_adot" {
  for_each = toset(local.services)

  name   = "adot-emf"
  role   = aws_iam_role.task[each.key].id
  policy = data.aws_iam_policy_document.adot.json
}

# ── ECS Exec en staging ────────────────────────────────────────────────
#
# Aurora es privada y no hay bastión: sin esto, consultar la BD o inspeccionar
# un servicio exige levantar una task efímera cada vez. ``litellm.tf`` ya
# tenía el mismo patrón para el proxy; esto lo extiende a ``api``, que es el
# contenedor con la ``DATABASE_URL`` de la aplicación.
#
# **Solo staging.** En producción el acceso a un shell dentro del contenedor
# que sirve los webhooks no se abre por comodidad: allí se sigue usando la
# task efímera de ``migrate`` con ``containerOverrides``.
locals {
  ecs_exec_services = terraform.workspace == "staging" ? ["api"] : []
}

data "aws_iam_policy_document" "task_ecs_exec" {
  statement {
    sid = "EcsExecChannels"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "task_ecs_exec" {
  for_each = toset(local.ecs_exec_services)

  name   = "ecs-exec"
  role   = aws_iam_role.task[each.key].id
  policy = data.aws_iam_policy_document.task_ecs_exec.json
}

data "aws_iam_policy_document" "s3_media" {
  statement {
    sid = "MediaBuckets"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "${local.data.media_bucket_arn}/*",
      "${local.data.state_blobs_bucket_arn}/*",
    ]
  }

  statement {
    sid       = "MediaBucketsList"
    actions   = ["s3:ListBucket"]
    resources = [local.data.media_bucket_arn, local.data.state_blobs_bucket_arn]
  }
}

resource "aws_iam_role_policy" "task_s3_media" {
  for_each = toset(local.s3_media_services)

  name   = "s3-media"
  role   = aws_iam_role.task[each.key].id
  policy = data.aws_iam_policy_document.s3_media.json
}
