# Nexus — Runbook operativo (Phase 1)

Este documento es la fuente de verdad operativa cuando algo se rompe en
producción. Está pensado para que Lee (operador único Phase 1) pueda
seguir los pasos sin tener el contexto completo del bloque que rompió.

Para arquitectura ver `Auphere/nexus/architecture/deployment.md` en el
KB. Para alertas y métricas ver
`Auphere/nexus/architecture/monitoring.md`.

---

## Stack en producción

| Pieza | Plataforma | Region | Notas |
|---|---|---|---|
| `nexus-api` | Railway | us-east | FastAPI Docker (`apps/api/Dockerfile`). Owns Alembic + Drizzle migrations via release command. |
| `nexus-worker` | Railway | us-east | Worker Docker (`apps/worker/Dockerfile`). Includes Node 20 runtime + `agendapro_browser_mcp/dist/` for the Stagehand subprocess. |
| `postgres` | Railway managed | us-east | Postgres 16 + pgvector. Apache AGE diferido a Phase 3+ (KG modelado relacional). |
| `redis` | Railway managed | us-east | Redis 7. |
| `auphere-admin` | Vercel | global | Next.js 16. Auto-deploy en `main` (configurable). |
| Secrets | Doppler | — | Workspace `auphere`, project `nexus`, configs `dev` + `production`. Sync nativo a Railway + Vercel. |
| LLM observability | Langfuse Cloud | — | Workspace `auphere`. SDK con noop fallback si las keys están vacías. |
| WhatsApp | Meta Cloud API (Tech Provider directo) | — | Webhook → `https://api.auphere.com/webhook/meta`. |
| Browser automation | Browserbase Startup | — | Aprovisionado en Bloque J cuando se onboardee Cultor Barber. |

DNS: `api.auphere.com` → Railway, `admin.auphere.com` → Vercel. Certs
auto via Let's Encrypt (Railway) y Vercel.

---

## Deploy (Phase 1: CLI manual desde local)

**Política Phase 1 (2026-05-12)**: deploys via Railway/Vercel CLI desde la
laptop de Lee, **no via GitHub Actions** (`deploy.yml` queda dormido como
fallback hasta Phase 2). Railway repo desconectado; Vercel admin debe
estar con auto-deploy DESACTIVADO antes de operar (verificar
**Settings → Git → "Deploy production builds on push to main" = OFF** o
equivalente según UI version).

Cuando entre Cultor en producción (Bloque K), revisitar política:
- Habilitar **branch protection en `main`** (CI verde requerido para merge).
- Reactivar `deploy.yml` (workflow_dispatch) → audit log + sync atómico
  API+Worker+Admin.

### Pre-requisitos una sola vez

```bash
railway login                  # auth Railway, queda en ~/.config/railway
vercel login                   # auth Vercel

# Link de proyecto Railway (selecciona auphere-nexus o lo que se llame)
cd /Users/lmatos/Workspace/nexus
railway link

# Link Vercel desde apps/admin
cd apps/admin
vercel link
cd ../..
```

### Deploy completo (los 3 servicios)

```bash
cd /Users/lmatos/Workspace/nexus

# 1. API primero (corre alembic + seed_connectors en preDeployCommand)
railway up --service nexus-api          # ~3 min

# 2. Worker después (sin migrations; el API ya las aplicó)
railway up --service nexus-worker       # ~3 min

# 3. Admin — deploy directo SIN build local
(cd apps/admin && vercel deploy --prod --yes)   # ~1 min Vercel buildea remoto
```

**IMPORTANTE Vercel + Sensitive env vars**: las env vars del proyecto
Vercel están marcadas como **Sensitive Environment Variables**
(Encrypted), lo que significa que ``vercel pull`` las baja como ``""``
por design — solo se inyectan en builds dentro de la infraestructura
Vercel. **NO usar el flow ``vercel build --prod`` + ``vercel deploy
--prebuilt``** porque el build local fallaría con ``DATABASE_URL must
be set``. El flow correcto es ``vercel deploy --prod`` directo:
Vercel pulls el código fuente, buildea en sus servers (donde tiene
acceso a las Sensitive vars), y deploya atomic. ~1 min wall clock
vs los 2-3 min del path build-local-y-prebuilt.

