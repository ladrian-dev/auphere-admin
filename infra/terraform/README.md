# Nexus — Terraform (AWS eu-south-2)

WP-23/24/25 del plan v2. Cuatro stacks + un bootstrap, con **workspaces**
`staging` y `prod` compartiendo el mismo código y difiriendo solo en tamaños
(ver `locals.sizing` en cada stack).

```
bootstrap/          Estado remoto (S3 + DynamoDB) y ECR compartido. Estado LOCAL, se aplica una vez.
00-network/         VPC, subredes, NAT, security groups por servicio, S3 gateway endpoint.
10-data/            Aurora PG Serverless v2 (pgvector), ElastiCache Valkey, S3+CloudFront, Secrets Manager.
20-services/        ECS Fargate: cluster, ALB, task definitions, servicios, autoescalado, task de migración.
30-observability/   SNS + alarmas CloudWatch (ALB, colas, Aurora, Valkey).
```

## Orden de aplicación

```bash
# 1. Bootstrap (una sola vez por cuenta; estado local, commitear el .tfstate NO — guardarlo en S3 a mano o re-importar)
cd bootstrap && terraform init && terraform apply

# 2. Copiar la salida a backend.hcl (los backends S3 no aceptan variables)
cp backend.hcl.example ../backend.hcl   # y rellenar bucket/dynamodb_table/region

# 3. Cada stack, en orden, por workspace:
cd ../00-network
terraform init -backend-config=../backend.hcl
terraform workspace new staging   # o: terraform workspace select staging
terraform apply
# ... repetir para 10-data, 20-services, 30-observability
```

Los stacks se leen entre sí vía `terraform_remote_state` usando el MISMO
workspace: aplicar `20-services` en workspace `staging` lee los outputs de
`00-network`/`10-data` del workspace `staging`.

## Decisiones fijadas (y por qué)

- **ECR vive en `bootstrap/`, no por workspace.** Los repos `nexus-api` y
  `nexus-worker` son artefactos de cuenta: staging y prod consumen las mismas
  imágenes (promoción por tag/digest, WP-26). Lifecycle **keep-50** — hay
  precedente real de keep-10 podando imágenes de servicios ociosos.
- **Dos imágenes, cuatro servicios.** `runner`/`scheduler`/`egress` son la
  imagen `nexus-worker` con `command` distinto en la task definition — el
  mismo patrón que Railway hoy (`infra/railway/*.toml`). Un Dockerfile por
  servicio triplicaría builds sin ganar aislamiento: la separación real la
  dan las task definitions, IAM y security groups por servicio.
- **`max_connections` de Aurora fijado por parámetro** (500 staging / 2000
  prod) en vez del default derivado de ACU — documentado en
  `10-data/aurora.tf`; el pool real lo gobernará PgBouncer/RDS Proxy (WP-15).
- **Valkey sin TLS in-transit** (subredes privadas, SG cerrado): la app usa
  `redis://` y activar TLS exige migrar a `rediss://` en todos los clientes.
  Se revisita en WP-27 si SOC 2 lo exige.
- **La migración corre como task ECS previa al rollout** (`nexus-migrate`,
  definida en `20-services/migrate.tf`, ejecutada por CI). Exit != 0 aborta
  el deploy — mismo contrato que el `preDeployCommand` de Railway.
- **Métricas custom para autoescalado** llegan a CloudWatch (namespace
  `Nexus`) vía sidecar ADOT en cada task (OTLP → EMF). El runner escala por
  `queue_oldest_pending_seconds`; egress por `outbound_pending_messages`,
  que publica el sweep del dispatcher cada 30 s **sin dimensiones** (el
  collector va con `NoDimensionRollup`, así que una etiqueta rompería la
  política) apoyado en el índice parcial de la migración 0067.
