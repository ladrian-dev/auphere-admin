# Implementation Plan: los números permitidos se editan en Ajustes del agente

**Branch**: `024-numeros-permitidos` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/024-numeros-permitidos/spec.md`

## Summary

El modo «solo administradores» que ya tiene el runtime gana pantalla en la
consola: en Ajustes del agente, una sección «A quién responde» con *A todo
el mundo* o *Solo a estos números*, guardada en el borrador y aplicada al
publicar, como el resto de ajustes. La lista sigue viviendo en
`policies.admin_access` (única verdad, compartida con la API de partners).
La pantalla dice cuándo un cliente está limitado (cabecera, lista de
clientes, Companion) y Conversaciones enseña cuántos mensajes quedaron sin
respuesta por no estar en la lista, gracias a una columna nueva en el
mensaje. Las plantillas de solo administradores no se pueden abrir a todo
el mundo. Una migración, ningún endpoint nuevo, ninguna dependencia nueva.

## Technical Context

**Language/Version**: Python 3.14 (API, worker) · TypeScript 5 / Next.js 16 (consola)

**Primary Dependencies**: FastAPI · SQLAlchemy async · react-hook-form + zod (ya en la consola) — **ninguna nueva**

**Storage**: PostgreSQL con RLS; `admin_access` en `agent_configs.policies` (existe); una columna nueva `messages.skipped_reason` (migración `0136_message_skipped_reason`, id ≤ 32 caracteres)

**Testing**: pytest (`unit`, `isolation`) para la API; pytest del worker (`tests/unit/test_dispatcher_admin_gate.py` existe); vitest en la consola; staging con número real para CE-002

**Target Platform**: API y worker en AWS, consola en Vercel

**Project Type**: monorepo — servicio web + worker + consola

**Performance Goals**: la lista de clientes lee la audiencia una vez por página (una consulta), nunca por fila

**Constraints**: se aplica al publicar (clarificación A) · el remitente lo decide el servidor (constitución I) · la ausencia de respuesta se enseña, no se calla (V) · la comparación de números es la que ya existe (Requisito 2.3)

**Scale/Scope**: una sección de formulario, dos campos de salida, una columna, una migración; 11 plantillas sin cambio (solo cobranza es de solo administradores)

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto, nunca del llamante | ☑ | La lista es parte de `agent_configs` del tenant; el remitente lo fija el webhook desde el canal. Test en `tests/isolation/test_console_agent_settings_audience.py`: el PUT de A no toca a B; barrido OpenAPI sin `tenant_id`/`sender` |
| II | Corte por superficie de confianza | ☑ | Superficie `0` |
| III | Lo leído es dato, nunca instrucción | ☑ | Los números y nombres son datos de configuración; no entran en el prompt |
| IV | Acción `mutates` con aprobación; auditoría nombra a la persona | ☑ | Guardar audita «cambió los ajustes del agente» (existe); publicar audita y es el paso explícito |
| V | Estados honestos; la ausencia se diseña | ☑ | «Responde solo a N números» en cabecera y lista; «N sin responder · número no permitido» en Conversaciones (D3, D4) |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | El Companion lee `audience` por `console.get_client` |
| VII | Test primero | ☑ | Cada bloque nace con su test rojo; el primero es el del gate con motivo (worker) |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | La KB es dueña del porqué | ☑ | `[[sessions/2026-09-30-spec-023-tres-conectores-mas]]`, `[[clients/flor-y-encanto]]` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía cambia. Test de que la escritura de la lista queda en el tenant del scope y de que la ruta no acepta identificadores de tenant ni de remitente | `T-ISO` en `tests/isolation/` |
| **Licencias** | Ninguna dependencia nueva | `T-LIC` |
| **Medidor** | Nada nuevo: un mensaje suprimido no llega al modelo | `T-MET` (aserción en el test del worker: cero eventos de consumo) |

## Project Structure

### Documentation (this feature)

```text
specs/024-numeros-permitidos/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/audience.md
├── evidence/
└── tasks.md
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/0136_message_skipped_reason.py
├── src/nexus_api/
│   ├── db/models/conversation.py                # Message.skipped_reason
│   ├── services/agent_audience.py               # NUEVO: leer/escribir admin_access como «audience», validar, locked
│   ├── api/console/agent_settings.py            # GET/PUT con audience
│   ├── api/console/schemas_agent_tools.py       # AudienceOut/AudienceIn/AudienceNumber; AgentSettingsIn/Out
│   ├── api/console/schemas.py                   # ClientAudienceOut en ClientSummaryOut/ClientOut
│   ├── api/console/tenants.py                   # audiencia por cliente (una consulta por página)
│   ├── api/console/conversations.py             # unanswered por conversación y en stats
│   └── api/console/schemas_*.py                 # ConversationOut.unanswered, ConversationStatsOut.unanswered
└── tests/
    ├── unit/test_agent_audience.py              # NUEVO
    ├── unit/test_endpoint_console_agent_settings_audience.py   # NUEVO
    ├── unit/test_endpoint_console_clients_audience.py          # NUEVO
    ├── unit/test_endpoint_console_conversations_unanswered.py  # NUEVO
    └── isolation/test_console_agent_settings_audience.py       # NUEVO

