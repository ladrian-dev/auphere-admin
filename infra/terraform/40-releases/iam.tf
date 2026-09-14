# Quién puede publicar una versión (spec 008, R2.2).
#
# **Un rol distinto del de despliegue, y ésa es la decisión entera.** Si la
# cadena publicara con `AWS_DEPLOY_ROLE_ARN`, comprometer el despliegue de la
# plataforma sería, además, poder poner un binario en la máquina de un partner.
# Separarlos convierte R2.2 —«sólo la cadena escribe»— en algo comprobable: este
# rol no puede tocar ECS, y el de despliegue no puede escribir aquí.
#
# Se asume por OIDC, como el resto del repositorio. No hay claves estáticas, y
# menos en el trabajo que toca la superficie más delicada.

variable "github_repository" {
  type        = string
  description = "owner/repo que puede asumir el rol. Nadie más."
  default     = "ladrian-dev/auphere-admin"
}

#: **Desde qué refs**, y no sólo desde qué repositorio.
#:
#: La primera versión de esto decía `repo:<owner>/<repo>:*` — cualquier rama,
#: cualquier tag, cualquier entorno. Un audit lo encontró el 2026-09-14 y el
#: contraste que lo delató estaba en la propia cuenta: el rol de despliegue
#: (`nexus-github-deploy`) lleva acotadas cuatro refs concretas desde siempre.
#: Se había copiado el patrón de OIDC sin copiar el alcance, y justo en el rol
#: que publica binarios que se instalan en máquinas de clientes.
#:
#: Con el comodín, cualquiera con permiso de push podía crear una rama, escribir
#: un workflow que asumiera este rol y servir su propio paquete desde
#: `updates.auphere.com` — sin pasar por ninguna revisión, porque su workflow no
#: necesitaba llegar a `main`.
#:
#: `refs/tags/v*` es la publicación normal. `refs/heads/main` cubre el disparo
#: manual de un incidente, que corre sobre una rama y no sobre un tag.
variable "publish_refs" {
  type        = list(string)
  description = "Refs de GitHub que pueden asumir el rol de publicación."
  default     = ["ref:refs/tags/v*", "ref:refs/heads/main"]
}

# El proveedor OIDC de GitHub ya existe en la cuenta: lo creó el rol de
# despliegue. Se referencia, no se vuelve a crear — dos proveedores para el
# mismo emisor es un error que AWS ni siquiera deja cometer.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Acotado al repositorio **y a las refs**. Sin la primera condición
    # cualquier repositorio de GitHub podría asumir el rol —el fallo clásico de
    # OIDC, y silencioso—; sin la segunda, cualquier rama del repositorio
    # propio, que es el mismo agujero un paso más adentro.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for r in var.publish_refs : "repo:${var.github_repository}:${r}"]
    }
  }
}

resource "aws_iam_role" "publisher" {
  name               = "nexus-${terraform.workspace}-desktop-publisher"
  description        = "Publica versiones de la app de escritorio. NO despliega nada."
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "publish" {
  # Escribir, sólo dentro del prefijo del canal. Ni en la raíz del bucket ni en
  # ningún otro sitio de la cuenta.
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.desktop.arn}/${var.channel_prefix}/*"]
  }

  # Listar hace falta para saber qué hay publicado. Borrar NO está, y no es un
  # olvido: publicar es añadir y mover el puntero (R2.5). Un rol que no puede
  # borrar no puede dejar sin marcha atrás a nadie, ni por error ni a propósito.
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.desktop.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.channel_prefix}/*"]
    }
  }

  # Invalidar la caché al publicar, para que el índice nuevo se vea sin esperar
  # al TTL. Sólo eso: no puede modificar la distribución.
  statement {
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [aws_cloudfront_distribution.desktop.arn]
  }
}

resource "aws_iam_role_policy" "publish" {
  name   = "publish-desktop-releases"
  role   = aws_iam_role.publisher.id
  policy = data.aws_iam_policy_document.publish.json
}

output "publisher_role_arn" {
  description = "Va al secreto AWS_RELEASE_ROLE_ARN del repositorio."
  value       = aws_iam_role.publisher.arn
}
