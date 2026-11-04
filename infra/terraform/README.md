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
# 20-services y 30-observability llevan además -var-file=<workspace>.tfvars.
```

Los stacks se leen entre sí vía `terraform_remote_state` usando el MISMO
workspace: aplicar `20-services` en workspace `staging` lee los outputs de
`00-network`/`10-data` del workspace `staging`.

## Cómo aplicar `30-observability`

Lo que difiere por entorno vive en `staging.tfvars` y `prod.tfvars`, y **no se
aplica con `-target`**: el plan completo es el que hay que leer.

```bash
export AWS_PROFILE=nexus AWS_REGION=eu-south-2   # el perfil por defecto es de otra cuenta
cd infra/terraform/30-observability
terraform init -backend-config=../backend.hcl
terraform workspace select staging               # o prod

terraform plan -var-file=staging.tfvars -out=staging.tfplan
terraform apply staging.tfplan
```

Los planes se guardan como `*.tfplan`, que git ignora. Un plan lleva dentro el
estado, con sus valores: no lo guardes con otra extensión, y este repo es público.

**Por qué olvidar algo no destruye nada.** `state_bucket`, `grafana_enabled` y
`alert_email` no tienen `default` a propósito. Antes, `grafana_enabled` valía
`false` si no se decía otra cosa, y un plan normal en staging destruía Grafana.

| Error | Qué pasa |
|---|---|
| Sin `-var-file`, con `-input=false` | `No value for required variable`, exit 1 |
| Sin `-var-file`, en una terminal | Terraform pregunta los valores. En staging no hay forma de contestar: `alert_email` tiene que ser `null`, y eso no se puede teclear |
| El `.tfvars` del otro entorno | `Resource precondition failed` en `aws_sns_topic.alerts`, exit 1. Terraform pinta encima un `Plan: … to destroy`, y es un plan fallido: **no se puede aplicar** |

**Quién recibe avisos.** Solo prod: `alert_email` tiene destinatario y las alarmas
van con `actions_enabled = true`. Staging no tiene suscriptor y todas sus alarmas
van con `actions_enabled = false`: aparca sus servicios de noche y cada mañana
registra un `worker_dead` que no es un fallo. Se miran en la consola.

### Hasta aplicarlo en los dos entornos

`imports.tf` adopta lo que ya existe en AWS sin recrearlo. En prod, y solo hasta
borrar ese archivo, hace falta una cosa más antes del plan:

```bash
export TF_VAR_alert_subscription_arn_to_import="$(aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:eu-south-2:793033583982:nexus-prod-alerts \
  --query 'Subscriptions[0].SubscriptionArn' --output text)"
```

**Ese ARN no se escribe en ningún archivo.** La suscripción se confirmó sin
autenticar, así que con su ARN `sns:Unsubscribe` no pide firma, y este repo es
público. Tampoco pegues la salida del plan en ningún sitio público: lo imprime.

Mientras no se aplique, cada plan enseña esto, y es lo esperado:

| Entorno | Plan | Qué es |
|---|---|---|
| staging | `0 to add, 6 to change, 0 to destroy` | Las 6 alarmas anteriores a la spec 051 pasan a `actions_enabled = false` y pierden `ok_actions`. `runner-queue-stalled` además coge los 4 periodos de evaluación que ya tiene prod |
| prod | `9 to import, 9 to add, 2 to change, 0 to destroy` | **Importa** la suscripción, 6 filtros y 2 alarmas hechos a mano. **Crea** las 7 alarmas y 2 filtros de la spec 051. **Cambia** solo las etiquetas de las 2 alarmas importadas, que no tenían ninguna |

Los dos, además, avisan de que `aws_sns_topic_subscription.email` deja de estar
gestionada (`Some objects will no longer be managed by Terraform`). Es una entrada
del estado que apunta a un ARN que ya no existe: se olvida, y no se destruye nada.

Crear las alarmas de la spec 051 en prod hace sonar la de la DLQ si sigue con
entradas: es un correo, y es lo que se quiere comprobar (spec 051, T036).

**Cuando estén aplicados los dos,** cada plan tiene que decir `No changes`. Entonces
borra `imports.tf` y la línea `alert_subscription_arn_to_import` de `staging.tfvars`,
en un commit aparte: hasta ese momento, prod sigue pidiendo la variable.

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

Cada entorno lo declara en su `.tfvars`: `grafana_enabled = true` en staging,
donde está en marcha, y `false` en prod. La variable no tiene `default`.
Encenderlo por primera vez en un entorno son cuatro pasos, y el orden importa
porque ECS **aborta el arranque de la task si un `valueFrom` no resuelve** — un
secreto vacío no da un error legible, da un servicio reintentando con
`runningCount = 0` para siempre.

```bash
# 1. La base de estado de Grafana (Aurora no es alcanzable desde fuera del
#    VPC; va por task efímera con la task definition de migración).
aws ecs run-task --cluster nexus-<ws> --task-definition nexus-<ws>-migrate ... \
  --overrides '{"containerOverrides":[{"name":"migrate","command":["sh","-lc",
    "psql \"$DATABASE_URL\" -c '\''CREATE DATABASE grafana'\''"]}]}'

# 2. El secreto, ANTES del servicio. Aquí sí hay -target, porque el resto de
#    Grafana todavía no puede arrancar.
terraform apply -target=aws_secretsmanager_secret.grafana \
  -var-file=<ws>.tfvars -var grafana_enabled=true
aws secretsmanager put-secret-value --secret-id nexus/<ws>/grafana --secret-string \
  '{"GF_SECURITY_ADMIN_PASSWORD":"...","NEXUS_REPORTING_DB_PASSWORD":"..."}'