Ref: https://vercel.com/docs/projects/environment-variables#sensitive-environment-variables

Total: ~8 min wall clock. Verificación post-deploy:

```bash
curl -s https://api.auphere.com/health
# {"status":"ok"}

ADMIN_TOKEN=$(doppler secrets get NEXUS_ADMIN_TOKEN --plain --config=production)
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api.auphere.com/admin/connectors | python3 -m json.tool
# connectors custom: agendapro, whatsapp_meta, woocommerce (+ Composio dinámicos)

curl -s -o /dev/null -w "%{http_code}\n" https://admin.auphere.com/connectors
# 307 (redirect a login)
```

Atajos según cambio:

| Cambio | Comando |
|---|---|
| Solo frontend | `(cd apps/admin && vercel deploy --prod --yes)` |
| Solo API (sin cambios en código compartido) | `railway up --service nexus-api` |
| Solo worker | `railway up --service nexus-worker` |
| Touch a `nexus_api.db.models` / `nexus_channels` / `nexus_mcp` | **Ambos services** (API + worker comparten esos paquetes) |

### Deploy de un commit específico

```bash
git checkout <sha>
railway up --service nexus-api    # toma el HEAD del working tree
git checkout main                  # volver
```

### Logs en vivo

```bash
railway logs --service nexus-api
railway logs --service nexus-worker
# Admin: Vercel dashboard → Deployments → click en el deploy → Build/Runtime logs
```

### Disciplina operacional

- **No deployar con CI rojo** en main. Chequear `gh run list --branch main --limit 1`
  antes de `railway up`. CI no bloquea el deploy CLI, depende de tu memoria.
- **API antes que worker** siempre. Worker que arranca contra DB sin migrar = crash.
- **Verificación post-deploy es parte del deploy**, no es opcional. Si los curls
  no devuelven lo esperado, rollback inmediato (próxima sección).

## Deploy via GitHub Actions (Phase 2+ fallback)

Trigger normal: GitHub Actions → workflow `deploy` → `Run workflow` →
elegir `target=all`. Si Actions no responde:

### API + worker (Railway CLI desde laptop)

```bash
# Doppler trae los secrets locales si necesitás verificarlos antes.
doppler run --config production -- railway whoami

# Asegurarte de estar parado en el commit que querés cortar:
git checkout main && git pull
git log -1 --oneline

# Redeploy nexus-api (release command corre Alembic + Drizzle).
railway up --service nexus-api --detach

# El worker se redeploya solo SI cambió la imagen. Si solo cambió un
# secret, forzá:
railway redeploy --service nexus-worker
```

`railway up` toma el HEAD de tu working tree. Si querés deploy de un
commit puntual: `git checkout <sha>` antes.

### Admin (Vercel CLI desde laptop)

```bash
cd apps/admin
vercel pull --environment=production
vercel build --prod
vercel deploy --prebuilt --prod
```

---

## Rollback

### API o worker

Railway dashboard → service → Deployments → seleccionar el revision
previa que estaba sana → `Redeploy`. Atomic — el reverse cutover
toma <60s.

CLI:
```bash
railway redeploy --service nexus-api --version <prev>
```

Si la migración Alembic del release roto fue *forward-compatible* (caso
normal: `ADD COLUMN`, `CREATE TABLE`), el rollback de la imagen es
seguro sin tocar la DB. Si la migración fue destructiva
(`DROP COLUMN`, `ALTER TYPE`) hay que `alembic downgrade -1` también
— **siempre revisar primero**.

### Admin

Vercel dashboard → Project → Deployments → seleccionar deployment
anterior → menú `...` → `Promote to Production`. Sin cutover de DB.

### DB (último recurso)

Railway managed Postgres → Snapshots → el daily snapshot más reciente.
RPO Phase 1 es 24h — perdés hasta un día de data. Antes de restaurar:
- Avisar a Lee si hay otros operadores.
- Pausar `nexus-worker` (escala a 0 réplicas) para que no escriba
  contra el DB en flux.
