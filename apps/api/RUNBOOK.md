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