# 3. La imagen (arm64) — normalmente la construye .github/workflows/deploy-grafana.yml.
docker buildx build --platform linux/arm64 -f infra/grafana/Dockerfile \
  -t <ecr>/nexus-grafana:staging --push infra/grafana

# 4. El resto del stack: `grafana_enabled = true` en <ws>.tfvars, y aplicar.
terraform apply -var-file=<ws>.tfvars
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


## LiteLLM OSS (staging only, `20-services`)

Apagado por defecto (`litellm_enabled = false`) para que un `apply` de
`20-services` no levante el proxy sin pedirlo. **Solo staging**: aunque
el flag se pase en el workspace `prod`, el `count` es 0. No aplicar este
servicio en prod. No reutilizar Valkey. No poner las keys en
`nexus/staging/app` — van al secreto propio `nexus/staging/litellm`.

Encenderlo la primera vez son tres pasos, y el orden importa porque ECS
**aborta el arranque de la task si un `valueFrom` no resuelve**.

```bash
# 0. Workspace. Nunca prod.
terraform workspace select staging

# 1. La base `litellm` en el Aurora que ya existe (Aurora no es alcanzable
#    desde fuera del VPC; va por task efímera con la task definition de
#    migración). Mismo estilo que Grafana.
aws ecs run-task --cluster nexus-<ws> --task-definition nexus-<ws>-migrate ... \
  --overrides '{"containerOverrides":[{"name":"migrate","command":["sh","-lc",
    "psql \"$DATABASE_URL\" -c '\''CREATE DATABASE litellm'\''"]}]}'

# 2. SG en 00-network ANTES de planear 20-services: el stack lee
#    litellm_security_group_id del remote state.
cd 00-network
terraform apply

# 3. El secreto, ANTES del servicio.
cd ../20-services
terraform apply -target=aws_secretsmanager_secret.litellm -var litellm_enabled=true
# Rellenar a mano (valores NO van en este repo): LITELLM_MASTER_KEY (sk-…),
# LITELLM_SALT_KEY, DATABASE_URL (postgres DIRECTO a la base `litellm`,
# no PgBouncer), ANTHROPIC_API_KEY, OPENAI_API_KEY.
# Mapping partner→VK: secreto aparte nexus/staging/litellm-partner-keys
# (JSON {partner_id: sk-…}). No va aquí ni en app. Luis rellena tras
# /key/generate. No apply de api/runner hasta entonces.

# 4. El resto de 20-services.
terraform apply -var litellm_enabled=true
```

Sin ALB: el DNS interno es `litellm.nexus-staging.internal:4000` (Cloud
Map). Las tasks de staging reciben `LITELLM_PROXY_API_BASE`; las de prod
no.

## Secretos

`10-data` crea el secreto `nexus/<workspace>/app` VACÍO. Los valores se cargan
a mano (o vía Doppler sync, WP-27): un único JSON cuyas claves son los nombres
de variable (`NEXUS_DATABASE_URL`, `NEXUS_FERNET_KEY`, …). Las task
definitions mapean cada clave con `valueFrom: <arn>:<clave>::`. La contraseña
maestra de Aurora la gestiona RDS en su propio secreto; `NEXUS_DATABASE_URL`
se construye con ella al poblar el secreto de app.

## CI

`develop` → staging automático (`.github/workflows/deploy-staging.yml`, sin
pasar por el workflow `ci`, ver `docs/develop-sin-tuberia.md`): build+push de
imágenes, task de migración (bloqueante), `update-service
--force-new-deployment` de los 4 servicios.
Los parámetros de red que CI necesita (cluster, subredes, SG) los publica
`20-services` en SSM bajo `/nexus/<workspace>/deploy/*`.


## LiteLLM OSS proxy (staging)

Apagado por defecto (`litellm_enabled = false`). `count` es 0 fuera de
staging: un apply de prod con el flag no crea el servicio. Sin ALB. Sin
Valkey (el de streams es `noeviction`). Secreto propio
`nexus/staging/litellm`, no `nexus/staging/app`.

Desde el 2026-11-03 nadie llama por él (enmienda de ADR-036): `llm_via_proxy` está
en `false` en `staging.tfvars`, y los servicios van directos al proveedor. El proxy
sigue encendido solo para poder volver atrás, poniéndola a `true` y aplicando.

```bash
# Solo: terraform workspace select staging

# 1. SG (00-network) — ingress 4000 desde los servicios, 5432 hacia Aurora.
# 2. Base propia en el Aurora que ya hay (no tablas Nexus, no PgBouncer).
aws ecs run-task --cluster nexus-staging --task-definition nexus-staging-migrate ... \
  --overrides '{"containerOverrides":[{"name":"migrate","command":["sh","-lc",
    "psql \"$NEXUS_DATABASE_URL_DIRECT\" -c '\''CREATE DATABASE litellm'\''"]}]}'

# 3. Secreto ANTES del servicio.
terraform apply -target=aws_secretsmanager_secret.litellm -var litellm_enabled=true
# Rellenar a mano (valores no van en git): LITELLM_MASTER_KEY (sk-),
# LITELLM_SALT_KEY, DATABASE_URL (db litellm, host del cluster, no pgbouncer),
# ANTHROPIC_API_KEY, OPENAI_API_KEY.

# 4. Servicio.
terraform apply -var litellm_enabled=true
```

DNS interno: `litellm.nexus-staging.internal:4000`. Partner no ve la UI.
Vendor keys salen del task del proxy, no de api/worker.