- Restore.
- Re-bootear worker.

DR drill formal queda para Phase 2 (cuando hay 2+ clientes).

---

## Cómo agregar un secret

1. **Doppler** (source-of-truth). Workspace `auphere` → project `nexus`
   → config `production`. `New secret` con nombre `NEXUS_*` (pattern
   del proyecto).
2. **Sync automático** a Railway + Vercel via Doppler integrations
   (provisionadas en Bloque I). Verificá en cada plataforma:
   - Railway dashboard → service → Variables.
   - Vercel dashboard → Project → Settings → Environment Variables.
3. **Forzar redeploy** para que las apps lean el nuevo valor — los
   secrets se inyectan al boot del container, no en runtime. Para
   redeploy sin cambio de código: `railway redeploy --service
   nexus-api` y/o `vercel --prod`.

⚠️ Nunca pegues secretos en este repo, en Slack, ni en chat con
Claude. Doppler es el único lugar.

---

## Alembic downgrade (manual, solo Lee + revisión)

```bash
# Verificá la versión actual.
railway run --service nexus-api alembic current

# Generá un dry-run del SQL que ejecutaría el downgrade.
railway run --service nexus-api alembic downgrade -1 --sql > /tmp/down.sql
less /tmp/down.sql

# Si pinta limpio, ejecutalo.
railway run --service nexus-api alembic downgrade -1
```

**Nunca** corras downgrade automático desde CI. La regla del proyecto
(`architecture/deployment.md`): downgrade es manual con
revisión. Si una migración tuvo un bug forward-only y necesitás ir
para atrás, escribí una nueva migración hacia adelante que repare el
problema en lugar de revertir.

---

## Playbook — alerta P1 `isolation.*_violation`

Cuando llega `alert_isolation_v1` por WhatsApp al teléfono operador:

1. **Identificar la métrica** — el template incluye `metric_name` y
   `count`. Las 7 canónicas están en `architecture/agent-isolation.md`.
2. **Pull del row del breach** — abrir `admin.auphere.com` → Tenant
   afectado → tab `Aislamiento`. La card de la métrica muestra el
   `last_breach_at`. Para más detalle, query directa:
   ```sql
   SELECT * FROM isolation_events
     WHERE tenant_id = '<uuid>'
       AND metric = '<metric>'
     ORDER BY created_at DESC LIMIT 10;
   ```
3. **Si la métrica es `isolation.tool_whitelist_violation`**: el
   pipeline ya skipeó la tool — daño contenido. Investigar por qué el
   LLM intentó invocarla; típicamente prompt drift o tool inyectada
   por error en el whitelist nuevo. Promote rollback al
   `agent_config` previo si el sistema está claramente regresivo.
4. **Si es `isolation.cross_tenant_query` o
   `isolation.unscoped_query`**: **STOP THE LINE**. Hay un bug
   estructural — pausar el worker (`railway redeploy --service
   nexus-worker --replicas 0`), capturar el trace en Langfuse, abrir
   un bug en KB con skill `bug-report`, y rollback al revision
   previa. NO redeployar hasta tener un test que reproduzca.
5. **Documentar** en KB sesión + bug report. Auto-actualizar el
   counter del lado del operator alerter es idempotent (UNIQUE on
   `audit_log_id` previene re-fire), pero si querés bajar el ruido
   mientras investigás, podés silenciar via update temporal a
   `tenants.cost_alert_threshold_usd_per_day`. El silencer formal
   entra Phase 2.

---

## Playbook — alerta `alert_whatsapp_burst_v1`

Trigger: ≥5 errores 5xx contra la Cloud API en una ventana de 2min (Bloque
H). El alerter respeta cooldown de 5min para no spamear.

1. **Meta Cloud API status** — `https://metastatus.com`. Si hay incidente
   declarado, no hay nada que hacer del lado nuestro: el outbound
   dispatcher ya retri-i con backoff (`MAX_ATTEMPTS=3`). Comunicar al
   cliente afectado.
