# QA Playground — Runbook

> Referencia arquitectónica: [ADR-020](../../../Work/Auphere/nexus/decisions/ADR-020-qa-playground-ucm-multichannel.md).
> Spec funcional: [qa-playground-mvp](../../../Work/Auphere/nexus/features/qa-playground-mvp.md).
> Contrato de alertas: [`alerts.md`](./alerts.md).

## 1. Qué es

El **QA Playground** es la superficie interna de Auphere para chatear
con el agente de un cliente como si fueras el cliente final, en sandbox
seguro (`dry_run=true` siempre), antes del go-live. Bajo el capó cada
mensaje viaja como **UCM** (Universal Channel Message): un schema
canal-agnóstico que se renderiza distinto en Web y WhatsApp. Es la
primera implementación del modelo "un cerebro, N canales".

Sólo accesible para operators con role `qa_operator` desde el detalle
del tenant (`/tenants/[id]`).

## 2. Cómo lo accede el operator

1. Iniciar sesión en el Operator Panel (Better Auth, role `qa_operator`).
2. Abrir el detalle del tenant: `/tenants/[id]`.
3. Bajar a la card **"Probar agente"** → botón **"Abrir Playground"**.
   (Alternativa: link directo desde la lista de threads QA recientes
   de la misma card.)
4. Se abre `/qa/[tenantId]/chat`:
   - Sidebar izquierdo: threads QA previos del operator para este tenant.
   - Central: dropdown **"Preview as"** (web / whatsapp), thread, composer.
   - Sidebar derecho: drawer Inspector con 5 tabs.
5. Escribir un mensaje. El agente responde con streaming.
6. Cambiar el dropdown a **whatsapp** para ver cómo se vería en el
   canal real (re-renderiza, NO re-ejecuta).
7. Cerrar la pestaña: el thread queda en la lista lateral para retomar.

> Badge **DRY RUN** siempre visible en el header. Si no lo ves, parar
> y reportar inmediatamente — significa que el ambiente está mal
> configurado.

## 3. Qué garantías tiene

Siete guardas, cada una con un test que la enforcea. Si alguno se
pone rojo, el feature no merge y/o se rollbackea (ver §7).

| # | Guarda | Test |
|---|---|---|
| 1 | RLS por `operator_id` — un operator solo ve sus threads | [`tests/isolation/test_8_qa_thread_isolation_by_operator.py`](../../apps/api/tests/isolation/test_8_qa_thread_isolation_by_operator.py) |
| 2 | RLS bajo concurrencia 100×5×5 (HTTP path) | [`tests/isolation/test_9_qa_concurrent_isolation.py`](../../apps/api/tests/isolation/test_9_qa_concurrent_isolation.py) |
| 3 | `dry_run=True` intercepta toda tool con `side_effects` | [`tests/unit/test_mcp_dry_run.py`](../../apps/api/tests/unit/test_mcp_dry_run.py) + [`tests/integration/test_mcp_dry_run_per_server.py`](../../apps/api/tests/integration/test_mcp_dry_run_per_server.py) |
| 4 | Auditoría persiste cada side-effect bloqueado | [`tests/integration/test_qa_audit_writer.py`](../../apps/api/tests/integration/test_qa_audit_writer.py) |
| 5 | Endpoints `/qa/*` requieren Bearer admin + `X-Operator-Id` | [`tests/integration/test_qa_endpoints.py`](../../apps/api/tests/integration/test_qa_endpoints.py) |
| 6 | INSERT cross-operator rechazado por `WITH CHECK` | [`tests/isolation/test_8_qa_thread_isolation_by_operator.py::test_qa_cross_operator_insert_rejected`](../../apps/api/tests/isolation/test_8_qa_thread_isolation_by_operator.py) |
| 7 | UCM emitido por el agente piloto valida contra WhatsApp | (Fase 6 Bloque C — `tests/integration/test_ucm_contract.py`) |

Los tests 1-6 están todos verdes al cierre de Fase 6. El 7 depende
del agente piloto cuando exista; mientras el grafo emita UCM tipo
`text` simple los asserts pasan trivialmente.

## 4. Arquitectura del runtime del Playground

**Decisión 2026-05-20**: el QA Playground invoca el agent graph
**in-process** desde el `nexus-api`, NO a través de un LangGraph Server
separado. El servidor opcional sigue en el repo bajo
`apps/qa-langgraph-server/` como **utility de desarrollo** (LangGraph
Studio inspection), pero **no se deploya** en producción.

### Por qué in-process

El grafo es el mismo código (`build_qa_pipeline` en
`apps/worker/.../runtime/qa_pipeline.py`) sea quien lo invoque. Pinearlo
dentro del API gana:

