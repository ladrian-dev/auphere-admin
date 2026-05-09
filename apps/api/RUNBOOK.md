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
| BSP WhatsApp | YCloud Growth | — | Webhook → `https://api.auphere.com/webhook/ycloud`. |
| Browser automation | Browserbase Startup | — | Aprovisionado en Bloque J cuando se onboardee Cultor Barber. |

DNS: `api.auphere.com` → Railway, `admin.auphere.com` → Vercel. Certs
auto via Let's Encrypt (Railway) y Vercel.

---

## Deploy manual (CI down o cutover urgente)

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

## Playbook — alerta `alert_ycloud_burst_v1`

Trigger: ≥5 errores 5xx contra YCloud en una ventana de 2min (Bloque
H). El alerter respeta cooldown de 5min para no spamear.

1. **YCloud status** — `https://status.ycloud.com`. Si hay incidente
   declarado, no hay nada que hacer del lado nuestro: el outbound
   dispatcher ya retri-i con backoff (`MAX_ATTEMPTS=3`). Comunicar al
   cliente afectado.
2. **Meta Cloud API status** — YCloud sirve sobre Meta. Si Meta está
   degradado, YCloud transitivamente lo está. `https://metastatus.com`.
3. **Auth failure** — si los 5xx son 401/403 en realidad (algunos BSP
   los miscatigorizan), validar que `NEXUS_YCLOUD_API_KEY` no fue
   rolled. Doppler → production → `NEXUS_YCLOUD_API_KEY`.
4. **Rate limit** — YCloud Growth tier es 80 msg/s. Si un tenant
   excede, el outbound dispatcher se va a backoff hasta que el rate
   recupere. No requiere acción inmediata.
5. **Si todo está OK upstream**: capturar el wamid + body del error en
   Langfuse, abrir bug en KB. El YCloudBurstTracker es process-wide
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

## Webhook YCloud — cutover y verify

Cuando `api.auphere.com` esté arriba con `/health` 200 desde DNS
público:

1. YCloud dashboard → Auphere account → Webhooks.
2. URL: `https://api.auphere.com/webhook/ycloud`.
3. Eventos suscritos: `whatsapp.inbound_message.received`,
   `whatsapp.message.updated`.
4. Secret: copiar el valor de Doppler
   `NEXUS_YCLOUD_WEBHOOK_SECRET` (lo generás tú, no lo da YCloud).
5. Save. YCloud envía un evento de prueba — debería responder 2xx
   (parser ack los `message.updated` con `ignored`).
6. Verificar en Railway logs que el webhook llega:
   `railway logs --service nexus-api | grep "ycloud"`.

Si el cutover devuelve 401 desde YCloud: timestamp drift > 300s o
secret mal pegado. Revalidar `NEXUS_YCLOUD_WEBHOOK_SECRET` en Doppler.

---

## Onboarding de un cliente nuevo (Block J)

> Phase 1 Lee onboardea cada tenant manualmente desde el panel. El wizard
> entrega el shape mínimo (identidad + costo); los pasos posteriores
> (WhatsApp, AgendaPro, prompt) se hacen en `/tenants/[id]/integrations`
> y `/tenants/[id]/agent`.

### Pre-requisitos por cliente

Antes de tocar el panel, asegurate de tener:

1. **Datos del owner**: nombre comercial, slug deseado, plan, mercado (CL/AR/...),
   timezone, email + WhatsApp E.164 del owner, horario de atención.
2. **Templates Meta**: los 9 templates UTILITY de
   `apps/channels/src/nexus_channels/whatsapp_ycloud/templates/cultor_barber/`
   creados en YCloud dashboard como UTILITY. Lead Meta 24-72h — **arranca
   día 1** para no bloquear el go-live. Los nombres exactos son:
   `reminder_24h`, `reminder_1h`, `no_show_followup`, `welcome_cl_es`,
   `alert_escalation_v1`, `alert_needs_reauth_v1`, `alert_cost_threshold_v1`,
   `alert_isolation_v1`, `alert_ycloud_burst_v1`.
3. **WABA del cliente**: si migrás un número existente, el owner debe ser
   admin del Facebook Business antes (precondición ADR-008). Si arrancás
   con número nuevo de prueba, YCloud Growth provee uno gratis.
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

Card "WhatsApp YCloud" → botón **Conectar manualmente** → dialog:

1. Pegar `waba_id` y `phone_number_id` (los obtenés del YCloud dashboard
   → WABA → Phone numbers).
2. Click **Verificar** → el panel llama a YCloud y muestra preview con
   E.164, display name, verified name, quality rating.
3. Confirmar visualmente que es la cuenta correcta.
4. Click **Confirmar y conectar** → crea fila `Channel`, audit log.

Errores YCloud típicos y qué significan:

- **400 "no encontró el par"** → typo en los IDs. Re-copiar del dashboard.
- **400 "401 / NEXUS_YCLOUD_API_KEY"** → la API key BSP fue rolled.
  Doppler → `production` → `NEXUS_YCLOUD_API_KEY`.
- **400 "403 / Tech Provider"** → el owner no agregó a Auphere como Tech
  Provider en su Facebook Business, o YCloud no ha bindeado la WABA.
- **409 "ya está conectado a otro tenant"** → el E.164 está usado por
  otro tenant. Ver "Migrar un número entre tenants" abajo.

### Paso 3 — Bootstrap AgendaPro

Card "AgendaPro" → **Bootstrap** → dialog con login + password + business URL.

- El backend invoca el subprocess Stagehand v3 + Browserbase Contexts
  (Block E) y persiste el `context_id` encriptado en `tenant_credentials`.
- Si Browserbase no está aprovisionado, devuelve 502 con mensaje claro.
- Si falla por credenciales inválidas, el owner debe re-confirmar el
  login con vos.

### Paso 4 — Agent config v1 desde el seed

`/tenants/[id]/agent` → botón **Aplicar plantilla inicial**:

1. Seleccionar `barbershop_v1` (única vertical Phase 1).
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

1. El webhook YCloud llega a `https://api.auphere.com/webhook/ycloud`.
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
3. Conectar manualmente desde el panel del tenant nuevo.
4. Coordinar con YCloud support la migración del número entre WABAs si
   también cambia de WABA (no es un flow del panel).

### Decisión: número nuevo vs migración

Si el cliente quiere mantener su número existente: coordinar migración con
YCloud support. Lead típico 3-5 días hábiles.

Si acepta un número nuevo de prueba: YCloud Growth provee uno gratis.
Phase 1 más rápido y con menos riesgo de bloqueo. Es el path
recomendado para cliente 1 (Cultor) si la migración demora.

---

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