3. **Auth failure** — si los 5xx son 401/403 en realidad (algunos BSP
   los miscatigorizan), validar que el BISUAT del tenant sigue válido
   (badge "Requiere re-auth" en el panel → re-correr Embedded Signup).
4. **Rate limit** — Cloud API ~80 msg/s por número. Si un tenant
   excede, el outbound dispatcher se va a backoff hasta que el rate
   recupere. No requiere acción inmediata.
5. **Si todo está OK upstream**: capturar el wamid + body del error en
   Langfuse, abrir bug en KB. El WhatsAppBurstTracker es process-wide
   (Phase 1 = single worker); si hay falsos positivos por restarts,
   Phase 2 lo migra a Redis-backed counter.

---

## Playbook — alerta `alert_cost_threshold_v1`

Trigger: `daily_cost_snapshots.cost_usd_total >= cost_alert_threshold`
para ese tenant (default $40/día Pro). Una sola alerta por día por
tenant.

1. **Identificar el tenant + día** — el template incluye
   `amount_usd_label`. Confirmar con la Langfuse Cloud cost
   dashboard: filtro por `user_id = <tenant_id>` + el día indicado.
2. **Causa común 1 — turn loop**: un agente entró en loop entre
   `respond` y `tool_call`. Visible como muchos turns con costo
   pequeño. Revisar `messages` ordenados por `created_at` para el
   tenant; si hay >50 turns en una misma `conversation_id`, el
   classifier o el respond está stuck. Promote rollback al
   `agent_config` previo.
3. **Causa común 2 — prompt grew**: alguien editó el `system_prompt`
   con context muy largo. Cada turn cuesta más. Calcular tokens del
   prompt + history y validar. Si excede 30k tokens regularmente,
   reducir o partir.
4. **Causa común 3 — tráfico legítimo**: el cliente tuvo un buen día
   y el threshold default no representa su volumen real. Update:
   ```sql
   UPDATE tenants SET cost_alert_threshold_usd_per_day = 60
     WHERE id = '<uuid>';
   ```
5. **Documentar** en la cadencia quincenal de mejora si la causa fue
   regresión del agente.

---

## Health checks

- `GET /health` — siempre 200 con `{"status":"ok"}`.
- `GET /health/live` — liveness (Railway probe).
- `GET /health/ready` — Phase 1 placeholder; Phase 2 chequea DB +
  Redis + LiteLLM real.

Si `/health` devuelve algo distinto a 200 desde DNS público:
1. ¿La last release falló el `preDeployCommand`? Mirar Railway
   deployment log → `Build` y `Deploy` tabs. La línea final del
   release script printea `release: done` cuando todo va.
2. ¿Postgres caído? Railway dashboard → Postgres service → status.
3. ¿DNS roto? `dig api.auphere.com` debe devolver el CNAME a
   Railway. CloudFlare → DNS rules para confirmar.

---

## Webhook Meta — registro y verify

Cuando `api.auphere.com` esté arriba con `/health` 200 desde DNS
público:

1. Meta App dashboard (App 957213733862330) → WhatsApp → Configuration.
2. Callback URL: `https://api.auphere.com/webhook/meta` (o el subdominio
   `webhooks.auphere.com` si está configurado — debe coincidir con
   `NEXUS_META_WEBHOOK_CALLBACK_URL`).
3. Verify token: el valor de `NEXUS_META_WEBHOOK_VERIFY_TOKEN` (Doppler).
4. Click **Verify and save** — Meta hace el GET handshake; el endpoint
   responde el `hub.challenge` si el token coincide.
5. Subscribe a los fields: `messages`, `message_template_status_update`
   (+ `smb_message_echoes`, `smb_app_state_sync`, `history` si hay
   tenants Coexistence).
6. Confirmar en logs: `railway logs --service nexus-api | grep "webhook.meta"`.

Si el handshake devuelve 403: verify token distinto entre dashboard y
Doppler. Si los POST devuelven 401: `NEXUS_META_APP_SECRET` no coincide
con el App Secret real (firma X-Hub-Signature-256).

