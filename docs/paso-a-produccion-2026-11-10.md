# Paso a producción del 2026-11-10: develop → main

Sustituye al checklist del 2026-11-08: se ha rehecho contra el estado real de
producción. `main` no se despliega desde el 22 de octubre (`daf0ca15`). Entra todo
lo de `develop` desde entonces, de la spec 043 a la 057, más la rama
`chore/paso-a-produccion-2026-11-10`.

> **Desplegado el 2026-11-10** (`ec5c74e5`, PR 18). `deploy-prod` en verde a las
> 18:21 UTC: la migración llegó a `0230_audit_words_agenda` en 1 min 23 s y los
> cinco servicios rodaron con `prod-ec5c74e5…`. Lo que queda abierto está en
> [Pendiente tras el despliegue](#pendiente-tras-el-despliegue).

- **Migraciones**: de la `0165` a la `0230`, 69 (cuatro números se repiten) en **una sola transacción**
  (`alembic/env.py`). Si una falla, no se aplica ninguna y producción sigue como
  estaba. La base pesa 209 MB, con unos 60.000 mensajes: se espera que tarde
  minutos, no más. `deploy-prod` espera ahora hasta 45 minutos (antes se rendía a
  los 10 aunque la tarea siguiera).
- **Clientes que tienen que seguir funcionando**:
  - **Mouna** (`b10f04ea`): agente admin de cobranza con `billing.*` de
    `amigable_cobro`, más el cron diario de recordatorios.
  - **New Air** (`9798d5cd`): sin agente. Su sistema llama a
    `POST /v1/messages/template` hacia las 13:01 UTC.
  - **meta-review-demo** (`83b79aab`) se queda activo por la revisión de Meta.
- **Reservas**: ningún cliente lo tiene ni lo tendrá tras el despliegue. El paso
  automático a Reservas ya no corre al desplegar (spec 048, requisito 3,
  enmendado el 2026-11-10). Habría activado Reservas en 7 clientes y republicado
  sin pruebas meta-review-demo y demo-lorenzo, que tienen `booking.*` en su
  versión activa.

---

## Hecho el 2026-11-10 (no repetir)

- **Imágenes de producción protegidas.** La regla de ECR de las 50 últimas había
  borrado `nexus-api:prod` y `nexus-worker:prod`: una tarea de prod que se
  reiniciara no habría arrancado. Ahora lo etiquetado `prod*` tiene su propia
  regla y se conservan las 10 últimas (`infra/terraform/bootstrap/main.tf`,
  aplicado).
  - La imagen de `main` se reconstruyó relanzando el `deploy-prod` del 22-oct
    (mismo código, migración sin cambios, servicios estables).
  - Lleva la etiqueta `prod-daf0ca15f2633270adb13298499b0c75f296f763`: es la
    vuelta atrás.
  - Desde esta rama, cada `deploy-prod` empuja también `prod-<sha>`.
- **Secreto** `NEXUS_CUSTOMERS_APP_TOKEN_SECRET` creado en `nexus/prod/app`
  (aleatorio). Sin él, el código nuevo se niega a arrancar en producción. No
  cambia nada hasta aplicar Terraform (paso 0).
- **Comprobado en producción** con consultas de solo lectura:
  - Ningún cliente tiene AgendaPro (la 0205 no aborta).
  - No hay bajas duplicadas (la 0206 no aborta).
  - Ningún documento de conocimiento supera el tope de la 0193.
  - No hay recordatorios pendientes.
  - Los 3 admins de Mouna están en E.164 (la 0192 los conserva).
  - `amigable_cobro` está conectado y `billing.*` está en el catálogo con su
    conector (la 0194 creará la activación).
  - Existe la fila `anthropic/claude-haiku-4-5` (la 0221 la copia).
  - Las colas de coexistencia están vacías: no habrá silencios de 2 h por ecos
    viejos.
  - La clave de Anthropic de producción responde con `claude-haiku-5-5` (el
    clasificador nuevo).
  - Las 39 plantillas de correo de Resend están en orden.
- **Planes de Terraform de producción leídos**:
  - `20-services`: reemplaza las 6 task definitions y actualiza los 5 servicios.
    Añade `NEXUS_CUSTOMERS_APP_TOKEN_SECRET` y quita `BROWSERBASE_*` y
    `NEXUS_OPERATOR_ALERT_EMAIL`.
  - `30-observability`: importa 9, crea 10, cambia 2 (solo etiquetas) y no
    destruye nada.
- **`ci` sobre `develop`** (`e06a0fbc`): todo en verde salvo 1 fallo de 2.078 en
  `test-api`. El tipo de trabajo `agenda_text` (057) no tenía su mundo en el
  barrido del proxy. Arreglado en esta rama.

---

## 0 · Antes de fusionar

- [x] La rama `chore/paso-a-produccion-2026-11-10` fusionada en `develop`, con
  `deploy-staging` en verde. En `/nexus/staging/migrate` sale `release: done` y
  ninguna línea `reservations.auto_pass`.
- [x] `ci` en verde sobre el `develop` final (`ea927945`) y sobre `main`
  (`ec5c74e5`).
- [ ] **GitHub → Settings → Environments → `production` → Required reviewers.**
  Hoy no tiene ninguna regla: fusionar en `main` despliega sin pedir permiso en
  cuanto `ci` termina. *No se puso: decisión de Luis del 2026-11-10.*
- [x] **New Air como solo envío**: panel → New Air → números de WhatsApp → agente
  apagado (`agent_enabled=false`), igual que la línea de avisos de Mouna.
  - Hoy no cambia nada, porque no tiene agente.
  - Sin esto, con el código nuevo, cada conversación que le escriba quedaría
    esperando a una persona y mandaría un aviso de escalado por WhatsApp
    (`no_agent` → `agent_unpublished`).
- [x] **Pausar** flor-y-encanto (`c6e4c7c7`) y demo-lorenzo (`a2bfc92d`) desde el
  panel.
  - Un cliente en pausa no contesta y sus crons paran (el de WooCommerce de
    flor-y-encanto incluido).
  - No manda avisos: el avisador solo atiende clientes activos.
  - Los 5 clientes en alta de Amacrux y Acme (`provisioning`) pasan a `active` con
    la 0181, pero no tienen ni canal ni versión publicada, así que no corre nada
    para ellos.
- [x] **Ventana**: fuera de 12:45–14:15 UTC. A las 13:01 llegan los envíos de New
  Air y a las 13:08 barre el cron de cobranza de Mouna. *Se desplegó a las
  18:16 UTC.*
- [x] **Snapshot manual** de `nexus-prod-aurora` con nombre
  `pre-develop-2026-11-10` (17:03 UTC).
- [x] **Terraform `20-services` en prod**, justo antes de fusionar. El plan tiene
  que ser el de arriba: 6 task definitions reemplazadas y 5 servicios
  actualizados.
  - Rueda los servicios con la imagen de `main`, mismo código.
  - Sin este paso, la migración del código nuevo no arranca: le falta el secreto.

```bash
export AWS_PROFILE=nexus AWS_REGION=eu-south-2 TF_WORKSPACE=prod
cd infra/terraform/20-services
terraform plan -var-file=prod.tfvars -var state_bucket=nexus-terraform-state-793033583982 -out=prod.tfplan
terraform apply prod.tfplan
```

- [x] **Terraform `30-observability` en prod**: las alarmas que sustituyen al correo
  de `platform_watcher` (spec 051). El plan tiene que dar 9 importaciones, 10
  altas, 2 cambios y 0 bajas.

```bash
export AWS_PROFILE=nexus AWS_REGION=eu-south-2 TF_WORKSPACE=prod
export TF_VAR_alert_subscription_arn_to_import="$(aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:eu-south-2:793033583982:nexus-prod-alerts --query 'Subscriptions[0].SubscriptionArn' --output text)"
cd infra/terraform/30-observability
terraform plan -var-file=prod.tfvars -out=prod.tfplan
terraform apply prod.tfplan
```

- [ ] **Pausar la consola**: Vercel → `auphere-console` → Settings → Git →
  desactivar los despliegues automáticos. La consola nueva habla con rutas que la
  API vieja no tiene. *No se hizo: Luis asumió el riesgo. La consola nueva
  convivió unos 70 min con la API vieja, hasta que rodaron los servicios.*

## 1 · Fusionar y desplegar

- [x] Fusionar el PR `develop` → `main` y aprobar `deploy-prod`.
- [x] En `/nexus/prod/migrate`: `alembic upgrade head` hasta
  `0230_audit_words_agenda`, el sembrado de conectores y `release: done`. **Ninguna**
  línea `reservations.auto_pass`.
- [x] Servicios estables (`roll services` en verde) y salud contra el ALB con el
  certificado verificado. La IP del ALB cambia (el 2026-11-10 era `89.60.74.158`),
  así que se resuelve en el momento:

```bash
curl --resolve "api.auphere.com:443:$(dig +short nexus-prod-317439020.eu-south-2.elb.amazonaws.com | head -1)" https://api.auphere.com/health
```

## 2 · Soltar las consolas

- [x] Reactivar los despliegues de `auphere-console` y redesplegar el último
  commit de `main`. Desplegar el Admin (`auphere-admin`) desde `main`. *Vercel
  los desplegó solo con `ec5c74e5`, en verde, y los dos responden.*
- [ ] Los partners de Mouna (Amacrux) y New Air (Facelad) entran en la consola
  nueva: la 0204 la enciende para todos.

## 3 · Comprobar en producción

- [ ] **Mouna, agente**: el siguiente mensaje de un admin da `handler.turn_complete`
  en `/nexus/prod/runner`. *A las 18:35 UTC aún no había escrito ningún admin.
  Una tarea suelta con la definición del runner pasó el nodo de clasificar real
  por `anthropic/claude-haiku-5-5`: etiqueta en 1 s, sin reserva y sin tocar la
  base.*
  - Hay `llm.call_complete` con `role=classify` y `model=anthropic/claude-haiku-5-5`.
  - `classify.unknown_label_using_fallback` queda cerca de cero.
  - No hay `tool.error` de `billing.*`.
  - En la consola, el agente muestra `amigable_cobro` activado.
- [ ] **Mouna, cobranza**: al día siguiente hacia las 13:08 UTC sale
  `cobranza_reminder_cron.swept`, y `cobranza_reminder.queued` si hay
  vencimientos.
- [ ] **New Air**:
  - El siguiente `POST /v1/messages/template` responde `pending` y egress da
    `outbound.dispatcher.sent`.
  - Sus entrantes dan `pipeline.skipped.send_only_channel`. *Visto: 2 tras el
    despliegue.*
  - No hay `operator_alerter.sent` de New Air. *Visto: ninguno.*
- [x] **Reservas**: ningún cliente lo tiene encendido. *Comprobado en la base:
  ninguna fila en `reservation_settings` y ningún `client_access` con
  `reservas`.*
- [x] **DLQ de entrada**: `./scripts/ops/dlq.sh prod list`. La herramienta solo
  existe con el código nuevo. Quedan 25 entradas del incidente de Aurora de
  agosto; decidir y vaciar (`docs/dlq.md`). La alarma nueva solo avisa de
  entradas nuevas. *Eran 19 de New Air y 6 de Mouna, de hace 75 días, todas
  por `password authentication failed`. Descartadas a las 18:46 UTC con el
  permiso de Luis; la DLQ queda vacía.*
  - **Ojo**: listar o descartar escribe esa causa en `/nexus/prod/scheduler`, y
    el filtro de `nexus-prod-db-auth-failures` busca ese texto. Cada pasada
    dispara un correo falso de «fallos de autenticación en la base», más el de
    vuelta a OK (18:33 y 18:47 UTC). El filtro está hecho a mano, fuera de Terraform.
- [x] **Alarmas**: confirmar que llega el correo de SNS y que ninguna salta sin
  motivo en la primera hora. *Solo saltó `nexus-prod-platform-alert-dlq-entries`,
  a las 18:01 UTC: el vigilante viejo contaba las 25 de agosto. Vuelve a OK
  cuando su ventana de 36 puntos quede sin datos.*
- [ ] **Avisar a Andrés**: la agenda nativa revierte sus commits del 3 y 4 de
  noviembre.

## Lo que cambia para los clientes (aceptado)

- **Bajas** (spec 050, decidido el 2026-11-10): una baja escrita solo frena el
  marketing. Las plantillas de utilidad de New Air y los recordatorios de Mouna
  salen igual. En producción hay 1 baja activa.
- **Clasificador**: Haiku 5.5 en lugar de `gpt-5.6-sol`. Los mensajes se agrupan
  durante 3 s en lugar de 1,5 s. WhatsApp pasa a Graph v26.
- **Admins de Mouna**: desde la 0192 y la 0204 manda la audiencia del canal
  («Solo mi equipo», con sus 3 números). Para cambiarlos, la página del canal;
  `set_cobranza_admins.py` y `admin_access` ya no deciden a quién se responde.
- **Sugerencias semanales**: una llamada al modelo por agente con 5 conversaciones
  y 5 contactos la semana anterior. Solo deja un aviso en la campana del partner.
  *Retiradas por Luis el mismo 2026-11-10 (spec 047, criterio 51.7): ver
  pendientes.*

## Pendiente tras el despliegue

- **Las sugerencias semanales no salen en producción.** La primera pasada
  (18:19 UTC) falló para Mouna y para flor-y-encanto con `LLMProxyUnavailable`,
  y sus trabajos quedaron `failed` (`suggestions_unavailable`).
  - Cada una tardó unos 91 s: tres cortes de 30 s. `default_complete` de
    `weekly_suggestions_cron.py` usa el plazo por defecto del proveedor (30 s,
    con dos reintentos del SDK). El constructor ya se arregló así (120 s, sin
    reintentos).
  - En staging las dos pasadas que salieron llevaban unos 1.700 tokens y
    tardaron de 3 a 5 s. Una semana real de Mouna no cabe en 30 s.
  - `map_proxy_failure` traduce el corte a «proxy unreachable», aunque producción
    no usa proxy.
  - El cron lo reintenta hasta 3 veces por agente y semana, una por hora, y
    luego para. No toca conversaciones ni factura al cliente.
  - Además corre para clientes en pausa (flor-y-encanto): `_tenants` solo
    descarta los archivados.
  - **Decisión de Luis (2026-11-10): retirarlas por ahora.** El agente debe
    mejorarse solo, no avisar al partner. Spec 047, criterio 51.7 y fase 30
    (T247–T250): el worker deja de arrancar el cron y «Mejoras» deja de
    prometerlas. Hasta que llegue a `main`, producción lo sigue intentando: hasta
    3 veces por agente y semana, sin cobrar a nadie.
- **Filtro de `db-auth-failures`**: que no cuente las líneas `ops.dlq.*`. Por
  ejemplo, el patrón `"password authentication failed" -"ops.dlq"` en los cinco
  filtros de prod.
- **Mouna**: comprobar el primer turno real y la cobranza del 2026-11-11 hacia
  las 13:08 UTC.
- **New Air**: comprobar el envío de plantillas del 2026-11-11 hacia las 13:01
  UTC.
- **Avisar a Andrés.**

## Si algo va mal

| Síntoma | Causa y salida |
|---|---|
| La migración falla | Una sola transacción: no se aplicó nada y producción sigue con `main`. Leer `/nexus/prod/migrate`, corregir y relanzar |
| La migración no termina en 45 min | Servicios sin tocar. No relanzar sin mirar antes `/nexus/prod/migrate` y los bloqueos en Aurora |
| Un servicio no se estabiliza | El circuit breaker vuelve a la task definition anterior, **pero `prod` ya apunta a la imagen nueva**: no es una vuelta atrás. Leer el registro del servicio y arreglar hacia delante |
| Hay que volver a `main` de verdad | El esquema nuevo no sirve a `main` (la 0205 borra columnas que `main` lee). Restaurar el snapshot del paso 0 y apuntar las task definitions a `prod-daf0ca15…`. Se pierde lo escrito entre medias: es decisión de Luis |
| Consola: «sin acceso» | La consola nueva habla con la API vieja. Esperar a que termine `deploy-prod` o volver a la consola anterior en Vercel |
| Mouna no contesta a un admin | `pipeline.skipped.*` en el runner: `not_admin` es la audiencia del canal; `no_balance` o `wallet_empty` serían la bolsa (tiene consumo ilimitado) |
| New Air recibe errores en la API | `api.messages.template.*` en `/nexus/prod/api`. La ruta y la autenticación no cambian entre ramas |
