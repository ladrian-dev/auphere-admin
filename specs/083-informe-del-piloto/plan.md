# Plan de implementación: el informe del piloto

**Carpeta**: `specs/083-informe-del-piloto` | **Fecha**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Entrada**: la spec, con las definiciones que Luis aceptó el 2026-11-26 y las decisiones D1–D14 tomadas sin él.

## Resumen

Una lectura nueva, `GET /console/clients/{ref}/report?from=&to=`, y una pestaña «Informe» del cliente que la pinta y se imprime. Las conversaciones se cuentan por **ciclos** y el «con persona» sale del **historial**, con un solo constructor de ciclos en `services/improvement/performance.py` que usan el informe y la página Rendimiento del agente. Los días van en la zona del cliente. El gasto es el de Consumo (`usage_lines.spend`), en una sesión propia.

## Contexto técnico

**Lenguaje/versión**: Python 3.11 (FastAPI, SQLAlchemy async) en `apps/api`; TypeScript estricto (Next 16, React 19) en `apps/console`.

**Dependencias principales**: las que ya hay. **Ninguna nueva** (ni en Python ni en `package.json`, que es de la 082).

**Almacenamiento**: lee `conversations`, `conversation_events`, `messages`, `audit_log`, `reservation_events`, `reservation_outbox`, `reservation_settings`, `client_access` y, para el gasto, el libro y las bolsas por `usage_lines.spend`. **Ninguna migración** (la última sigue siendo la `0243`).

**Pruebas**: pytest (unitarias del constructor de ciclos; de integración de la ruta y de Rendimiento; de aislamiento) y Vitest (la vista y sus estados).

**Plataforma**: la API en ECS; la consola en Vercel.

**Rendimiento**: seis consultas por informe, indexadas por `conversation_id`, más el gasto. Objetivo CE-006: menos de 2 s con 2 000 conversaciones.

**Restricciones**: propiedad de ficheros de la nota de KB. No se tocan `runtime/*`, `apps/mcp`, la Bandeja, Reservas, `agent-builder.tsx`, `package.json`, FAQ ni revisión.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto | ☑ | La ruta usa `client_scope`: resuelve `{ref}` bajo el partner del principal (404 opaco) y abre la transacción con la RLS del cliente. Ninguna consulta filtra por un `tenant_id` que venga de fuera. El gasto llama a `usage_lines.spend` con `[scope.tenant.id]` y el partner del principal. Pruebas: la de alcance de la consola la barre sola (C8, 404 opaco, sin ids) y una propia en `tests/isolation/test_client_report_scope.py` cruza partners y clientes del mismo partner (garantía 1). |
| II | Corte por superficie | ☑ | Superficie `0`, ya abierta. Declarada en la spec. |
| III | Lo leído es dato | ☑ | No llega nada a un agente. |
| IV | Acción consecuente con aprobación | ☑ | Solo lee. No escribe auditoría: las lecturas de la consola no se auditan, así que no hace falta frase en `console_audit_vocabulary`. |
| V | Estados honestos; la ausencia se diseña | ☑ | Cinco estados. Parcial: el gasto que no se pudo leer. Sin Reservas, no hay bloques de agenda (ni vacíos ni explicados). El cliente sin cierre por inactividad lo dice. Los límites del freno se dicen. |
| VI | Por API | ☑ | No aplica. |
| VII | Test primero | ☑ | Cada criterio nace como prueba en rojo (`tasks.md`): primero el constructor de ciclos, luego la ruta, luego la vista. |
| VIII | Licencias | ☑ | Ninguna dependencia nueva. |
| IX | KB dueña del porqué | ☑ | La spec cita la nota `research/2026-11-26-beta-jemma-p0-p1.md`; una tarea enlaza la carpeta de la spec desde la nota. |

### Las tres puertas de `/speckit-tasks`

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | Garantía 1 y el alcance de la consola (CP-04, C8). | T004 (`tests/isolation/test_client_report_scope.py`) y la barrida de `test_console_scope.py`, que se corre sin tocarla (T015). |
| **Licencias** | Ninguna dependencia nueva. | — |
| **Medidor** | Nada: no gasta. | — |

## Diseño

### Backend

**`services/improvement/performance.py`** (de esta spec):

- `client_zone(session) -> ZoneInfo`: la zona del cliente del contexto (`tenants.timezone`, UTC si no vale).
- `build_spans(created_at, events) -> list[Span]`: **pura**. Los ciclos de una fila con las reglas de R1 (D3).
- Filtros de mensaje (R2): `contact_wrote()`, `agent_sent()`, `person_wrote()`.
- `period_cycles(session, *, since, until, zone, owner=None) -> list[Cycle]`: los ciclos del periodo (su primer mensaje del contacto cae en `[since, until)`), cada uno con su día local, si fue con persona y su primera respuesta. Seis consultas:
  1. las conversaciones con mensaje del contacto en el periodo (canal de clientes; con `owner`, las del agente, como hoy);
  2. su `created_at` y sus `resolved`/`reopened`;
  3. las horas de los mensajes del contacto del periodo;
  4. el último mensaje del contacto **antes** del periodo, por conversación (para saber si el ciclo ya había empezado antes);
  5. los envíos del agente desde el primer mensaje del periodo (hora + `latency_ms`);
  6. las señales de persona (eventos `escalated`/`takeover`, auditorías `inbox.takeover`/`conversation.takeover`/`agent.booking_brake` y mensajes de persona) desde el principio del ciclo más antiguo.