## Onboarding de un cliente nuevo (Block J)

> Phase 1 Lee onboardea cada tenant manualmente desde el panel. El wizard
> entrega el shape mínimo (identidad + costo); los pasos posteriores
> (WhatsApp, AgendaPro, prompt) se hacen en `/tenants/[id]/integrations`
> y `/tenants/[id]/agent`.

### Pre-requisitos por cliente

Antes de tocar el panel, asegurate de tener:

1. **Datos del owner**: nombre comercial, slug deseado, plan, mercado (CL/AR/...),
   timezone, email + WhatsApp E.164 del owner, horario de atención.
2. **Templates Meta**: las plantillas UTILITY del tenant se crean y
   gestionan desde el panel — `/tenants/[id]/connectors` → WhatsApp →
   **Plantillas**. Lead de revisión Meta minutos–72h — **arranca día 1**
   para no bloquear el go-live. Set recomendado: `reminder_24h`,
   `reminder_1h`, `no_show_followup`, `welcome_cl_es`,
   `alert_escalation_v1`, `alert_needs_reauth_v1`, `alert_cost_threshold_v1`,
   `alert_isolation_v1`, `alert_whatsapp_burst_v1` (las `alert_*` y las
   del backchannel `auphere_owner_consult` / `auphere_owner_action_request`
   van en la WABA de Auphere, no en la del tenant).
3. **WABA del cliente**: el owner necesita acceso a su Facebook Business
   y un número (nuevo o existente) para el Embedded Signup. El flujo
   registra el número bajo la App de Auphere (Tech Provider).
4. **Browserbase Startup tier** aprovisionado y `BROWSERBASE_API_KEY` +
   `BROWSERBASE_PROJECT_ID` en Doppler `production` (necesario para el
   bootstrap AgendaPro real; el panel devuelve 502 con mensaje claro si
   las keys no están).

### Paso 1 — Crear el tenant

`/tenants` → botón **Nuevo cliente** → completar el form:

- **Slug**: lowercase + guiones (ej. `cultor-barber`). El form valida
  disponibilidad async — si ves "Ya existe", elegí otro.
- **Plan**: pro para clientes Phase 1.
- **Timezone**: typically `America/Santiago` para CL.
- **Cost alert**: default $40/día (Pro tier). Override post-creación si
  el cliente tiene volumen alto.

Submit → redirige a `/tenants/[id]/integrations`.

### Paso 2 — Conectar WhatsApp

Card "WhatsApp (Meta)" → botón **Conectar con Meta** (Embedded Signup):

1. Elegir modo: **Cloud API** (número dedicado al bot) o **Coexistence**
   (el owner sigue usando la app de WhatsApp Business en su teléfono).
2. Se abre el popup de Facebook Login for Business — el owner (o el
   operador con acceso delegado) autoriza y selecciona/crea el número.
3. El backend intercambia el code por el BISUAT, registra el número,
   suscribe el webhook y crea la fila `Channel` (audit log incluido).
4. Smoke inmediato: botón **Enviar prueba** (template `hello_world`).

Errores típicos:

- **Popup bloqueado / no carga** → revisar `NEXT_PUBLIC_META_APP_ID` y
  los `NEXT_PUBLIC_META_CONFIG_ID_*` en Vercel (build-time).
- **"(#10) Permission denied"** → la App no tiene Advanced Access a
  `whatsapp_business_messaging/management` o no está en Live Mode.
- **Token inválido post-signup** → badge "Requiere re-auth" en el panel;
  re-correr el signup.
- **409 "ya está conectado a otro tenant"** → el E.164 está usado por
  otro tenant. Desconectar el canal del tenant anterior primero.

### Paso 3 — Bootstrap AgendaPro

Card "AgendaPro" → **Bootstrap** → dialog con login + password + business URL.

- El backend invoca el subprocess Stagehand v3 + Browserbase Contexts
  (Block E) y persiste el `context_id` encriptado en `tenant_credentials`.
