# Un secreto JSON por entorno con TODA la config de app: cada clave es un
# nombre de variable (NEXUS_DATABASE_URL, NEXUS_FERNET_KEY, …) y las task
# definitions mapean clave→env con ``valueFrom: <arn>:<clave>::``.
#
# Los VALORES no viven en Terraform: se cargan a mano (o Doppler sync,
# WP-27). NEXUS_DATABASE_URL se construye con el endpoint del cluster y la
# password del secreto gestionado por RDS (output ``aurora_master_secret_arn``).

resource "aws_secretsmanager_secret" "app" {
  name        = "nexus/${terraform.workspace}/app"
  description = "Config de aplicación Nexus ${terraform.workspace} — JSON clave=env var"

  recovery_window_in_days = terraform.workspace == "prod" ? 30 : 7
}