- `handed_to_person()`: pasa a ser una expresión `EXISTS` sobre el historial de la fila (R3). La siguen usando la lista y `suggestions.py`.
- `agent_performance`: ciclos del agente por día local; el gasto por día local (`timezone(<zona>, occurred_at)::date`).
- `agent_conversations`: el resultado por `handed_to_person()` y el motivo del último escalado (`cause` de R4 en el vocabulario de hoy: `escalated`, el código de la puerta o `taken_by_person`).

**`services/client_report.py`** (nuevo): `build_report(session, *, tenant, partner_id, day_from, day_to, now)` compone:

- conversaciones y primera respuesta, de `period_cycles`;
- incidencias: los `escalated` del periodo de conversaciones de clientes, más los frenos `retried`/`grader_fallback`; resueltas si el ciclo en que ocurrieron (con `build_spans`) tiene final;
- freno: las auditorías del periodo por resultado;
- agenda y recordatorios (R5, R6), solo con `reservation_settings`;
- gasto (R7), en su sesión, con `try/except` → `None` y un log `client_report.spend_unavailable` (sin datos de nadie).

**`api/console/client_report.py`** (nuevo): la ruta, sus modelos de respuesta y la validación del periodo (R1.5). Se monta junto a los demás routers de la consola.

### Consola

- `lib/backend/client-report.ts`: tipos del contrato y `clientReport(ref, from, to)`, esparcido en `backendFor`.
- `components/shell/routes-v2.ts` y `components/clients/v2/client-header-v2.tsx`: la pestaña `report`, solo con `conversations:read` y `usage:read` (`clients/[ref]/layout.tsx` le pasa el permiso).
- `app/(console)/clients/[ref]/report/{page,loading,error}.tsx`: la página del servidor lee `from` y `to` de la URL (por defecto, los últimos 30 días en la zona que devuelve la API), pide el informe y la lista de clientes del partner para el selector.
- `components/report/`: `client-report.tsx` (la vista), `report-filters.tsx` (cliente y periodo; cambia la URL con `useTransition`, y mientras tanto la vista pinta su esqueleto) y `report-model.ts` (funciones puras: periodo, porcentajes, columnas de la gráfica).
- `i18n/lanes/report.ts`: el carril de textos, registrado en `messages.ts`.
- Imprimir (R11): `print:` en el marco (`console-shell-v2.tsx`) y en la cabecera del cliente; tema claro en `beforeprint`/`afterprint`; `[print-color-adjust:exact]` en el informe; un encabezado solo de impresión con el cliente, el periodo, la zona y la hora de generación.

### Composición de la página

Dirección estética: la del design system de Auphere (instrumento de trabajo, sobrio y compacto; datos arriba).

1. Filtros en una fila: el selector de cliente, «Desde», «Hasta», los atajos 7/30/90 días y «Imprimir» (la única acción principal).
2. Cuatro cifras (`Metric`): conversaciones atendidas, resueltas sin persona (con «objetivo 70 %»), primera respuesta ≤60 s (con «objetivo 95 %») y gasto del periodo (con «X por conversación»).
3. La gráfica por día (`BlockChart`, dos series: «Resueltas sin persona» en `series-1`, «Con persona» en `series-2`).
4. Agenda (tabla operación × quién) y Recordatorios (tabla tipo × resultado), en dos columnas en escritorio.
5. Incidencias: recuento por motivo y la lista.
6. Freno de reservas y la nota de sus límites.
7. Las definiciones de cada cifra, al pie de cada bloque.

## Estructura de archivos

```text
apps/api/src/nexus_api/
├── services/improvement/performance.py      # cambia
├── services/client_report.py                # nuevo
└── api/console/client_report.py             # nuevo (+ montaje del router)
apps/api/tests/
├── unit/test_083_cycles.py                  # nuevo
├── integration/console/test_client_report.py  # nuevo
├── integration/improvement/test_suggestions.py  # se siembra historial
└── isolation/test_client_report_scope.py    # nuevo
apps/console/src/
├── lib/backend/client-report.ts             # nuevo (+ backendFor)
├── components/report/*                      # nuevo
├── components/shell/{routes-v2.ts,console-shell-v2.tsx}  # pestaña e impresión
├── components/clients/v2/client-header-v2.tsx           # pestaña
├── app/(console)/clients/[ref]/layout.tsx              # permiso de la pestaña
├── app/(console)/clients/[ref]/report/*                # nuevo
└── i18n/lanes/report.ts                     # nuevo (+ messages.ts)
```

## Complexity Tracking

| Qué | Por qué | Alternativa descartada |
|---|---|---|
| El constructor de ciclos en Python, no en SQL | Las reglas de reapertura (D3) y de ciclo previo al periodo son secuenciales; en SQL harían falta ventanas encadenadas difíciles de probar. La función pura se prueba sin base. | Una consulta con `LAG`/`LEAD` sobre los eventos. |
| Tocar el marco de la consola para imprimir | El marco fija el alto y desplaza dentro: sin `print:` corta el informe. Son clases `print:` que no cambian la pantalla. | CSS global de impresión (más difícil de ver de dónde sale). |