- Si Browserbase no está aprovisionado, devuelve 502 con mensaje claro.
- Si falla por credenciales inválidas, el owner debe re-confirmar el
  login con vos.

### Paso 4 — Agent config v1 desde el seed

`/tenants/[id]/agent` → botón **Aplicar plantilla inicial**:

1. Seleccionar el seed del vertical (barbershop, beauty_salon, nail_studio,
   spa, medspa, dental, clinica, restaurante, aesthetic_clinic o generic).
2. Completar dirección, horario textual, nombre del agente, tono.
3. Submit → backend renderea el prompt + tools whitelist + policies y
   crea `agent_config v1 staged`.
4. Revisar el prompt rendered en el editor.
5. Si pinta bien, **Promote** la versión 1 desde la tabla de versiones.

El runtime invalida cache automáticamente; el siguiente turno usa la
nueva versión sin redeploy (pub/sub Redis).

### Paso 5 — Smoke conversación

Mandar un mensaje de prueba al WhatsApp del tenant desde un teléfono
propio. Esperado:

1. El webhook Meta llega a `https://api.auphere.com/webhook/meta`.
2. El worker procesa el inbound (Redis stream).
3. El agente responde con texto coherente al rol del seed.
4. Trace visible en Langfuse Cloud filtrando por `user_id=<tenant_id>`.
5. Conversación visible live en `/tenants/[id]/conversations` (SSE).

Si el smoke falla: chequear los counters en `/tenants/[id]/aislamiento`.
Si están todos en 0, el problema es de configuración (prompt, tools).
Si hay counters en > 0, ver el playbook de `alert_isolation_v1` arriba.

### Migrar un número entre tenants

Si Cultor migra desde otro proyecto del usuario que ya tiene su número
en una WABA distinta:

1. Confirmar con el owner que quiere migrar (no perder histórico).
2. **Quitar el número del tenant anterior**: actualmente requiere SQL
   manual (Phase 2 expone botón "Desconectar"):
   ```sql
   DELETE FROM channels
     WHERE type = 'whatsapp'
       AND provider_identifier = '+56911112222';
   ```
3. Re-correr Embedded Signup desde el panel del tenant nuevo.

### Decisión: número nuevo vs migración

Si el cliente quiere mantener su número existente: el Embedded Signup
en modo Coexistence o la migración de número de Meta lo soportan, pero
el número no puede estar activo en otra WABA — coordinar la liberación
primero.

Si acepta un número nuevo: más rápido y con menos riesgo de bloqueo.

---

## Connectors (Bloque L)

Connectors unifica integraciones en una sola tabla: WhatsApp (canal),
AgendaPro (browser_credentials), Calendar/Calendly/Notion (oauth_composio).
Decisión: ADR-011 + `architecture/connectors.md`.

### Conectar un OAuth connector (Calendar, Calendly, Notion)

1. **Pre-requisito (una sola vez por connector)**: en el dashboard
   Composio de la org `auphere`, crear el auth_config para el toolkit
   (`googlecalendar`, `calendly`, `notion`). El adapter Nexus resuelve
   automáticamente el `auth_config_id` via `composio.auth_configs.list()`
   por el toolkit slug — **no hay que pegar IDs en Doppler**. Composio
   dashboard es la única fuente de verdad.

   Doppler solo necesita estos dos Composio secrets:
   - `NEXUS_COMPOSIO_API_KEY`
   - `NEXUS_COMPOSIO_WEBHOOK_SECRET`

   Phase 1 = free tier (composio.dev, $0/mo, 20K calls/mo).

   Errores comunes del setup, qué dicen y qué hacer:
   - HTTP 503 "no auth_config registered in Composio for toolkit X" →
     crear el auth_config en el dashboard Composio antes de retry.
   - HTTP 409 "multiple auth_configs for toolkit X" → eliminar duplicados
     del dashboard Composio. Phase 1 espera exactamente uno por toolkit.

2. **Pre-requisito por tenant**: `owner_phone` debe estar
   configurado en `tenants` (el endpoint rechaza con 400 si no).