- Cero servicio adicional a deployar.
- Cero licensing issue (custom auth del LangGraph Server requiere
  LangSmith Enterprise — feature paga).
- Cero retry-on-404 / persistence sync entre 2 procesos.
- Tests directos contra el grafo, no parsing de SSE manual.
- Un solo Bearer secret a rotar.

### Cuándo SÍ vamos a necesitar un servidor de streaming separado

Cuando aterrice **un canal web público para clientes finales** (widget
embebido en sitios de clientes, no este Playground interno). Ese canal
sí necesitará streaming visible token-por-token. Se diseñará como un
**channel adapter** más (igual que YCloud WhatsApp hoy), con su propio
endpoint público y su decisión arquitectónica entre SSE custom vs
LangGraph Server enterprise vs WebSocket. NO se va a retrofittear el
Playground interno.

### Cómo correrlo local

El qa-api ya importa el grafo del worker como dep core (path
`../worker`). Local con Docker basta:

```bash
docker compose up -d            # postgres + redis + nexus-api
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up -d api        # picks up the env var from the shell
```

El composer del Playground (`/qa/[tenantId]/chat`) llama al endpoint
`POST /qa/threads/{id}/send` del nexus-api. Ese endpoint:

1. Auto-seedea customer + conversation + inbound message (primer turn,
   idempotente).
2. Setea contextvars (operator_id, tenant_id, qa_thread_id) y los
   pone disponibles al runtime.
3. Invoca `qa_pipeline.ainvoke(state, config={"configurable":
   {"thread_id": qa_thread_id}})` IN-PROCESS.
4. El grafo corre los nodos classify → handler → respond →
   ucm_formatter → checkpoint, con `dry_run=True` forzado.
5. Devuelve el UCM final + intent + tool_calls al frontend.

### Producción (Railway)

UN solo servicio (`nexus-api`) con persistencia Postgres ya existente.

1. **Service Railway**: `nexus-api` (build desde `apps/api/Dockerfile`,
   build context = repo root). Ya existe.
2. **Variables nuevas para el grafo in-process**:
   - `ANTHROPIC_API_KEY` (secret).
   - `OPENAI_API_KEY` (secret, fallback opcional).
   - `LITELLM_LOCAL_MODEL_COST_MAP=True`.
3. **Persistencia del checkpointer**: el grafo usa `MemorySaver`
   in-process. Un restart de container pierde los checkpoints
   in-memory PERO la conversación se reconstruye desde `messages` en
   Postgres en el siguiente turn — no hay impacto visible.
4. **Vercel admin**: el BFF `apps/admin/src/app/api/qa/*` apunta al
   nexus-api (env var `NEXUS_BACKEND_URL`, ya existente). NO necesita
   ninguna URL nueva.
5. **Bearer secret rotation**: `NEXUS_ADMIN_TOKEN` vive en 2 servicios
   (nexus-api + admin Vercel). Rotación = redeploy ambos sincronizados.

> El qa-api Dockerfile fue actualizado para incluir las path-deps del
> monorepo en el image final (worker, mcp, ucm-schema, channels). La
> sesión de deploy a Railway sigue pendiente pero el image build local
> ya valida que `nexus-api:latest` puede ejecutar el grafo end-to-end.

### Servidor opcional para developers