apps/worker/
├── src/nexus_worker/runtime/dispatcher.py       # marca skipped_reason="not_admin" en el entrante suprimido
└── tests/unit/test_dispatcher_admin_gate.py     # + el motivo queda en el mensaje; cero consumo

apps/console/src/
├── lib/backend/agent-tools-types.ts             # Audience types; ClientAudience
├── components/agent-tools/settings-schema.ts    # audience en el espejo zod; parseo de líneas
├── components/agent-tools/agent-settings-form.tsx  # sección «A quién responde»
├── components/agent-tools/audience-lines.ts     # NUEVO: texto ↔ números (puro, testeable)
├── components/clients/client-header-model.ts / clients-table.tsx / summary/…  # «Responde solo a N números»
├── app/(console)/clients/[ref]/conversations/page.tsx  # columna «sin responder»
└── i18n/lanes/agent-tools.ts · record.ts · conversations lane
```

**Structure Decision**: un módulo de servicio (`agent_audience.py`) concentra
la traducción `admin_access` ↔ `audience`, la validación y el bloqueo por
plantilla, para que el endpoint de ajustes, el de clientes y los tests
lean lo mismo. El gate del runtime (`admin_gate.py`) no se toca.

## Fase 1 — diseño

| Artefacto | Qué fija |
|---|---|
| [`research.md`](research.md) | D0–D6: dónde vive la lista, cuándo se aplica, cómo se enseña, la columna del mensaje, la sección del formulario |
| [`data-model.md`](data-model.md) | `audience` de entrada y salida, `admin_access` resultante, la columna nueva, los campos de cliente y conversación |
| [`contracts/audience.md`](contracts/audience.md) | Los cambios de forma en ajustes, clientes y conversaciones, con sus códigos |
| [`quickstart.md`](quickstart.md) | La suite local y la prueba en staging con número real |

### El orden de entrega

1. **API y worker**: `agent_audience.py`, ajustes con `audience`, migración
   y motivo en el mensaje, aislamiento. Con esto la lista ya se puede fijar
   desde la consola por API.
2. **La sección del formulario**: Historia 1 completa.
3. **La pantalla honesta**: cabecera, lista de clientes, Conversaciones,
   Companion. Historia 2.
4. **El bloqueo por plantilla**: `locked` en API y formulario. Historia 3.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple, y por qué no |
|---|---|---|
| Columna `messages.skipped_reason` y migración | Requisito 3.2: Conversaciones tiene que decir por qué un mensaje quedó sin respuesta, y hoy nada lo distingue de uno pendiente | Deducirlo cruzando la lista con los entrantes sin saliente: se equivoca en cuanto la lista cambia (D4) |
| Módulo `agent_audience.py` | Tres endpoints (ajustes, clientes, conversaciones) y el Companion leen la misma cosa; una sola traducción evita tres | Traducir en cada endpoint: tres copias que se desfasan |
| Lectura de la plantilla para `locked` | Historia 3: cobranza no se puede abrir a todo el mundo | Una bandera en el tenant: duplicaría lo que la plantilla ya declara |