3. **Operación**:
   - Panel → tenant → tab "Connectors" → click "Conectar Google
     Calendar" en la card "Disponibles".
   - Backend pide a Composio un magic-link, manda WhatsApp template
     `connector_consent_request_v1` al owner del tenant.
   - El operador puede copiar el link manual del Dialog si el WhatsApp
     no llegó (fallback).
   - El cliente clickea el link, autoriza en Google.
   - Composio webhookea → connector status = `connected`.
   - Tools sync corre automáticamente. Read-only tools quedan
     `mode=always` (usables); destructive tools quedan `mode=blocked`
     hasta override (`google_calendar` tiene `auto_enable_destructive=false`).

4. **Promover tools destructivas**: panel → tab "Connectors" →
   ver tabla de overrides → cambiar mode `blocked` → `always` para
   tools que se quieren habilitar. El cambio es per-tenant.

### Desconectar un connector

Panel → tenant → Connectors → "Desconectar". Tokens upstream se
revocan (best-effort), `tenant_connectors.status = disconnected`,
tools del connector dejan de ser invocables en el próximo turn.

### Composio caído

- ≤ 15 min: degradación silenciosa, agente cae al mensaje canónico.
- 15 min – 48 h: alerta P2 al operador. Browser_credentials +
  webhook_manual no se afectan. Aceptable según ADR-011 (basado en
  incidente Apr 28-30 2026 de 36h).
- > 48 h: escalation P1, decisión humana sobre comunicar a clientes.

### Re-emitir consent link

Si el link expiró (TTL 7d) o el WhatsApp del owner falló: panel →
Connectors → "Reenviar consent" en la card del connector pendiente.
Rate-limited a 3/hora por (tenant, connector).

### Agregar un connector nuevo al catálogo

Ver [architecture/connectors.md → "Cómo agregar un connector nuevo"](../../../Work/Auphere/nexus/architecture/connectors.md).
Tiempo target: ~2h para un OAuth connector vía Composio (seed YAML +
auth_config registrado + 1-2 tests).

### Test coverage

Bloque L entrega 84 tests nuevos (59 unit + 20 integration + 5
isolation) más allá de la suite ~309 de J. La isolation suite
extendida cubre: no leak de connections cross-tenant, user_id binding
en Composio, overrides RLS, disconnect aislamiento. **El plan de
tests del bloque (`architecture/connectors-testing.md`) listaba ~128
como target aspiracional; se entregaron 84 reales focused — la
delta se cubre en un follow-up cuando entren clientes 2-3.**

Refactor 2026-05-12 (post-implementación): los 3 settings
`NEXUS_COMPOSIO_AUTH_CONFIG_*` fueron eliminados a favor de un lookup
runtime via `composio.auth_configs.list(toolkit=...)`. Composio
dashboard es ahora la única fuente de verdad para auth_configs. +5
tests cubren los caminos: lookup happy, missing (503), ambiguous (409),
case-insensitive matching.

## Cosas que no debés hacer (sin pensarlo dos veces)

- **`railway run alembic downgrade head` o `alembic downgrade base`**.
  Borra todas las tablas. Solo manual + revisión.
- **`DROP TABLE` o `TRUNCATE` directos en producción**. La regla:
  toda mutación de schema pasa por una migración.
- **Push de un commit con isolation suite roja a `main`**. CI
  bloquea, pero `--no-verify` la saltea. La regla del proyecto:
  isolation rojo bloquea merge, no lo evades.
- **Compartir `NEXUS_ADMIN_TOKEN` o `NEXUS_FERNET_KEY` en chat**.
  Doppler-only.
- **Activar `NEXUS_LANGFUSE_*` con keys de un workspace que no es el
  de producción**. Las trazas de prod no deben mezclarse con dev.

## Consola de partners (PLAN-CONSOLE-V1) — activar un partner

La consola (`apps/console`) habla con la API por `/console/*` con tokens
EdDSA de 60 s que acuña por petición; la API verifica la firma con la
clave pública y **vuelve a comprobar la pertenencia** en
`partner_memberships`. No hay token estático de por medio.