`apps/qa-langgraph-server/` queda en el repo para developers que
quieran inspeccionar el grafo con [LangGraph Studio](https://smith.langchain.com/studio/):

```bash
cd apps/qa-langgraph-server
.venv/bin/langgraph dev --port 2024 --no-browser
# Abrir Studio: https://smith.langchain.com/studio/?baseUrl=http://localhost:2024
```

NO está en el path del Playground — el frontend habla con el nexus-api,
NO con este servidor. Si lo prendés, no afecta nada.

## 5. Troubleshooting

### Escenario 1 — "No puedo abrir el chat — 403"

- **Síntoma:** el operator hace clic en "Abrir Playground" y ve 403
  en la página o en la network tab.
- **Diagnóstico:**
  - ¿La sesión Better Auth está activa? Revisar cookie `auth_session`.
  - ¿El user tiene role `qa_operator`? `SELECT role FROM user_roles
    WHERE user_id = '<...>';`
  - ¿El header `X-Operator-Id` llega al backend? Network tab del
    proxy `/api/qa/threads` → el BFF lo pone en server-side; si
    falta, hay bug en el BFF route handler.
  - Logs: `structlog` etiqueta `qa_security.unauthorized`.
- **Fix:** asignar role en BD, re-login. Si el BFF no pone el header,
  arreglar la route handler (`apps/admin/src/app/api/qa/threads/route.ts`).

### Escenario 2 — "El chat carga pero no aparecen threads"

- **Síntoma:** sidebar izquierdo dice "No hay conversaciones todavía".
- **Diagnóstico:**
  - ¿El operator tiene threads previos en ESTE tenant? Otros tenants
    no aparecen — es by-design.
  - SQL (con `app.operator_id` seteado vía `qa_scoped_session`):
    ```sql
    SELECT id, tenant_id, title FROM qa.threads WHERE operator_id = '<op>';
    ```
  - Si la query directa muestra rows pero el endpoint devuelve `[]`:
    el `SET LOCAL ROLE nexus_app` no se aplicó → bug en `qa_session`
    dependency. Revisar logs del request.
- **Fix:** si es estado normal (primer uso), crear thread con "+ nueva".
  Si hay bug de RLS, ABRIR INCIDENT — es una guarda 1.

### Escenario 3 — "Aprieto enviar y no pasa nada"

- **Síntoma:** composer no envía. Streaming nunca arranca.
- **Diagnóstico:**
  - ¿El LangGraph Server está corriendo? `curl <host>:2024/health`.
  - ¿El composer está `disabled`? En el cierre de Fase 5 el composer
    quedó `disabled` hasta que el runtime live esté wireado. Si el
    runtime aún no se conectó, este es el comportamiento esperado.
  - Network tab del browser → ¿hay request al endpoint del runtime?
    Si no, falta el wiring (Fase 5 cierre).
- **Fix:** si runtime no está conectado, esperarlo (ver pendientes
  Fase 5). Si está conectado y el composer no dispara, mirar consola
  del browser: probablemente error de auth o stream callback.

### Escenario 4 — "El audit tab está vacío aunque el agente llamó tools"

- **Síntoma:** el agente parece haber llamado una tool (ves la frase
  "checked your calendar" en la respuesta) pero la tab Audit del
  Inspector está vacía.
- **Diagnóstico:**
  - Counter `qa.side_effect.blocked` ¿se movió? Si no, la tool en
    cuestión tiene `side_effects = ()` (es read-only) y NO se
    audita — por diseño.
  - Si sí se movió pero la tabla está vacía: counter
    `qa.audit.write_failed > 0` → la persistencia falló. Revisar
    logs estructurados `qa_audit.write_failed`.
  - Si counter no se movió y el side_effect estaba declarado: bug en
    `qa_audit.py` (ver Bloque E.2). NO debería ocurrir; abrir incident.
- **Fix:**
  - Si el tool es read-only, explicarle al operator que es expected.
  - Si la persistencia rota: ver Escenario 5; el counter ya hizo page.

### Escenario 5 — "Veo un thread de otro operator (REPORT BUG)"

- **Síntoma:** un operator ve en su sidebar un thread cuyo título no
  reconoce; al abrirlo, identifica que es de otra persona.
- **Severidad:** **CRÍTICO**. Es una violación de la garantía 1
  (RLS por operator). El feature debe RE-cerrarse hasta resolución.
- **Diagnóstico inmediato:**
  - Capturar `operator_id` actual + `thread.id` visible.
  - SQL superuser:
    ```sql
    SELECT operator_id, tenant_id, title FROM qa.threads WHERE id = '<thread>';
    ```
  - Comparar `operator_id` real vs el que reporta. Si difieren:
    RLS bypass real.
  - Verificar que `app.operator_id` se setea ANTES del `SET LOCAL
    ROLE nexus_app` (la dependency `qa_session` lo hace; revisar
    logs si el orden se respetó).
  - Suite [`tests/isolation/test_9_qa_concurrent_isolation.py`](../../apps/api/tests/isolation/test_9_qa_concurrent_isolation.py)
    correrla local con el operator_id del incidente como
    fixture forzado.
- **Fix temporal:** revoke del Bearer `NEXUS_ADMIN_TOKEN` (rotación
  inmediata) → todos los `/qa/*` 401 → feature off de facto.
- **Fix definitivo:** identificar el bug, escribir test isolation
  que lo reproduzca, re-deploy.

### Escenario 6 — "El UCM rinde raro en WhatsApp preview"

- **Síntoma:** el mensaje se ve bien en Web pero en WhatsApp preview
  aparece truncado, sin botones, o con texto raro.
- **Diagnóstico:**
  - Inspector → tab Tools → ver el UCM que emitió el agente.
  - ¿El `fallback_text` está definido? Es obligatorio en v1.0.0.
  - ¿El type tiene `capabilities_required` que WhatsApp no soporta?
    `degrade(ucm, "whatsapp")` debería resolverlo a texto plano —
    revisar `degrade.steps[]` en el state del run.
  - ¿El `ucm.shadow_diff` está en log nivel WARN? Significa que el
    formatter UCM disagree con el output WhatsApp legacy.
- **Fix:** si es el agente: ajustar el system_prompt para que emita
  el type correcto. Si es el renderer: bug en
  `packages/ucm-render-web` o `packages/ucm-preview-whatsapp`.

## 6. On-call playbook

Una sola alerta es pageable (ver [`alerts.md`](./alerts.md)).

| Alerta | Acción inmediata |
|---|---|
| `qa_audit_write_failed_rate` | Page al on-call de plataforma → revisar logs `qa_audit.write_failed` → confirmar Postgres + RLS sanos → si persiste 15min, considerar rotación de Bearer para apagar el Playground hasta arreglar. |
| `qa_side_effect_blocked_anomaly` | Daily digest. NO escalar salvo confirmar que es atacante / loop / script. Si el operator legítimo está jugando con un agente nuevo, es esperado. |
| `ucm_shadow_diff_nonzero_rate > 1%` | Silent log. Revisión semanal por plataforma. Si > 5% sostenido → escalar el formatter UCM del agente piloto. |
| `qa_run_duration_p95 > 30s` | Daily digest. Probable LLM provider degradado; ver Langfuse tag `qa=true` para confirmar. |
| `qa_thread_created_spike` | Silent log. Solo investigar si es el MISMO operator > 100 threads / 5min — probable bug en frontend. |

Escala a engineering lead si:
- Cualquier guarda de isolation rompe en CI.
- Se detecta un thread cross-operator (Escenario 5).
- `qa.audit.write_failed` > 0 durante > 30min después del page.

## 7. Rollback total

Si hay que apagar el feature sin redeploy:

### 7.1 Apagar el LangGraph Server

- Bajar el container del `qa-langgraph-server`. El admin sigue
  cargando el detalle del tenant; al hacer clic en "Abrir Playground"
  el composer falla en silencio (gracefully — Fase 5 dejó el
  composer disabled hasta que el runtime conecte) o muestra error
  al primer turn. La card sigue ahí.
- **Mejor**: feature flag `NEXUS_QA_PLAYGROUND_ENABLED=false` en el
  admin (no implementada al cierre de Fase 6 — agendarla si hace
  falta apagar UX). Mientras tanto, ocultar la card requiere
  redeploy del admin.

### 7.2 Apagar el backend QA

```sql
-- Revoke todas las rows de qa.threads (soft, sin DROP):
UPDATE qa.threads SET archived_at = now() WHERE archived_at IS NULL;
```

Esto no destruye datos; sólo oculta threads de la lista. Permite
restaurar.

### 7.3 Rotación de Bearer (kill switch real)

- Cambiar `NEXUS_ADMIN_TOKEN` en Railway → todos los endpoints
  `/qa/*` empiezan a devolver 401.
- Comunicar al equipo: "QA Playground apagado por incidente, ETA
  para volver: <X>". Canal: #ops-page.
- Cuando se resuelva, restaurar el Bearer (o emitir uno nuevo y
  actualizar admin + langgraph-server).

### 7.4 Comunicación a operators

- Mensaje en #qa-ops-internal:
  > QA Playground está temporalmente apagado por
  > <razón breve / link al incidente>. Volveremos a notificar
  > cuando esté arriba. Si tu tarea bloquea por esto, ping a
  > @plataforma.

- NO comunicar a clientes externos. El Playground es interno —
  ningún cliente lo sabe.

---

## Apéndice: scripts útiles

```bash
# Verde rápido de la suite QA
cd apps/api
uv run pytest tests/unit/test_mcp_dry_run.py \
              tests/isolation/test_8_qa_thread_isolation_by_operator.py \
              tests/isolation/test_9_qa_concurrent_isolation.py \
              tests/integration/test_qa_endpoints.py \
              tests/integration/test_qa_audit_writer.py \
              tests/integration/test_qa_metrics.py \
              tests/integration/test_mcp_dry_run_per_server.py -q

# Counters en vivo (in-process)
uv run python -c "
from nexus_api.core.metrics import counters
print({k:v for k,v in counters.snapshot().items() if k.startswith('qa.')})
"

# Snapshot del audit por operator (superuser, ignora RLS)
psql -h localhost -p 5433 -U nexus -d nexus -c \
  "SELECT tool_name, count(*) FROM qa.side_effect_audit
   WHERE created_at > now() - interval '1 day'
   GROUP BY tool_name ORDER BY 2 DESC;"
```
