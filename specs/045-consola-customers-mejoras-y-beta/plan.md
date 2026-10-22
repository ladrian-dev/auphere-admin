# Plan de implementación: 045 — la consola customers, mejoras y Beta

**Rama**: `045-consola-customers-mejoras-y-beta` | **Fecha**: 2026-10-22 | **Spec**: [spec.md](spec.md)

## Resumen

Tres frentes sobre lo que ya existe (spec 030): (1) la regla de la Bandeja,
apoyada en dos columnas nuevas de `conversations` que escribe el despachador y
rellena una migración, y aplicada en `inbox_view`, la fan-out del push y el
Panel; (2) campos aditivos de API para el saldo, el horario y el silencio de
avisos (contrato congelado para la app); (3) las pantallas del diseño con los
componentes y tokens de `@nexus/ui`, y la insignia Beta.

## Contexto técnico

**Lenguaje/versión**: Python 3.12 (FastAPI, SQLAlchemy 2 async, Alembic) · TypeScript 5.9 / Next.js 16 / React 19.2

**Dependencias**: ninguna nueva.

**Almacenamiento**: PostgreSQL 16 (RLS FORCE). Migración `0171_inbox_attended`.

**Pruebas**: pytest (unit, integration, isolation) · vitest + Testing Library · Playwright + axe (e2e lite).

**Plataforma**: API (ECS), worker, consola web.

**Restricciones**: la lista de la Bandeja sigue con su keyset y su índice
(parcial nuevo); el relleno corre en una transacción por lotes de conversaciones.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | Columnas nuevas bajo la RLS de `conversations`; `tests/isolation/test_lite_inbox_attended_only.py` barre lista, contadores, detalle, hilo y push con un número silenciado |
| II | Superficie | ☑ | `0`, la abierta; ningún flujo nuevo de fuera |
| III | Lo leído es dato | ☑ | El motivo del escalado se enseña como texto, no se interpreta |
| IV | Acción `mutates` | ☑ | No hay acciones nuevas; las de la Bandeja siguen con su auditoría |
| V | Estados honestos | ☑ | Cinco estados por bloque; sin pestañas de un canal; sin botón de compra |
| VI | Por API | ☑ | Todo por `/console/lite/*` |
| VII | Test primero | ☑ | Cada criterio de la spec tiene su prueba en `tasks.md`, en rojo antes |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | KB | ☑ | `[[research/2026-10-22-reservas-y-consola-customers/_index]]` |

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | Garantía 1 (RLS): la Bandeja y el push solo con lo atendido | T004, T005 |
| **Licencias** | Ninguna | — |
| **Medidor** | Nada | — |

## Diseño

### Bandeja

- `dispatcher.py` (worker): después de decidir `skipped_reason`, si es `None` y
  el número tiene agente (no es solo de envío), `attended_at = COALESCE(attended_at, now)`
  y `last_attended_inbound_at = now`. `enqueue_message_for_you` pasa **después**
  de la puerta y no se llama para un mensaje silenciado.
- `services/inbox_view.py`: un predicado `_visible()` (`attended_at IS NOT NULL`)
  en la base de `list_conversations`, `counts`, `get_conversation`; el hilo y la
  vista previa filtran `created_at >= attended_at` y `skipped_reason IS NULL`;
  `unread_expr` usa `last_attended_inbound_at`.
- `items[].waiting` y `waiting_since`: subconsulta del último
  `conversation_events.kind = 'escalated'`.
- `services/push_fanout.py`: `compose` comprueba visibilidad; badge con `counts`.
- `services/lite_home.py`: `waiting` sale de `inbox_view.counts` (el mismo
  número que la Bandeja).

### API aditiva

- `LiteBalanceOut` + `month_days_left`, `runs_out_on` (función pura
  `balance_horizon(days_left, today_local)`), en `home.py` y `usage.py`.
- `/me.business` (zona, horario canónico, etiqueta por idioma —función pura en
  `services/business_hours.py`, espejo de `hoursLabel` de la consola—).
- `client_phones.quiet_outside_hours` + `NoticesIn/Out`; `push_fanout._targets`
  marca `skipped/quiet_hours` fuera de horario para los no urgentes.

### Consola

- `app-sidebar.tsx`: rama de cliente con la insignia Beta (`shell.beta.client.hint`).
- Panel (`lite-panel-view.tsx`): cabecera «Hola, {nombre}» con eyebrow del
  negocio y línea; KPI de conversaciones en `HighlightMetric` (tarjeta oscura y
  curva), «esperan», saldo con «Cubre N de M días» y barra con tono por días;
  gráfica con media; atención con texto nuevo.
- Bandeja: intro con WhatsApp; fila con motivo y espera; píldora «N agentes
  activos» (con más de uno) que abre el filtro de agente.
- Consumo: saldo primero con «Te alcanza hasta…»; detalle técnico agrupado en
  mensajes, uso del modelo y multimedia.
- Estados: esqueletos `loading.tsx` en `/` y `/usage` con las medidas finales.

## Estructura

```text
apps/api/alembic/versions/0171_inbox_attended.py
apps/api/src/nexus_api/db/models/conversation.py, client_phone.py
apps/api/src/nexus_api/services/{inbox_view,push_fanout,lite_home,business_hours}.py
apps/api/src/nexus_api/api/console/lite/{inbox,home,usage,me,phones}.py
apps/worker/src/nexus_worker/runtime/dispatcher.py
apps/console/src/components/{shell,lite,inbox}/…, app/(console)/{loading,usage/loading}.tsx
apps/console/src/i18n/lanes/{lite,inbox}.ts, i18n/messages.ts
docs/consola-lite.md
```

## Complexity Tracking

| Añadido | Por qué |
|---|---|
| Dos columnas en `conversations` en vez de calcular desde `messages` | `messages` está particionada por mes y es la tabla grande: el «sin leer» de cada fila y los contadores tendrían que recorrerla en cada lectura |