- **El cert del ALB se pide aquí pero se valida a mano** (`20-services/acm.tf`):
  el DNS de auphere.com no vive en esta cuenta. Primer apply → cert
  `PENDING_VALIDATION` + los CNAME en el output
  `certificate_validation_records`; cuando ACM lo emite,
  `terraform apply -var https_enabled=true` crea el listener 443 y convierte
  el 80 en redirect. Staging pide el comodín de `staging.auphere.com`
  (un solo registro de validación cubre dominio + comodín).

## Grafana (WP-30b, `30-observability`)

Apagado por defecto (`grafana_enabled = false`) para que un `apply` de las
alarmas en un workspace nuevo no levante un servicio de más sin pedirlo.
Encenderlo por primera vez son cuatro pasos, y el orden importa porque ECS
**aborta el arranque de la task si un `valueFrom` no resuelve** — un
secreto vacío no da un error legible, da un servicio reintentando con
`runningCount = 0` para siempre.

```bash
# 1. La base de estado de Grafana (Aurora no es alcanzable desde fuera del
#    VPC; va por task efímera con la task definition de migración).
aws ecs run-task --cluster nexus-<ws> --task-definition nexus-<ws>-migrate ... \
  --overrides '{"containerOverrides":[{"name":"migrate","command":["sh","-lc",
    "psql \"$DATABASE_URL\" -c '\''CREATE DATABASE grafana'\''"]}]}'

# 2. El secreto, ANTES del servicio.
terraform apply -target=aws_secretsmanager_secret.grafana -var grafana_enabled=true
aws secretsmanager put-secret-value --secret-id nexus/<ws>/grafana --secret-string \
  '{"GF_SECURITY_ADMIN_PASSWORD":"...","NEXUS_REPORTING_DB_PASSWORD":"..."}'

# 3. La imagen (arm64) — normalmente la construye .github/workflows/deploy-grafana.yml.
docker buildx build --platform linux/arm64 -f infra/grafana/Dockerfile \
  -t <ecr>/nexus-grafana:staging --push infra/grafana

# 4. El resto del stack.
terraform apply -var grafana_enabled=true
```

Falta un paso que **no** hace Terraform: la migración `0078` crea el rol
`nexus_reporting` **sin contraseña** a propósito (una credencial en un
fichero de migración queda publicada en el historial de git para siempre).
Hay que ponérsela, y tiene que ser la misma que
`NEXUS_REPORTING_DB_PASSWORD` del secreto:

```sql
ALTER ROLE nexus_reporting PASSWORD '<la del secreto>';
```

Hasta ese momento la fuente de datos de Postgres da
`password authentication failed` y los paneles de coste salen vacíos; los
de CloudWatch y X-Ray funcionan igual, porque van por el rol IAM de la task.

El DNS es manual (auphere.com no vive en esta cuenta): `CNAME`
`grafana.<ws>.auphere.com` → el `alb_dns_name` de `20-services`. El cert
comodín `*.staging.auphere.com` ya lo cubre; **no** hace falta pedir uno.

## Secretos

`10-data` crea el secreto `nexus/<workspace>/app` VACÍO. Los valores se cargan
a mano (o vía Doppler sync, WP-27): un único JSON cuyas claves son los nombres
de variable (`NEXUS_DATABASE_URL`, `NEXUS_FERNET_KEY`, …). Las task
definitions mapean cada clave con `valueFrom: <arn>:<clave>::`. La contraseña
maestra de Aurora la gestiona RDS en su propio secreto; `NEXUS_DATABASE_URL`
se construye con ella al poblar el secreto de app.

## CI

`develop` → staging automático (`.github/workflows/deploy-staging.yml`, corre
tras el workflow `ci` verde): build+push de imágenes, task de migración
(bloqueante), `update-service --force-new-deployment` de los 4 servicios.
Los parámetros de red que CI necesita (cluster, subredes, SG) los publica
`20-services` en SSM bajo `/nexus/<workspace>/deploy/*`.
