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
  `queue_oldest_pending_seconds`; egress por `outbound_pending_messages`
  (gauge pendiente de publicar en la app — hasta entonces egress se queda en
  su mínimo, que es un estado seguro).

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