**La consola no tiene base de datos** (ADR-032, migración `0088`): las
cuentas, las contraseñas y las sesiones viven en la API, en el esquema
`console_auth` (`principals`, `principal_sessions`), y el BFF solo guarda
una cookie con un token opaco. No hay que crear ningún rol de Postgres
para ella ni ejecutar migraciones de Drizzle.

1. **Claves** (una vez por entorno): `cd apps/console && pnpm keys:generate`.
   La privada → secreto de la consola (`NEXUS_CONSOLE_JWT_PRIVATE_KEY`); la
   pública → secreto de la API (`NEXUS_CONSOLE_JWT_PUBLIC_KEY`) +
   `NEXUS_CONSOLE_ENABLED=true`. Con el interruptor encendido y sin clave la
   API se niega a arrancar en prod.
2. **Esquema `console_auth`**: lo crea `alembic upgrade head` (0088). Nada
   que hacer aparte de migrar la API.
3. **Encender al partner**: `UPDATE partners SET console_enabled = true WHERE
   slug = '<slug>'`. Comprobar `max_clients` (0081; sembrado real +50 %).
4. **Primer owner**: `scripts/seed_console_memberships.py` (siguiente
   sección). El resto entra por invitación desde `/team` (caduca a los 21
   días).
5. **Apagar**: `console_enabled=false` deja fuera a ese partner al instante
   (el backend lo comprueba en cada petición); `NEXUS_CONSOLE_ENABLED=false`
   apaga la superficie entera (503).

**Cuenta bloqueada** (10 fallos seguidos → 15 min): se desbloquea sola. Para
adelantarlo, `UPDATE console_auth.principals SET failed_attempts = 0,
locked_until = NULL WHERE lower(email) = '<correo>'`. No hay recuperación de
contraseña en v1: se resuelve con `--set-password` (abajo).

## Consola: alta de partner piloto (CP-33 — Facelad / Amacrux)

Camino recomendado para un partner real (la persona crea su cuenta ella
misma; nadie teclea contraseñas ajenas):

1. **Migrar la API** (`alembic upgrade head`): la 0088 crea el esquema
   `console_auth` con `principals` y `principal_sessions`. La consola no
   necesita rol de Postgres propio — el rol `nexus_console` y
   `infra/postgres/console_role.sql` se retiraron con ADR-032.
2. **Invitación de owner + encender la consola** (idempotente):
   ```bash
   cd apps/api
   NEXUS_DATABASE_URL=… uv run python scripts/seed_console_memberships.py \
     --partner-slug facelad --owner-email maria@facelad.com \
     --display-name "María" --enable-console \
     --console-origin https://console.auphere.com [--email] [--reissue]
   ```
   Imprime el enlace `/invite/<token>` (caduca a los 21 días). `--email`
   intenta enviarlo con Brevo/Resend (best-effort; el enlace se imprime
   siempre). No hace falta que exista un owner previo: la aceptación crea
   la primera membresía con el rol invitado (owner).
3. La persona abre el enlace, elige contraseña (mínimo 12 caracteres) y
   **entra directamente**: la API crea el principal, la membresía y la
   sesión en la misma llamada. El resto del equipo lo invita ella desde
   `/team`.
4. Verificar: `GET /console/onboarding` muestra el checklist; la campana
   recibe `member.joined` cuando acepte alguien más.

Alternativa sin enlace — **solo desarrollo o desbloqueo**, porque implica
teclear la contraseña de otra persona:

```bash
cd apps/api
NEXUS_DATABASE_URL=… uv run python scripts/seed_console_memberships.py \
  --partner-slug demo --owner-email owner@demo.test \
  --enable-console --set-password 'una-contraseña-de-12+'
```

Crea el principal y la membresía de una vez. Si el correo ya tiene cuenta,
**no** reescribe la contraseña; si la membresía existía apuntando a otro
`user_id` (por ejemplo el de better-auth anterior a ADR-032), la reapunta al
principal nuevo.
